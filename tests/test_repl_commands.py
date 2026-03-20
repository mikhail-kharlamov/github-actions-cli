from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from rich.console import Console

from gh_actions_cli.app import App
from gh_actions_cli.config import AppConfig
from gh_actions_cli import repl
from gh_actions_cli.models import JobSummary, StepSummary, WorkflowSummary


class FakeGitHubClient:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str | int, str, dict[str, str]]] = []
        self.downloaded_artifacts: list[int] = []

    def list_workflows(self) -> list[WorkflowSummary]:
        return [WorkflowSummary(id=101, name="Build", path=".github/workflows/build.yml", state="active")]

    def get_workflow_runs(self, workflow_id: str | int, limit: int = 10) -> list:
        return []

    def get_run(self, run_id: int):
        raise AssertionError("unused")

    def list_jobs(self, run_id: int) -> list[JobSummary]:
        return [
            JobSummary(
                id=201,
                run_id=run_id,
                name="test",
                status="completed",
                conclusion="success",
                steps=[StepSummary(number=1, name="Checkout", status="completed", conclusion="success")],
            )
        ]

    def dispatch_workflow(self, workflow_id_or_file: str | int, ref: str, inputs: dict[str, str]) -> None:
        self.dispatched.append((workflow_id_or_file, ref, inputs))

    def download_run_logs(self, run_id: int) -> bytes:
        raise AssertionError("unused")

    def get_workflow_file_content(self, path: str, ref: str) -> str:
        return """
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
"""

    def get_repository(self) -> dict:
        return {"default_branch": "main"}

    def list_run_artifacts(self, run_id: int) -> list:
        from gh_actions_cli.models import ArtifactSummary

        return [
            ArtifactSummary(
                id=501,
                run_id=run_id,
                name="eval-agent-result",
                size_in_bytes=4096,
                expired=False,
                archive_download_url="https://api.github.com/repos/owner/repo/actions/artifacts/501/zip",
            )
        ]

    def download_artifact_zip(self, artifact_id: int) -> bytes:
        self.downloaded_artifacts.append(artifact_id)
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("result.txt", "artifact payload")
        return buffer.getvalue()


def _make_app() -> tuple[App, Console, FakeGitHubClient]:
    console = Console(record=True, width=120)
    client = FakeGitHubClient()
    config = AppConfig(
        github_pat="token",
        github_repository="owner/repo",
        owner="owner",
        repo="repo",
        github_api_url="https://api.github.com",
        poll_interval=0,
        default_branch=None,
    )
    return App(config=config, console=console, github_client=client), console, client


def test_workflows_command_updates_session_indexes() -> None:
    app, _console, _client = _make_app()

    should_continue = app.handle_line("/workflows")

    assert should_continue is True
    assert app.session.workflow_index[1].id == 101


def test_steps_command_uses_last_job_index() -> None:
    app, console, _client = _make_app()
    app.session.job_index[1] = JobSummary(
        id=201,
        run_id=301,
        name="test",
        status="completed",
        conclusion="success",
        steps=[],
    )

    app.handle_line("/steps 1")

    output = console.export_text()
    assert "Checkout" in output


def test_run_command_dispatches_workflow_using_list_index() -> None:
    app, _console, client = _make_app()
    app.handle_line("/workflows")

    app.handle_line("/run 1 ref=develop dry_run=true")

    assert client.dispatched == [("build.yml", "develop", {"dry_run": "true"})]


def test_quit_command_stops_repl() -> None:
    app, _console, _client = _make_app()

    should_continue = app.handle_line("/quit")

    assert should_continue is False


def test_artifacts_command_updates_session_indexes() -> None:
    app, _console, _client = _make_app()
    app.session.run_index[1] = SimpleNamespace(id=301)

    should_continue = app.handle_line("/artifacts 1")

    assert should_continue is True
    assert app.session.artifact_index[1].id == 501


def test_download_artifacts_command_extracts_selected_artifact(tmp_path: Path) -> None:
    app, _console, client = _make_app()
    app.session.run_index[1] = SimpleNamespace(id=301)
    app.handle_line("/artifacts 1")

    should_continue = app.handle_line(f"/download-artifacts 1 1 dir={tmp_path}")

    assert should_continue is True
    assert client.downloaded_artifacts == [501]
    assert (tmp_path / "eval-agent-result" / "result.txt").read_text() == "artifact payload"


def test_download_artifacts_command_creates_missing_target_directory(tmp_path: Path) -> None:
    app, _console, client = _make_app()
    missing_dir = tmp_path / "nested" / "artifacts"
    app.session.run_index[1] = SimpleNamespace(id=301)
    app.handle_line("/artifacts 1")

    should_continue = app.handle_line(f"/download-artifacts 1 1 dir={missing_dir}")

    assert should_continue is True
    assert client.downloaded_artifacts == [501]
    assert (missing_dir / "eval-agent-result" / "result.txt").read_text() == "artifact payload"


def test_enable_line_editing_binds_history_keys(monkeypatch) -> None:
    calls: list[str] = []
    fake_readline = SimpleNamespace(parse_and_bind=calls.append)
    monkeypatch.setitem(sys.modules, "readline", fake_readline)

    result = repl.enable_line_editing()

    assert result is fake_readline
    assert calls == ["tab: complete"]


def test_run_repl_adds_entered_commands_to_history(monkeypatch) -> None:
    history: list[str] = []
    fake_readline = SimpleNamespace(parse_and_bind=lambda _value: None, add_history=history.append)
    monkeypatch.setattr(repl, "enable_line_editing", lambda: fake_readline)

    app, console, _client = _make_app()
    inputs = iter(["/help", "/quit"])
    monkeypatch.setattr(console, "input", lambda _prompt: next(inputs))

    exit_code = repl.run_repl(app, console)

    assert exit_code == 0
    assert history == ["/help", "/quit"]
