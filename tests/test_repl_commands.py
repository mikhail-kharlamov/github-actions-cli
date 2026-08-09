from __future__ import annotations

import builtins
import dataclasses
import datetime
import sys
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from rich.console import Console

from gh_actions_cli.app import App, _parse_defer_time
from gh_actions_cli.config import AppConfig
from gh_actions_cli import repl
from gh_actions_cli.models import JobSummary, StepSummary, WorkflowRunSummary, WorkflowSummary


class FakeGitHubClient:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str | int, str, dict[str, str]]] = []
        self.downloaded_artifacts: list[int] = []
        self.cancelled_runs: list[int] = []

    def list_workflows(self) -> list[WorkflowSummary]:
        return [WorkflowSummary(id=101, name="Build", path=".github/workflows/build.yml", state="active")]

    def get_workflow_runs(self, workflow_id: str | int, limit: int = 10) -> list:
        from gh_actions_cli.models import WorkflowRunSummary

        return [
            WorkflowRunSummary(
                id=301,
                workflow_id=101,
                name="Build",
                status="in_progress",
                conclusion=None,
                head_branch="main",
            )
        ]

    def get_run(self, run_id: int):
        from gh_actions_cli.models import WorkflowRunSummary

        return WorkflowRunSummary(
            id=run_id,
            workflow_id=101,
            name="Build",
            status="in_progress",
            conclusion=None,
            head_branch="main",
        )

    def get_run_payload(self, run_id: int) -> dict:
        return {
            "id": run_id,
            "name": "Build",
            "display_title": "Build",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": "abc123",
            "path": ".github/workflows/build.yml@refs/heads/main",
        }

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
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(
                "test_2.txt",
                "\n".join(
                    [
                        "2026-03-19T10:00:01Z ##[group]Run Checkout",
                        "2026-03-19T10:00:02Z cloning repo",
                        "2026-03-19T10:00:03Z ##[endgroup]",
                    ]
                ),
            )
        return buffer.getvalue()

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

    def list_repository_runs(self, limit: int = 100) -> list:
        from gh_actions_cli.models import WorkflowRunSummary

        return [
            WorkflowRunSummary(
                id=301,
                workflow_id=101,
                name="Build",
                status="queued",
                conclusion=None,
                head_branch="main",
            ),
            WorkflowRunSummary(
                id=302,
                workflow_id=101,
                name="Build",
                status="in_progress",
                conclusion=None,
                head_branch="main",
            ),
            WorkflowRunSummary(
                id=303,
                workflow_id=102,
                name="Deploy",
                status="queued",
                conclusion=None,
                head_branch="release",
            ),
            WorkflowRunSummary(
                id=304,
                workflow_id=102,
                name="Deploy",
                status="completed",
                conclusion="success",
                head_branch="release",
            ),
        ]

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

    def cancel_run(self, run_id: int) -> None:
        self.cancelled_runs.append(run_id)


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


def test_run_args_command_shows_saved_dispatch_arguments() -> None:
    app, console, _client = _make_app()
    app.handle_line("/workflows")
    app.handle_line("/runs 1")
    app.handle_line("/run 1 ref=develop dry_run=true")
    app.handle_line("/run-args 301")

    output = console.export_text()
    assert "develop" in output
    assert "dry_run" in output


def test_cancel_run_command_cancels_selected_run() -> None:
    app, _console, client = _make_app()
    app.handle_line("/workflows")
    app.handle_line("/runs 1")

    should_continue = app.handle_line("/cancel-run 1")

    assert should_continue is True
    assert client.cancelled_runs == [301]


def test_run_status_shows_current_step_for_in_progress_run() -> None:
    app, console, client = _make_app()
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="in_progress", conclusion=None, head_branch="main",
    )
    client.list_jobs = lambda run_id: [
        JobSummary(
            id=201, run_id=run_id, name="run-java", status="in_progress", conclusion=None,
            steps=[
                StepSummary(number=1, name="Checkout", status="completed", conclusion="success"),
                StepSummary(number=2, name="Run benchmark", status="in_progress"),
                StepSummary(number=3, name="Upload results", status="queued"),
            ],
        ),
        JobSummary(id=202, run_id=run_id, name="run-python", status="queued", conclusion=None),
    ]

    app.handle_line("/run-status 1")

    output = console.export_text()
    assert "run-java" in output
    assert "step 2/3: Run benchmark" in output
    assert "run-python" in output
    assert "queued" in output
    assert app.session.job_index[1].name == "run-java"


