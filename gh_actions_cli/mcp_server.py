"""MCP server exposing gh-actions-cli's GitHub Actions functionality as tools for agents.

Configuration is read from the same environment variables as the CLI
(GITHUB_PAT, GITHUB_REPOSITORY, GITHUB_API_URL, GH_ACTIONS_DEFAULT_BRANCH, ...).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mcp.server import MCPServer

from gh_actions_cli.artifacts import extract_artifact_zip
from gh_actions_cli.config import AppConfig, ConfigError, load_config
from gh_actions_cli.github_api import GitHubActionsClient
from gh_actions_cli.logs import extract_job_logs, extract_step_log
from gh_actions_cli.models import ArtifactSummary, JobSummary, WorkflowRunSummary, WorkflowSummary
from gh_actions_cli.workflow_parser import WorkflowParseError, extract_workflow_dispatch_inputs

server = MCPServer(
    name="gh-actions-cli",
    description="Inspect, run, and diagnose GitHub Actions workflows for a configured repository.",
)


@contextmanager
def _client() -> Iterator[tuple[GitHubActionsClient, AppConfig]]:
    config = load_config()
    with GitHubActionsClient(config) as client:
        yield client, config


def _resolve_ref(client: GitHubActionsClient, config: AppConfig, ref: str | None) -> str:
    if ref:
        return ref
    if config.default_branch:
        return config.default_branch
    repository = client.get_repository()
    return str(repository.get("default_branch") or "main")


def _workflow_dict(workflow: WorkflowSummary) -> dict[str, Any]:
    return {"id": workflow.id, "name": workflow.name, "path": workflow.path, "state": workflow.state}


def _run_dict(run: WorkflowRunSummary) -> dict[str, Any]:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "name": run.name,
        "status": run.status,
        "conclusion": run.conclusion,
        "head_branch": run.head_branch,
    }


def _job_dict(job: JobSummary) -> dict[str, Any]:
    return {
        "id": job.id,
        "run_id": job.run_id,
        "name": job.name,
        "status": job.status,
        "conclusion": job.conclusion,
        "steps": [
            {"number": step.number, "name": step.name, "status": step.status, "conclusion": step.conclusion}
            for step in job.steps
        ],
    }


def _artifact_dict(artifact: ArtifactSummary) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "run_id": artifact.run_id,
        "name": artifact.name,
        "size_in_bytes": artifact.size_in_bytes,
        "expired": artifact.expired,
    }


def _find_job(jobs: list[JobSummary], job: str) -> JobSummary:
    if job.isdigit():
        job_id = int(job)
        for candidate in jobs:
            if candidate.id == job_id:
                return candidate
    for candidate in jobs:
        if candidate.name == job:
            return candidate
    raise ValueError(f"Job '{job}' not found in this run.")


def _find_workflow(workflows: list[WorkflowSummary], workflow: str) -> WorkflowSummary:
    if workflow.isdigit():
        workflow_id = int(workflow)
        for candidate in workflows:
            if candidate.id == workflow_id:
                return candidate
    for candidate in workflows:
        if Path(candidate.path).name == workflow or candidate.name == workflow:
            return candidate
    raise ValueError(f"Workflow '{workflow}' not found.")


@server.tool()
def list_workflows() -> list[dict[str, Any]]:
    """List all GitHub Actions workflows defined in the configured repository."""
    with _client() as (client, _config):
        return [_workflow_dict(workflow) for workflow in client.list_workflows()]


@server.tool()
def get_workflow_dispatch_inputs(workflow: str, ref: str | None = None) -> list[dict[str, Any]]:
    """Get the `workflow_dispatch` input parameters declared by a workflow.

    `workflow` may be a workflow id, file name (e.g. "ci.yml"), or workflow name.
    `ref` defaults to the repository's default branch.
    """
    with _client() as (client, config):
        workflows = client.list_workflows()
        target = _find_workflow(workflows, workflow)
        resolved_ref = _resolve_ref(client, config, ref)
        yaml_text = client.get_workflow_file_content(target.path, resolved_ref)
        try:
            inputs = extract_workflow_dispatch_inputs(yaml_text)
        except WorkflowParseError as error:
            raise ValueError(str(error)) from error
        return [
            {
                "name": item.name,
                "description": item.description,
                "required": item.required,
                "default": item.default,
                "type": item.type,
                "options": item.options,
            }
            for item in inputs
        ]


@server.tool()
def dispatch_workflow(workflow: str, ref: str | None = None, inputs: dict[str, str] | None = None) -> dict[str, Any]:
    """Trigger a `workflow_dispatch` run.

    `workflow` may be a workflow id, file name (e.g. "ci.yml"), or workflow name.
    `ref` defaults to the repository's default branch. `inputs` are the
    workflow_dispatch input values (see get_workflow_dispatch_inputs).
    """
    with _client() as (client, config):
        workflows = client.list_workflows()
        target = _find_workflow(workflows, workflow)
        resolved_ref = _resolve_ref(client, config, ref)
        client.dispatch_workflow(Path(target.path).name, resolved_ref, inputs or {})
        return {"dispatched": True, "workflow": _workflow_dict(target), "ref": resolved_ref, "inputs": inputs or {}}


@server.tool()
def list_runs(workflow: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """List recent workflow runs for the repository, optionally filtered to one workflow."""
    with _client() as (client, _config):
        if workflow:
            workflows = client.list_workflows()
            target = _find_workflow(workflows, workflow)
            runs = client.get_workflow_runs(target.id, limit=limit)
        else:
            runs = client.list_repository_runs(limit=limit)
        return [_run_dict(run) for run in runs]


@server.tool()
def get_run(run_id: int) -> dict[str, Any]:
    """Get the status and conclusion of a single workflow run."""
    with _client() as (client, _config):
        return _run_dict(client.get_run(run_id))


@server.tool()
def cancel_run(run_id: int) -> dict[str, Any]:
    """Cancel an in-progress or queued workflow run."""
    with _client() as (client, _config):
        client.cancel_run(run_id)
        return {"cancelled": True, "run_id": run_id}


@server.tool()
def list_jobs(run_id: int) -> list[dict[str, Any]]:
    """List jobs (and their steps) for a workflow run."""
    with _client() as (client, _config):
        return [_job_dict(job) for job in client.list_jobs(run_id)]


@server.tool()
def get_job_log(run_id: int, job: str, tail_lines: int | None = None) -> dict[str, Any]:
    """Get the raw log output for one job in a run.

    `job` may be a job id or job name. `tail_lines`, if set, returns only the
    last N lines instead of the full log.
    """
    with _client() as (client, _config):
        jobs = client.list_jobs(run_id)
        target = _find_job(jobs, job)
        archive = client.download_run_logs(run_id)
        job_logs = extract_job_logs(archive, jobs)
        job_log = job_logs.get(target.id)
        if job_log is None:
            raise ValueError(f"No log content found for job '{job}'.")
        content = job_log.content
        if tail_lines is not None:
            content = "\n".join(content.splitlines()[-tail_lines:])
        return {"job_id": target.id, "job_name": target.name, "content": content}


@server.tool()
def get_step_log(run_id: int, job: str, step: str) -> dict[str, Any]:
    """Get the log output for a single step within a job.

    `job` may be a job id or job name. `step` may be a step number or step name.
    """
    with _client() as (client, _config):
        jobs = client.list_jobs(run_id)
        target = _find_job(jobs, job)
        archive = client.download_run_logs(run_id)
        job_logs = extract_job_logs(archive, jobs)
        job_log = job_logs.get(target.id)
        if job_log is None:
            raise ValueError(f"No log content found for job '{job}'.")
        result = extract_step_log(job_log.content, target, step)
        return {"step_name": result.step_name, "content": result.content, "fallback_used": result.fallback_used}


@server.tool()
def list_artifacts(run_id: int) -> list[dict[str, Any]]:
    """List artifacts produced by a workflow run."""
    with _client() as (client, _config):
        return [_artifact_dict(artifact) for artifact in client.list_run_artifacts(run_id)]


@server.tool()
def download_artifact(artifact_id: int, destination_dir: str) -> dict[str, Any]:
    """Download and extract an artifact's zip contents to a local directory."""
    with _client() as (client, _config):
        archive = client.download_artifact_zip(artifact_id)
        paths = extract_artifact_zip(archive, Path(destination_dir).expanduser())
        return {"extracted_to": str(Path(destination_dir).expanduser()), "files": [str(path) for path in paths]}


