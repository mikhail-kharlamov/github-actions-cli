from __future__ import annotations

import base64

import httpx

from gh_actions_cli.config import AppConfig
from gh_actions_cli.models import ArtifactSummary, JobSummary, StepSummary, WorkflowRunSummary, WorkflowSummary


class GitHubAPIError(RuntimeError):
    """Raised when GitHub API returns an error response."""


class GitHubActionsClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client: httpx.Client | None = None

    def __enter__(self) -> "GitHubActionsClient":
        self._client = httpx.Client(
            base_url=self.config.github_api_url,
            headers={
                "Authorization": f"Bearer {self.config.github_pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    def __exit__(self, *_args: object) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def list_workflows(self) -> list[WorkflowSummary]:
        payload = self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/workflows")
        return [
            WorkflowSummary(
                id=item["id"],
                name=item["name"],
                path=item["path"],
                state=item.get("state", "unknown"),
            )
            for item in payload.get("workflows", [])
        ]

    def get_workflow(self, workflow_id: str | int) -> WorkflowSummary:
        payload = self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/workflows/{workflow_id}")
        return WorkflowSummary(
            id=payload["id"],
            name=payload["name"],
            path=payload["path"],
            state=payload.get("state", "unknown"),
        )

    def get_workflow_runs(self, workflow_id: str | int, limit: int = 10) -> list[WorkflowRunSummary]:
        payload = self._get_json(
            f"/repos/{self.config.owner}/{self.config.repo}/actions/workflows/{workflow_id}/runs",
            params={"per_page": str(limit)},
        )
        return [self._parse_run(item) for item in payload.get("workflow_runs", [])]

    def get_run(self, run_id: int) -> WorkflowRunSummary:
        payload = self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}")
        return self._parse_run(payload)

    def get_run_payload(self, run_id: int) -> dict:
        return self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}")

    def list_jobs(self, run_id: int) -> list[JobSummary]:
        payload = self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}/jobs")
        jobs: list[JobSummary] = []
        for item in payload.get("jobs", []):
            steps = [
                StepSummary(
                    number=step["number"],
                    name=step["name"],
                    status=step.get("status", "unknown"),
                    conclusion=step.get("conclusion"),
                )
                for step in item.get("steps", [])
            ]
            jobs.append(
                JobSummary(
                    id=item["id"],
                    run_id=item["run_id"],
                    name=item["name"],
                    status=item.get("status", "unknown"),
                    conclusion=item.get("conclusion"),
                    steps=steps,
                )
            )
        return jobs

    def list_run_artifacts(self, run_id: int) -> list[ArtifactSummary]:
        payload = self._get_json(f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}/artifacts")
        return [
            ArtifactSummary(
                id=item["id"],
                run_id=run_id,
                name=item["name"],
                size_in_bytes=item.get("size_in_bytes", 0),
                expired=bool(item.get("expired", False)),
                archive_download_url=item.get("archive_download_url", ""),
            )
            for item in payload.get("artifacts", [])
        ]

    def dispatch_workflow(self, workflow_id_or_file: str | int, ref: str, inputs: dict[str, str]) -> None:
        self._request(
            "POST",
            f"/repos/{self.config.owner}/{self.config.repo}/actions/workflows/{workflow_id_or_file}/dispatches",
            json={"ref": ref, "inputs": inputs},
        )

    def download_run_logs(self, run_id: int) -> bytes:
        response = self._request("GET", f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}/logs")
        return response.content

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        response = self._request(
            "GET",
            f"/repos/{self.config.owner}/{self.config.repo}/actions/artifacts/{artifact_id}/zip",
        )
        return response.content

    def cancel_run(self, run_id: int) -> None:
        self._request("POST", f"/repos/{self.config.owner}/{self.config.repo}/actions/runs/{run_id}/cancel")

    def get_workflow_file_content(self, path: str, ref: str) -> str:
        payload = self._get_json(
            f"/repos/{self.config.owner}/{self.config.repo}/contents/{path}",
            params={"ref": ref},
        )
        content = payload.get("content", "")
        if payload.get("encoding") == "base64":
            return base64.b64decode(content).decode("utf-8")
        return content

    def get_repository(self) -> dict:
        return self._get_json(f"/repos/{self.config.owner}/{self.config.repo}")

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict:
        response = self._request("GET", path, params=params)
        return response.json()

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("GitHubActionsClient must be used as a context manager.")
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as error:
            raise GitHubAPIError(str(error)) from error
        if response.is_error:
            self._raise_api_error(response)
        return response

    def _raise_api_error(self, response: httpx.Response) -> None:
        message = ""
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            message = str(payload.get("message", ""))
        if not message:
            message = f"GitHub API error: {response.status_code}"
        raise GitHubAPIError(message)

    @staticmethod
    def _parse_run(item: dict) -> WorkflowRunSummary:
        return WorkflowRunSummary(
            id=item["id"],
            workflow_id=item.get("workflow_id"),
            name=item.get("name") or item.get("display_title") or str(item["id"]),
            status=item.get("status", "unknown"),
            conclusion=item.get("conclusion"),
            head_branch=item.get("head_branch"),
        )