def test_run_status_omits_jobs_for_completed_run() -> None:
    app, console, client = _make_app()
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="completed", conclusion="success", head_branch="main",
    )
    calls = []
    client.list_jobs = lambda run_id: calls.append(run_id) or []

    app.handle_line("/run-status 1")

    assert calls == []
    output = console.export_text()
    assert "Jobs" not in output


def test_logs_command_writes_job_log_to_file(tmp_path: Path) -> None:
    app, _console, _client = _make_app()
    app.session.job_index[1] = JobSummary(
        id=201,
        run_id=301,
        name="test",
        status="completed",
        conclusion="success",
        steps=[StepSummary(number=1, name="Checkout", status="completed", conclusion="success")],
    )
    target = tmp_path / "nested" / "job.log"

    should_continue = app.handle_line(f"/logs 1 file={target}")

    assert should_continue is True
    assert target.read_text() != ""
    assert "cloning repo" in target.read_text()


def test_step_log_command_writes_step_log_to_file(tmp_path: Path) -> None:
    app, _console, _client = _make_app()
    app.session.job_index[1] = JobSummary(
        id=201,
        run_id=301,
        name="test",
        status="completed",
        conclusion="success",
        steps=[StepSummary(number=1, name="Checkout", status="completed", conclusion="success")],
    )
    target = tmp_path / "step-logs" / "checkout.log"

    should_continue = app.handle_line(f"/step-log 1 1 file={target}")

    assert should_continue is True
    assert target.read_text() != ""
    assert "Checkout" in target.read_text()


def test_logs_command_can_skip_terminal_output_with_no_print_flag(tmp_path: Path) -> None:
    app, console, _client = _make_app()
    app.session.job_index[1] = JobSummary(
        id=201,
        run_id=301,
        name="test",
        status="completed",
        conclusion="success",
        steps=[StepSummary(number=1, name="Checkout", status="completed", conclusion="success")],
    )
    target = tmp_path / "job.log"

    should_continue = app.handle_line(f"/logs 1 file={target} no_print=true")

    assert should_continue is True
    output = console.export_text()
    assert "cloning repo" not in output
    assert "Лог сохранен" in output
    assert "cloning repo" in target.read_text()


def test_runner_load_command_shows_repository_and_workflow_stats() -> None:
    app, console, _client = _make_app()

    should_continue = app.handle_line("/runner-load")

    output = console.export_text()
    assert should_continue is True
    assert "runner-load" in output
    assert "queued: 2" in output
    assert "in_progress: 1" in output
    assert "Перегружено" in output
    assert "Build" in output
    assert "Deploy" in output


def test_step_log_command_can_skip_terminal_output_with_no_print_flag(tmp_path: Path) -> None:
    app, console, _client = _make_app()
    app.session.job_index[1] = JobSummary(
        id=201,
        run_id=301,
        name="test",
        status="completed",
        conclusion="success",
        steps=[StepSummary(number=1, name="Checkout", status="completed", conclusion="success")],
    )
    target = tmp_path / "step.log"

    should_continue = app.handle_line(f"/step-log 1 1 file={target} no_print=true")

    assert should_continue is True
    output = console.export_text()
    assert "cloning repo" not in output
    assert "Лог сохранен" in output
    assert "cloning repo" in target.read_text()


def test_quit_command_stops_repl() -> None:
    app, _console, _client = _make_app()

    should_continue = app.handle_line("/quit")

    assert should_continue is False


# --- /lang tests ---

def test_lang_command_shows_current_language_with_no_args() -> None:
    app, console, _client = _make_app()

    should_continue = app.handle_line("/lang")

    assert should_continue is True
    assert "ru" in console.export_text()


def test_lang_command_switches_interface_to_english() -> None:
    app, console, _client = _make_app()

    app.handle_line("/lang en")
    output_after_switch = console.export_text()
    should_continue = app.handle_line("/help")

    assert should_continue is True
    assert "Interface language: en." in output_after_switch
    help_output = console.export_text()
    assert "show the command list" in help_output
    assert "показать список команд" not in help_output


def test_lang_command_rejects_unknown_language() -> None:
    app, console, _client = _make_app()

    should_continue = app.handle_line("/lang fr")

    assert should_continue is True
    output = console.export_text()
    assert "fr" in output


def test_run_status_labels_switch_to_english() -> None:
    app, console, client = _make_app()
    app.handle_line("/lang en")
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="in_progress", conclusion=None, head_branch="main",
    )
    client.list_jobs = lambda run_id: [
        JobSummary(id=201, run_id=run_id, name="run-python", status="queued", conclusion=None),
    ]

    app.handle_line("/run-status 1")

    output = console.export_text()
    assert "Jobs:" in output
    assert "queued" in output


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
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))

    exit_code = repl.run_repl(app, console)

    assert exit_code == 0
    assert history == ["/help", "/quit"]