@server.tool()
def get_runner_load(limit: int = 100) -> dict[str, Any]:
    """Summarize current queued/in-progress run pressure across the repository's workflows."""
    with _client() as (client, _config):
        runs = client.list_repository_runs(limit=limit)
        active_runs = [run for run in runs if run.status in {"queued", "in_progress", "pending", "waiting"}]
        queued = sum(1 for run in active_runs if run.status == "queued")
        in_progress = sum(1 for run in active_runs if run.status == "in_progress")

        by_workflow: dict[int | None, dict[str, Any]] = {}
        for run in active_runs:
            entry = by_workflow.setdefault(
                run.workflow_id, {"workflow_id": run.workflow_id, "workflow_name": run.name, "queued": 0, "in_progress": 0}
            )
            if run.status == "queued":
                entry["queued"] += 1
            elif run.status == "in_progress":
                entry["in_progress"] += 1

        if queued >= 2 or queued + in_progress >= 4:
            pressure = "overloaded"
        elif queued >= 1 or in_progress >= 2:
            pressure = "moderate"
        else:
            pressure = "free"

        workflows = sorted(
            by_workflow.values(),
            key=lambda item: (item["queued"] + item["in_progress"], item["queued"], item["workflow_name"]),
            reverse=True,
        )
        return {
            "queued": queued,
            "in_progress": in_progress,
            "total_active": queued + in_progress,
            "pressure": pressure,
            "workflows": workflows,
        }


def main() -> int:
    try:
        load_config()
    except ConfigError as error:
        import sys

        print(f"gh-actions-mcp: {error}", file=sys.stderr)
        return 1
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
