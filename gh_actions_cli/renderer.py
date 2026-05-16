from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gh_actions_cli.models import (
    ArtifactSummary,
    JobSummary,
    RunnerLoadSummary,
    StepSummary,
    WorkflowDispatchInput,
    WorkflowRunSummary,
    WorkflowSummary,
)


def status_style(status: str | None, conclusion: str | None = None) -> str:
    target = conclusion or status or ""
    if target in {"success", "completed"}:
        return "green"
    if target in {"failure", "timed_out", "cancelled", "action_required"}:
        return "red"
    if target in {"queued", "in_progress", "waiting", "pending"}:
        return "yellow"
    return "dim"


def render_workflows(console: Console, workflows: list[WorkflowSummary]) -> None:
    table = Table(title="GitHub Workflows")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("File", style="dim")
    table.add_column("State")
    for index, workflow in enumerate(workflows, start=1):
        table.add_row(str(index), workflow.name, workflow.path.rsplit("/", maxsplit=1)[-1], workflow.state)
    console.print(table)


def render_runs(console: Console, runs: list[WorkflowRunSummary]) -> None:
    table = Table(title="Workflow Runs")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Run ID")
    table.add_column("Name")
    table.add_column("Branch")
    table.add_column("Status")
    for index, run in enumerate(runs, start=1):
        style = status_style(run.status, run.conclusion)
        status = run.conclusion or run.status
        table.add_row(str(index), str(run.id), run.name, run.head_branch or "-", f"[{style}]{status}[/{style}]")
    console.print(table)


def render_jobs(console: Console, jobs: list[JobSummary]) -> None:
    table = Table(title="Jobs")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Job ID")
    table.add_column("Name")
    table.add_column("Status")
    for index, job in enumerate(jobs, start=1):
        style = status_style(job.status, job.conclusion)
        table.add_row(str(index), str(job.id), job.name, f"[{style}]{job.conclusion or job.status}[/{style}]")
    console.print(table)


def render_steps(console: Console, steps: list[StepSummary]) -> None:
    table = Table(title="Steps")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Step")
    table.add_column("Status")
    for step in steps:
        style = status_style(step.status, step.conclusion)
        table.add_row(str(step.number), step.name, f"[{style}]{step.conclusion or step.status}[/{style}]")
    console.print(table)


def render_dispatch_inputs(console: Console, inputs: list[WorkflowDispatchInput]) -> None:
    table = Table(title="workflow_dispatch inputs")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Required")
    table.add_column("Default")
    table.add_column("Description")
    for item in inputs:
        default = "" if item.default is None else str(item.default)
        required = "yes" if item.required else "no"
        description = item.description
        if item.options:
            description = f"{description} Options: {', '.join(item.options)}".strip()
        table.add_row(item.name, item.type, required, default, description)
    console.print(table)


def render_artifacts(console: Console, artifacts: list[ArtifactSummary]) -> None:
    table = Table(title="Artifacts")
    table.add_column("#", style="cyan", no_wrap=True)
    table.add_column("Artifact ID")
    table.add_column("Name")
    table.add_column("Size")
    table.add_column("Expired")
    for index, artifact in enumerate(artifacts, start=1):
        table.add_row(
            str(index),
            str(artifact.id),
            artifact.name,
            str(artifact.size_in_bytes),
            "yes" if artifact.expired else "no",
        )
    console.print(table)


def render_runner_load(console: Console, summary: RunnerLoadSummary) -> None:
    pressure_style = {
        "Свободно": "green",
        "Умеренно": "yellow",
        "Перегружено": "red",
    }.get(summary.pressure, "cyan")
    lines = [
        "runner-load",
        f"Оценка: {summary.pressure}",
        f"queued: {summary.queued}",
        f"in_progress: {summary.in_progress}",
        f"active_total: {summary.total_active}",
    ]
    console.print(Panel("\n".join(lines), border_style=pressure_style, title="Runner Load"))

    table = Table(title="By Workflow")
    table.add_column("Workflow")
    table.add_column("Queued")
    table.add_column("In Progress")
    table.add_column("Total Active")
    for item in summary.workflows:
        table.add_row(
            item.workflow_name,
            str(item.queued),
            str(item.in_progress),
            str(item.queued + item.in_progress),
        )
    console.print(table)


def render_message(console: Console, text: str, style: str = "cyan") -> None:
    console.print(Panel(text, border_style=style))


def render_error(console: Console, text: str) -> None:
    console.print(Panel(text, border_style="red", title="Ошибка"))