def test_run_repl_passes_prompt_to_readline_input(monkeypatch) -> None:
    fake_readline = SimpleNamespace(parse_and_bind=lambda _value: None, add_history=lambda _line: None)
    monkeypatch.setattr(repl, "enable_line_editing", lambda: fake_readline)

    app, console, _client = _make_app()
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return "/quit"

    def fail_console_input(_prompt: str) -> str:
        raise AssertionError("readline input must receive the prompt directly")

    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(console, "input", fail_console_input)

    exit_code = repl.run_repl(app, console)

    assert exit_code == 0
    assert prompts == [repl.READLINE_PROMPT]


def test_readline_prompt_uses_plain_ansi_for_libedit() -> None:
    fake_readline = SimpleNamespace(__doc__="Importing this module enables command line editing using libedit readline.")

    prompt = repl.readline_prompt(fake_readline)

    assert prompt == repl.ANSI_PROMPT
    assert "\001" not in prompt
    assert "\002" not in prompt
    assert "\033[1;36m" in prompt


def test_run_repl_stops_current_command_on_command_interrupt(monkeypatch) -> None:
    monkeypatch.setattr(repl, "enable_line_editing", lambda: None)

    app, console, _client = _make_app()
    inputs = iter(["/workflows", "/quit"])
    monkeypatch.setattr(console, "input", lambda _prompt: next(inputs))

    original_handle_line = app.handle_line

    def interrupt_once(line: str) -> bool:
        if line == "/workflows":
            raise repl.CommandInterrupted
        return original_handle_line(line)

    app.handle_line = interrupt_once

    exit_code = repl.run_repl(app, console)

    assert exit_code == 0
    output = console.export_text()
    assert "Команда остановлена" in output


def test_command_interrupt_handler_is_restored(monkeypatch) -> None:
    if repl.COMMAND_INTERRUPT_SIGNAL is None:
        return

    handlers: list[tuple[int, object]] = []
    previous_handler = object()

    def fake_signal(signal_number: int, handler: object) -> object:
        handlers.append((signal_number, handler))
        return previous_handler

    monkeypatch.setattr(repl.signal, "signal", fake_signal)

    with repl.command_interrupts_enabled():
        assert handlers == [(repl.COMMAND_INTERRUPT_SIGNAL, repl._raise_command_interrupted)]

    assert handlers[-1] == (repl.COMMAND_INTERRUPT_SIGNAL, previous_handler)


# --- deferred dispatch tests ---

def _make_free_runs() -> list:
    return [
        WorkflowRunSummary(id=304, workflow_id=101, name="Build", status="completed", conclusion="success", head_branch="main"),
    ]


def _make_busy_runs() -> list:
    return [
        WorkflowRunSummary(id=301, workflow_id=101, name="Build", status="queued", conclusion=None, head_branch="main"),
        WorkflowRunSummary(id=302, workflow_id=101, name="Build", status="in_progress", conclusion=None, head_branch="main"),
        WorkflowRunSummary(id=303, workflow_id=102, name="Deploy", status="queued", conclusion=None, head_branch="main"),
    ]


def test_run_command_with_defer_idle_dispatches_immediately_when_free() -> None:
    app, console, client = _make_app()
    app.handle_line("/workflows")
    client.list_repository_runs = lambda limit=100: _make_free_runs()
    slept: list[float] = []
    app._sleep_fn = slept.append

    should_continue = app.handle_line("/run 1 ref=main defer=idle")

    assert should_continue is True
    assert client.dispatched == [("build.yml", "main", {})]
    assert slept == []
    output = console.export_text()
    assert "Раннеры свободны" in output
    assert "отправлен" in output


def test_run_command_with_defer_idle_polls_until_free() -> None:
    app, console, client = _make_app()
    app.handle_line("/workflows")
    responses = iter([_make_busy_runs(), _make_busy_runs(), _make_free_runs()])
    client.list_repository_runs = lambda limit=100: next(responses)
    slept: list[float] = []
    app._sleep_fn = slept.append

    should_continue = app.handle_line("/run 1 ref=main defer=idle poll=10")

    assert should_continue is True
    assert client.dispatched == [("build.yml", "main", {})]
    assert len(slept) == 2
    assert slept[0] == 10 * 60
    output = console.export_text()
    assert "Раннеры заняты" in output
    assert "Раннеры свободны" in output
    assert "отправлен" in output


def test_run_command_with_defer_idle_excludes_defer_from_inputs() -> None:
    app, _console, client = _make_app()
    app.handle_line("/workflows")
    client.list_repository_runs = lambda limit=100: _make_free_runs()
    app._sleep_fn = lambda _s: None

    app.handle_line("/run 1 ref=main defer=idle dry_run=true")

    assert client.dispatched == [("build.yml", "main", {"dry_run": "true"})]


def test_run_command_with_defer_time_waits_until_scheduled() -> None:
    app, console, client = _make_app()
    app.handle_line("/workflows")
    # now=14:00, target=23:00 → remaining=9h; after one sleep now passes target
    times = iter([
        datetime.datetime(2026, 5, 28, 14, 0, 0),  # _parse_defer_time call
        datetime.datetime(2026, 5, 28, 14, 0, 0),  # first loop check
        datetime.datetime(2026, 5, 28, 23, 1, 0),  # second loop check → exit
    ])
    app._now_fn = lambda: next(times)
    slept: list[float] = []
    app._sleep_fn = slept.append

    should_continue = app.handle_line("/run 1 ref=main defer=23:00")

    assert should_continue is True
    assert client.dispatched == [("build.yml", "main", {})]
    assert len(slept) == 1
    output = console.export_text()
    assert "23:00" in output
    assert "отправлен" in output


def test_run_command_with_defer_time_and_idle_waits_then_polls() -> None:
    app, console, client = _make_app()
    app.handle_line("/workflows")
    times = iter([
        datetime.datetime(2026, 5, 28, 22, 0, 0),  # _parse_defer_time
        datetime.datetime(2026, 5, 28, 23, 1, 0),  # loop check → already past
    ])
    app._now_fn = lambda: next(times)
    slept: list[float] = []
    app._sleep_fn = slept.append
    client.list_repository_runs = lambda limit=100: _make_free_runs()

    should_continue = app.handle_line("/run 1 ref=main defer=23:00,idle")

    assert should_continue is True
    assert client.dispatched == [("build.yml", "main", {})]
    output = console.export_text()
    assert "23:00" in output
    assert "Раннеры свободны" in output


def test_run_command_with_unknown_defer_raises_error() -> None:
    app, console, client = _make_app()
    app.handle_line("/workflows")

    should_continue = app.handle_line("/run 1 ref=main defer=tomorrow")

    assert should_continue is True
    assert client.dispatched == []
    output = console.export_text()
    assert "Не удалось распознать" in output


# --- _parse_defer_time unit tests ---

def _fixed_now(hour: int, minute: int = 0) -> Callable[[], datetime.datetime]:
    dt = datetime.datetime(2026, 5, 28, hour, minute, 0)
    return lambda: dt


def test_parse_defer_time_24h_format_same_day() -> None:
    result = _parse_defer_time("23:00", lambda: datetime.datetime(2026, 5, 28, 14, 0))
    assert result == datetime.datetime(2026, 5, 28, 23, 0)


def test_parse_defer_time_24h_format_next_day_when_past() -> None:
    result = _parse_defer_time("09:00", lambda: datetime.datetime(2026, 5, 28, 14, 0))
    assert result == datetime.datetime(2026, 5, 29, 9, 0)


def test_parse_defer_time_ampm_11pm() -> None:
    result = _parse_defer_time("11pm", lambda: datetime.datetime(2026, 5, 28, 14, 0))
    assert result == datetime.datetime(2026, 5, 28, 23, 0)


def test_parse_defer_time_ampm_with_minutes() -> None:
    result = _parse_defer_time("11:30pm", lambda: datetime.datetime(2026, 5, 28, 14, 0))
    assert result == datetime.datetime(2026, 5, 28, 23, 30)


def test_parse_defer_time_ampm_noon() -> None:
    result = _parse_defer_time("12pm", lambda: datetime.datetime(2026, 5, 28, 10, 0))
    assert result == datetime.datetime(2026, 5, 28, 12, 0)


def test_parse_defer_time_ampm_midnight() -> None:
    result = _parse_defer_time("12am", lambda: datetime.datetime(2026, 5, 28, 10, 0))
    assert result == datetime.datetime(2026, 5, 29, 0, 0)


def test_parse_defer_time_returns_none_for_garbage() -> None:
    result = _parse_defer_time("tomorrow", lambda: datetime.datetime(2026, 5, 28, 10, 0))
    assert result is None


# --- /diagnose tests ---

def _make_app_with_ai(ai_fn: Callable[[str], str]) -> tuple[App, Console, FakeGitHubClient]:
    """Make an app where _run_ai_subprocess is replaced by a callable for testing."""
    app, console, client = _make_app()
    app._run_ai_subprocess = ai_fn  # type: ignore[method-assign]
    return app, console, client


def _failed_job() -> JobSummary:
    return JobSummary(
        id=201, run_id=301, name="test", status="completed", conclusion="failure",
        steps=[StepSummary(number=1, name="Run tests", status="completed", conclusion="failure")],
    )


def test_diagnose_command_saves_report_for_failed_run(tmp_path: Path) -> None:
    app, console, client = _make_app_with_ai(lambda _prompt: "**test**: Причина: тест упал.")
    app.config = dataclasses.replace(
        app.config, diagnose_output_dir=str(tmp_path), max_log_lines_per_job=50
    )
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="completed",
        conclusion="failure", head_branch="main",
    )
    client.list_jobs = lambda run_id: [_failed_job()]

    should_continue = app.handle_line("/diagnose 1")

    assert should_continue is True
    reports = list(tmp_path.glob("301-Build-*.md"))
    assert len(reports) == 1
    content = reports[0].read_text()
    assert "Анализ падения" in content
    assert "Build #301" in content
    assert "тест упал" in content
    output = console.export_text()
    assert "Анализ сохранён" in output


def test_diagnose_command_reports_no_failed_jobs() -> None:
    app, console, _client = _make_app_with_ai(lambda _p: "ok")
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="completed",
        conclusion="success", head_branch="main",
    )
    app.session.job_index[1] = JobSummary(
        id=201, run_id=301, name="test", status="completed", conclusion="success", steps=[],
    )

    should_continue = app.handle_line("/diagnose 1")

    assert should_continue is True
    output = console.export_text()
    assert "не найдено" in output


def test_diagnose_command_includes_failed_job_logs_in_prompt(tmp_path: Path) -> None:
    received_prompts: list[str] = []

    def capture(prompt: str) -> str:
        received_prompts.append(prompt)
        return "анализ"

    app, _console, client = _make_app_with_ai(capture)
    app.config = dataclasses.replace(app.config, diagnose_output_dir=str(tmp_path))
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="completed",
        conclusion="failure", head_branch="develop",
    )
    client.list_jobs = lambda run_id: [_failed_job()]

    app.handle_line("/diagnose 1")

    assert len(received_prompts) == 1
    prompt = received_prompts[0]
    assert "Build" in prompt
    assert "develop" in prompt
    assert "#301" in prompt
    assert "test" in prompt        # job name
    assert "Run tests" in prompt   # failed step name
    assert "cloning repo" in prompt  # from FakeGitHubClient log fixture


def test_diagnose_command_propagates_ai_tool_not_found_as_error(tmp_path: Path) -> None:
    import subprocess as sp

    def raise_not_found(_prompt: str) -> str:
        raise ValueError("AI-инструмент не найден: 'nonexistent-ai'")

    app, console, _client = _make_app_with_ai(raise_not_found)
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="completed",
        conclusion="failure", head_branch="main",
    )
    app.session.job_index[1] = JobSummary(
        id=201, run_id=301, name="test", status="completed", conclusion="failure", steps=[],
    )

    should_continue = app.handle_line("/diagnose 1")

    assert should_continue is True
    output = console.export_text()
    assert "не найден" in output


def test_follow_command_auto_diagnoses_on_failure(tmp_path: Path) -> None:
    app, console, client = _make_app_with_ai(lambda _p: "причина: упало")
    app.config = dataclasses.replace(
        app.config, diagnose_output_dir=str(tmp_path), poll_interval=0
    )
    app.session.run_index[1] = WorkflowRunSummary(
        id=301, workflow_id=101, name="Build", status="in_progress",
        conclusion=None, head_branch="main",
    )
    # client.get_run returns completed+failure
    from gh_actions_cli.models import WorkflowRunSummary as WRS
    client.get_run = lambda run_id: WRS(
        id=run_id, workflow_id=101, name="Build",
        status="completed", conclusion="failure", head_branch="main",
    )
    client.list_jobs = lambda run_id: [_failed_job()]

    should_continue = app.handle_line("/follow 1 diagnose=true")

    assert should_continue is True
    reports = list(tmp_path.glob("301-Build-*.md"))
    assert len(reports) == 1
    output = console.export_text()
    assert "Анализ сохранён" in output
