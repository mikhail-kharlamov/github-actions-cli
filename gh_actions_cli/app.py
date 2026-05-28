from __future__ import annotations

import datetime
import os
import re
import select
import subprocess
import time
from pathlib import Path
from typing import Callable
from typing import Protocol

from rich.console import Console

from gh_actions_cli.artifacts import extract_artifact_zip
from gh_actions_cli.commands import CommandError, parse_command
from gh_actions_cli.config import AppConfig
from gh_actions_cli.github_api import GitHubAPIError
from gh_actions_cli.logs import extract_job_logs, extract_step_log
from gh_actions_cli.models import (
    ArtifactSummary,
    JobSummary,
    RunInvocation,
    RunnerLoadSummary,
    SessionState,
    WorkflowLoadSummary,
    WorkflowRunSummary,
    WorkflowSummary,
)
from gh_actions_cli.renderer import (
    render_artifacts,
    render_dispatch_inputs,
    render_error,
    render_jobs,
    render_message,
    render_runner_load,
    render_runs,
    render_steps,
    render_workflows,
)
from gh_actions_cli.workflow_parser import WorkflowParseError, extract_workflow_dispatch_inputs


def _parse_defer_time(time_str: str, now_fn: Callable[[], datetime.datetime]) -> datetime.datetime | None:
    """Parse '11pm', '11:30pm', '23:00' → next occurrence of that wall-clock time."""
    now = now_fn()

    m = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt <= now:
            dt += datetime.timedelta(days=1)
        return dt

    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$", time_str, re.IGNORECASE)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3).lower()
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt <= now:
            dt += datetime.timedelta(days=1)
        return dt

    return None


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and carriage returns produced by a PTY."""
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\r", "", text)


def _tail_lines(text: str, n: int) -> str:
    """Return the last n lines of text."""
    lines = text.splitlines()
    return "\n".join(lines[-n:]) if len(lines) > n else text


HELP_TEXT = """\
/help                        показать список команд
/workflows                   получить список workflow
/workflow <workflow>         показать детали workflow
/dispatch-inputs <workflow>  показать workflow_dispatch inputs
/run <workflow> [ref=...] [defer=idle|TIME|TIME,idle] [poll=10] [key=value ...]
  defer=idle          — ждать, пока раннеры свободны, затем запустить
  defer=11pm          — запустить ровно в указанное время (11pm / 23:00 / 11:30pm)
  defer=11pm,idle     — начать проверку раннеров с указанного времени
  poll=N              — интервал проверки в минутах (по умолчанию 10)
/run-form <workflow>         интерактивный запуск workflow
/runs <workflow> [limit=10]  последние run-ы workflow
/run-status <run-id>         статус конкретного run
/follow <run-id> [diagnose=true]  следить за статусом run; при падении авто-запускает /diagnose
/jobs <run-id>               jobs конкретного run
/steps <job-id>              steps конкретного job
/logs <job-id>               лог job целиком
/step-log <job-id> <step>    лог одного шага
/follow-logs <job-id>        обновлять лог job до завершения
/artifacts <run-id>          список артефактов run
/download-artifacts <run-id> <artifact...> [dir=...]  скачать выбранные артефакты
/cancel-run <run-id>         остановить run
/run-args <run-id>           показать аргументы запуска run
/runner-load [limit=100]     показать текущую загрузку раннеров по репозиторию
/diagnose <run-id>           AI-анализ упавших джобов, сохраняет отчёт в файл
/clear                       очистить экран
/quit                        выйти

Переменные окружения для диагностики:
  GH_ACTIONS_AI_COMMAND      команда AI-инструмента (по умолч. codex)
  GH_ACTIONS_AI_COMMAND_ARGS аргументы перед промптом (по умолч. пусто; для claude: -p)
  GH_ACTIONS_DIAGNOSE_DIR    куда сохранять отчёты (по умолч. ~/.gh-actions-diagnoses)
  GH_ACTIONS_MAX_LOG_LINES   строк лога на джобу (по умолч. 150)
  GH_ACTIONS_AI_TIMEOUT      таймаут в секундах (по умолч. 120)

Горячие клавиши:
Ctrl+\\                      остановить текущую команду на macOS/Linux
Ctrl+C                       выйти из CLI
"""


class GitHubClientProtocol(Protocol):
    def list_workflows(self) -> list[WorkflowSummary]: ...
    def get_workflow(self, workflow_id: str | int) -> WorkflowSummary: ...
    def get_workflow_runs(self, workflow_id: str | int, limit: int = 10) -> list[WorkflowRunSummary]: ...
    def list_repository_runs(self, limit: int = 100) -> list[WorkflowRunSummary]: ...
    def get_run(self, run_id: int) -> WorkflowRunSummary: ...
    def get_run_payload(self, run_id: int) -> dict: ...
    def list_jobs(self, run_id: int) -> list[JobSummary]: ...
    def list_run_artifacts(self, run_id: int) -> list[ArtifactSummary]: ...
    def dispatch_workflow(self, workflow_id_or_file: str | int, ref: str, inputs: dict[str, str]) -> None: ...
    def download_run_logs(self, run_id: int) -> bytes: ...
    def download_artifact_zip(self, artifact_id: int) -> bytes: ...
    def cancel_run(self, run_id: int) -> None: ...
    def get_workflow_file_content(self, path: str, ref: str) -> str: ...
    def get_repository(self) -> dict: ...


class App:
    def __init__(self, config: AppConfig, console: Console, github_client: GitHubClientProtocol) -> None:
        self.config = config
        self.console = console
        self.github_client = github_client
        self.session = SessionState()
        self._sleep_fn: Callable[[float], None] = time.sleep
        self._now_fn: Callable[[], datetime.datetime] = datetime.datetime.now

    def handle_line(self, raw: str) -> bool:
        try:
            command = parse_command(raw)
            return self._dispatch(command.name, command.args, command.options)
        except (CommandError, GitHubAPIError, WorkflowParseError, ValueError) as error:
            render_error(self.console, str(error))
            return True

    def _dispatch(self, name: str, args: list[str], options: dict[str, str]) -> bool:
        if name == "help":
            render_message(self.console, HELP_TEXT)
        elif name == "quit":
            return False
        elif name == "clear":
            self.console.clear()
        elif name == "workflows":
            self._handle_workflows()
        elif name == "workflow":
            self._handle_workflow(args)
        elif name == "dispatch-inputs":
            self._handle_dispatch_inputs(args)
        elif name == "run":
            self._handle_run(args, options)
        elif name == "run-form":
            self._handle_run_form(args)
        elif name == "runs":
            self._handle_runs(args, options)
        elif name == "run-status":
            self._handle_run_status(args)
        elif name == "follow":
            self._handle_follow(args, options)
        elif name == "jobs":
            self._handle_jobs(args)
        elif name == "steps":
            self._handle_steps(args)
        elif name == "logs":
            self._handle_logs(args, options)
        elif name == "step-log":
            self._handle_step_log(args, options)
        elif name == "follow-logs":
            self._handle_follow_logs(args)
        elif name == "artifacts":
            self._handle_artifacts(args)
        elif name == "download-artifacts":
            self._handle_download_artifacts(args, options)
        elif name == "cancel-run":
            self._handle_cancel_run(args)
        elif name == "run-args":
            self._handle_run_args(args)
        elif name == "runner-load":
            self._handle_runner_load(options)
        elif name == "diagnose":
            self._handle_diagnose(args)
        return True

    def _handle_workflows(self) -> None:
        workflows = self.github_client.list_workflows()
        self.session.workflow_index = {index: item for index, item in enumerate(workflows, start=1)}
        render_workflows(self.console, workflows)

    def _handle_workflow(self, args: list[str]) -> None:
        workflow = self._resolve_workflow(args)
        render_message(
            self.console,
            f"Workflow: {workflow.name}\nID: {workflow.id}\nFile: {workflow.path}\nState: {workflow.state}",
        )

    def _handle_dispatch_inputs(self, args: list[str]) -> None:
        workflow = self._resolve_workflow(args)
        inputs = self._load_workflow_inputs(workflow)
        if not inputs:
            render_message(self.console, "У workflow нет workflow_dispatch inputs.", style="yellow")
            return
        render_dispatch_inputs(self.console, inputs)

    def _handle_run(self, args: list[str], options: dict[str, str]) -> None:
        workflow = self._resolve_workflow(args)
        ref = options.get("ref") or self._default_ref()
        inputs = {key: value for key, value in options.items() if key not in ("ref", "defer", "poll")}
        defer = options.get("defer")
        if defer:
            poll_minutes = int(options.get("poll", "10"))
            self._deferred_dispatch(workflow, ref, inputs, defer, poll_minutes)
            return
        self._do_dispatch(workflow, ref, inputs)

    def _do_dispatch(self, workflow: WorkflowSummary, ref: str, inputs: dict[str, str]) -> None:
        self.github_client.dispatch_workflow(self._workflow_dispatch_target(workflow), ref, inputs)
        self.session.recent_invocations.insert(
            0,
            RunInvocation(
                run_id=self._latest_run_id_for_workflow(workflow.id),
                workflow_identifier=str(workflow.id),
                workflow_name=workflow.name,
                ref=ref,
                inputs=inputs,
            ),
        )
        render_message(self.console, f"Workflow {workflow.name} отправлен с ref={ref}.", style="green")

    def _deferred_dispatch(
        self,
        workflow: WorkflowSummary,
        ref: str,
        inputs: dict[str, str],
        defer: str,
        poll_minutes: int,
    ) -> None:
        parts = [p.strip() for p in defer.split(",")]
        schedule_time: datetime.datetime | None = None
        wait_for_idle = False

        for part in parts:
            if part.lower() == "idle":
                wait_for_idle = True
            else:
                schedule_time = _parse_defer_time(part, self._now_fn)
                if schedule_time is None:
                    raise ValueError(
                        f"Не удалось распознать время: {part!r}. "
                        "Используйте формат 11pm, 11:30pm или 23:00."
                    )

        if not schedule_time and not wait_for_idle:
            raise ValueError("Укажите defer=idle, defer=11pm или defer=11pm,idle.")

        if schedule_time:
            render_message(
                self.console,
                f"Отложенный запуск: ожидание до {schedule_time.strftime('%H:%M')} "
                f"(Ctrl+\\ для отмены)...",
                style="yellow",
            )
            while True:
                remaining = (schedule_time - self._now_fn()).total_seconds()
                if remaining <= 0:
                    break
                self._sleep_fn(min(remaining, 30))

        if wait_for_idle:
            render_message(
                self.console,
                f"Ожидание свободных раннеров (интервал: {poll_minutes} мин)...",
                style="yellow",
            )
            while True:
                load = self._compute_runner_load()
                if load.pressure == "Свободно":
                    render_message(self.console, "Раннеры свободны — отправляю.", style="green")
                    break
                render_message(
                    self.console,
                    f"Раннеры заняты (queued: {load.queued}, in_progress: {load.in_progress}), "
                    f"следующая проверка через {poll_minutes} мин...",
                    style="yellow",
                )
                self._sleep_fn(poll_minutes * 60)

        self._do_dispatch(workflow, ref, inputs)

    def _handle_run_form(self, args: list[str]) -> None:
        workflow = self._resolve_workflow(args)
        inputs = self._load_workflow_inputs(workflow)
        if not inputs:
            raise ValueError("У workflow нет workflow_dispatch inputs для интерактивного запуска.")
        values: dict[str, str] = {}
        ref = self.console.input("ref (Enter для default branch): ").strip() or self._default_ref()
        for item in inputs:
            suffix = f" [{item.default}]" if item.default is not None else ""
            prompt = f"{item.name} ({item.type}){suffix}: "
            value = self.console.input(prompt).strip()
            if not value and item.default is not None:
                value = str(item.default)
            if not value and item.required:
                raise ValueError(f"Поле {item.name} обязательно.")
            if value:
                values[item.name] = self._normalize_input_value(item.type, value, item.options)
        self.github_client.dispatch_workflow(self._workflow_dispatch_target(workflow), ref, values)
        self.session.recent_invocations.insert(
            0,
            RunInvocation(
                run_id=self._latest_run_id_for_workflow(workflow.id),
                workflow_identifier=str(workflow.id),
                workflow_name=workflow.name,
                ref=ref,
                inputs=values,
            ),
        )
        render_message(self.console, f"Workflow {workflow.name} отправлен.", style="green")

    def _handle_runs(self, args: list[str], options: dict[str, str]) -> None:
        workflow = self._resolve_workflow(args)
        limit = int(options.get("limit", "10"))
        runs = self.github_client.get_workflow_runs(workflow.id, limit=limit)
        self.session.run_index = {index: item for index, item in enumerate(runs, start=1)}
        render_runs(self.console, runs)

    def _handle_run_status(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        render_message(
            self.console,
            f"Run {run.id}\nName: {run.name}\nBranch: {run.head_branch or '-'}\nStatus: {run.status}\nConclusion: {run.conclusion or '-'}",
        )

    def _handle_follow(self, args: list[str], options: dict[str, str] | None = None) -> None:
        run = self._resolve_run(args)
        diagnose = self._option_enabled(options or {}, "diagnose")
        while True:
            current = self.github_client.get_run(run.id)
            render_message(
                self.console,
                f"Run {current.id}: {current.conclusion or current.status}",
                style="yellow" if current.status != "completed" else "green",
            )
            if current.status == "completed":
                if diagnose and current.conclusion == "failure":
                    self._handle_diagnose([str(run.id)])
                break
            if self.config.poll_interval:
                time.sleep(self.config.poll_interval)

    def _handle_jobs(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        jobs = self.github_client.list_jobs(run.id)
        self.session.job_index = {index: item for index, item in enumerate(jobs, start=1)}
        render_jobs(self.console, jobs)

    def _handle_steps(self, args: list[str]) -> None:
        job = self._resolve_job(args)
        if not job.steps:
            jobs = self.github_client.list_jobs(job.run_id)
            fresh_job = next((item for item in jobs if item.id == job.id), None)
            if fresh_job is None:
                raise ValueError(f"Job {job.id} не найден.")
            job = fresh_job
            self.session.job_index = {
                index: item if item.id != job.id else job
                for index, item in self.session.job_index.items()
            }
        render_steps(self.console, job.steps)

    def _handle_logs(self, args: list[str], options: dict[str, str]) -> None:
        job = self._resolve_job(args)
        job_logs = self._load_job_logs(job.run_id)
        selected = job_logs.get(job.id)
        if selected is None:
            raise ValueError(f"Для job {job.id} не удалось найти лог.")
        if not self._option_enabled(options, "no_print"):
            self.console.print(selected.content)
        self._write_text_output(selected.content, options.get("file"))

    def _handle_step_log(self, args: list[str], options: dict[str, str]) -> None:
        if len(args) < 2:
            raise ValueError("Нужно указать job и step.")
        job = self._resolve_job(args[:1])
        if not job.steps:
            jobs = self.github_client.list_jobs(job.run_id)
            job = next((item for item in jobs if item.id == job.id), job)
        job_logs = self._load_job_logs(job.run_id)
        selected = job_logs.get(job.id)
        if selected is None:
            raise ValueError(f"Для job {job.id} не удалось найти лог.")
        result = extract_step_log(selected.content, job, args[1])
        if result.fallback_used:
            render_message(
                self.console,
                f"Не удалось точно выделить шаг {result.step_name}, показываю лог job целиком.",
                style="yellow",
            )
        if not self._option_enabled(options, "no_print"):
            self.console.print(result.content)
        self._write_text_output(result.content, options.get("file"))

    def _handle_follow_logs(self, args: list[str]) -> None:
        job = self._resolve_job(args)
        previous = ""
        while True:
            current_run = self.github_client.get_run(job.run_id)
            job_logs = self._load_job_logs(job.run_id)
            selected = job_logs.get(job.id)
            if selected and selected.content != previous:
                delta = selected.content[len(previous) :] if previous and selected.content.startswith(previous) else selected.content
                self.console.print(delta)
                previous = selected.content
            if current_run.status == "completed":
                break
            if self.config.poll_interval:
                time.sleep(self.config.poll_interval)

    def _handle_artifacts(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        artifacts = self.github_client.list_run_artifacts(run.id)
        self.session.artifact_index = {index: item for index, item in enumerate(artifacts, start=1)}
        render_artifacts(self.console, artifacts)

    def _handle_download_artifacts(self, args: list[str], options: dict[str, str]) -> None:
        if len(args) < 2:
            raise ValueError("Нужно указать run и хотя бы один артефакт или all.")
        run = self._resolve_run(args[:1])
        artifacts = self.github_client.list_run_artifacts(run.id)
        self.session.artifact_index = {index: item for index, item in enumerate(artifacts, start=1)}
        selected_artifacts = self._resolve_artifacts(args[1:], artifacts)
        base_dir = Path(options.get("dir", f"artifacts/run-{run.id}")).expanduser()
        downloaded: list[str] = []
        for artifact in selected_artifacts:
            archive = self.github_client.download_artifact_zip(artifact.id)
            destination = base_dir / artifact.name
            extract_artifact_zip(archive, destination)
            downloaded.append(str(destination))
        render_message(
            self.console,
            "Скачано:\n" + "\n".join(downloaded),
            style="green",
        )

    def _handle_cancel_run(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        self.github_client.cancel_run(run.id)
        render_message(self.console, f"Run {run.id} отправлен на остановку.", style="yellow")

    def _handle_run_args(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        invocation = next((item for item in self.session.recent_invocations if item.run_id == run.id), None)
        if invocation is not None:
            lines = [
                f"Run: {run.id}",
                f"Source: {invocation.source}",
                f"Workflow: {invocation.workflow_name}",
                f"ref: {invocation.ref}",
                "inputs:",
            ]
            if invocation.inputs:
                lines.extend(f"  {key}={value}" for key, value in invocation.inputs.items())
            else:
                lines.append("  <none>")
            render_message(self.console, "\n".join(lines), style="green")
            return

        payload = self.github_client.get_run_payload(run.id)
        display_title = payload.get("display_title") or payload.get("name") or str(run.id)
        path = payload.get("path") or payload.get("workflow_url") or "-"
        event = payload.get("event", "-")
        head_sha = payload.get("head_sha", "-")
        lines = [
            f"Run: {run.id}",
            "Source: github-best-effort",
            f"Title: {display_title}",
            f"Event: {event}",
            f"Branch: {payload.get('head_branch') or '-'}",
            f"Commit: {head_sha}",
            f"Workflow ref: {path}",
            "inputs:",
            "  GitHub API не возвращает workflow_dispatch inputs для чужих run в явном виде.",
        ]
        render_message(self.console, "\n".join(lines), style="yellow")

    def _handle_diagnose(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        jobs = self.github_client.list_jobs(run.id)
        failed_jobs = [j for j in jobs if j.conclusion in {"failure", "timed_out"}]
        if not failed_jobs:
            render_message(self.console, f"Run {run.id}: упавших джобов не найдено.", style="yellow")
            return

        render_message(
            self.console,
            f"Упавших джобов: {len(failed_jobs)}. Скачиваю логи...",
            style="yellow",
        )
        job_logs = self._load_job_logs(run.id)

        prompt = self._build_diagnose_prompt(run, failed_jobs, job_logs)

        render_message(
            self.console,
            f"Запускаю AI-анализ [{self.config.ai_command}]...",
            style="yellow",
        )
        analysis = self._run_ai_subprocess(prompt)

        report_path = self._save_diagnose_report(run, analysis)
        render_message(
            self.console,
            f"Анализ сохранён: {report_path}",
            style="green",
        )

    def _build_diagnose_prompt(
        self,
        run: WorkflowRunSummary,
        failed_jobs: list[JobSummary],
        job_logs: dict,
    ) -> str:
        lines: list[str] = [
            "Ты — инженер DevOps. Ниже логи упавших джобов из GitHub Actions.",
            "Проанализируй причины каждого падения и составь краткий отчёт строго на русском языке.",
            "",
            f"Воркфлоу: {run.name}",
            f"Ветка: {run.head_branch or '-'}",
            f"Ран: #{run.id}",
            "",
        ]
        for job in failed_jobs:
            log_entry = job_logs.get(job.id)
            raw_log = log_entry.content if log_entry else "(лог недоступен)"
            log_tail = _tail_lines(raw_log, self.config.max_log_lines_per_job)
            failed_step = next(
                (s.name for s in reversed(job.steps) if s.conclusion in {"failure", "timed_out"}),
                "-",
            )
            lines += [
                f"== Джоба: {job.name} ==",
                f"Статус: {job.conclusion}",
                f"Упавший шаг: {failed_step}",
                f"--- Лог (последние {self.config.max_log_lines_per_job} строк) ---",
                log_tail,
                "---",
                "",
            ]
        lines += [
            "Формат ответа — для каждой джобы:",
            "**<название джобы>**",
            "- Причина: <краткое объяснение>",
            "- Точка отказа: <файл/команда/шаг>",
            "- Рекомендация: <что исправить>",
        ]
        return "\n".join(lines)

    def _run_ai_subprocess(self, prompt: str) -> str:
        args = [a for a in self.config.ai_command_args.split() if a]
        cmd = [self.config.ai_command, *args, prompt]
        try:
            import pty  # Unix-only; graceful fallback below if unavailable
            return self._run_ai_pty(cmd)
        except ImportError:
            return self._run_ai_plain(cmd)

    def _run_ai_pty(self, cmd: list[str]) -> str:
        """Run the AI tool through a pseudo-TTY so isatty(stdout) returns True."""
        import pty
        master_fd, slave_fd = pty.openpty()
        chunks: list[bytes] = []
        proc: subprocess.Popen | None = None
        try:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    close_fds=True,
                )
            except FileNotFoundError:
                raise ValueError(
                    f"AI-инструмент не найден: {self.config.ai_command!r}. "
                    "Проверьте GH_ACTIONS_AI_COMMAND."
                )
            finally:
                os.close(slave_fd)  # parent does not need the slave end

            deadline = time.monotonic() + self.config.ai_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    raise ValueError(
                        f"AI-инструмент не ответил за {self.config.ai_timeout} сек. "
                        "Увеличьте GH_ACTIONS_AI_TIMEOUT."
                    )
                ready, _, _ = select.select([master_fd], [], [], min(remaining, 1.0))
                if ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                        if chunk:
                            chunks.append(chunk)
                    except OSError:
                        break  # slave closed — process exited
                if proc.poll() is not None:
                    # Drain any last bytes still in the buffer
                    try:
                        while select.select([master_fd], [], [], 0)[0]:
                            chunk = os.read(master_fd, 4096)
                            if chunk:
                                chunks.append(chunk)
                            else:
                                break
                    except OSError:
                        pass
                    break
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass

        raw = b"".join(chunks).decode("utf-8", errors="replace")
        output = _strip_ansi(raw).strip()

        if proc is not None and proc.returncode != 0:
            detail = output[:200] or "(нет вывода)"
            raise ValueError(f"AI-инструмент завершился с ошибкой: {detail}")
        return output

    def _run_ai_plain(self, cmd: list[str]) -> str:
        """Fallback for systems without pty (e.g. Windows)."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.config.ai_timeout
            )
        except FileNotFoundError:
            raise ValueError(
                f"AI-инструмент не найден: {self.config.ai_command!r}. "
                "Проверьте GH_ACTIONS_AI_COMMAND."
            )
        except subprocess.TimeoutExpired:
            raise ValueError(
                f"AI-инструмент не ответил за {self.config.ai_timeout} сек. "
                "Увеличьте GH_ACTIONS_AI_TIMEOUT."
            )
        if result.returncode != 0:
            detail = result.stderr.strip()[:200] or "(нет вывода)"
            raise ValueError(f"AI-инструмент завершился с ошибкой: {detail}")
        return result.stdout.strip()

    def _save_diagnose_report(self, run: WorkflowRunSummary, analysis: str) -> Path:
        output_dir = Path(self.config.diagnose_output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.-]", "_", run.name or "workflow")
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{run.id}-{safe_name}-{timestamp}.md"
        report_path = output_dir / filename
        header = "\n".join([
            f"# Анализ падения: {run.name} #{run.id}",
            f"Дата: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Ветка: {run.head_branch or '-'}",
            "",
            "---",
            "",
        ])
        report_path.write_text(header + analysis, encoding="utf-8")
        return report_path

    def _handle_runner_load(self, options: dict[str, str]) -> None:
        limit = int(options.get("limit", "100"))
        summary = self._compute_runner_load(limit=limit)
        render_runner_load(self.console, summary)

    def _compute_runner_load(self, limit: int = 100) -> RunnerLoadSummary:
        runs = self.github_client.list_repository_runs(limit=limit)
        active_runs = [run for run in runs if run.status in {"queued", "in_progress", "pending", "waiting"}]
        queued = sum(1 for run in active_runs if run.status == "queued")
        in_progress = sum(1 for run in active_runs if run.status == "in_progress")
        workflows: dict[int | None, WorkflowLoadSummary] = {}
        for run in active_runs:
            item = workflows.setdefault(
                run.workflow_id,
                WorkflowLoadSummary(
                    workflow_id=run.workflow_id,
                    workflow_name=run.name,
                ),
            )
            if run.status == "queued":
                item.queued += 1
            elif run.status == "in_progress":
                item.in_progress += 1
        return RunnerLoadSummary(
            queued=queued,
            in_progress=in_progress,
            total_active=queued + in_progress,
            pressure=self._runner_pressure(queued=queued, in_progress=in_progress),
            workflows=sorted(
                workflows.values(),
                key=lambda item: (item.queued + item.in_progress, item.queued, item.workflow_name),
                reverse=True,
            ),
        )

    def _resolve_workflow(self, args: list[str]) -> WorkflowSummary:
        if not args:
            raise ValueError("Нужно указать workflow.")
        token = args[0]
        if token.isdigit() and int(token) in self.session.workflow_index:
            return self.session.workflow_index[int(token)]
        if token.isdigit():
            return self.github_client.get_workflow(int(token))
        for workflow in self.session.workflow_index.values():
            if Path(workflow.path).name == token:
                return workflow
        workflows = self.github_client.list_workflows()
        for workflow in workflows:
            if Path(workflow.path).name == token:
                return workflow
        raise ValueError(f"Workflow {token} не найден.")

    def _resolve_run(self, args: list[str]) -> WorkflowRunSummary:
        if not args:
            raise ValueError("Нужно указать run.")
        token = args[0]
        if token.isdigit() and int(token) in self.session.run_index:
            return self.session.run_index[int(token)]
        if token.isdigit():
            return self.github_client.get_run(int(token))
        raise ValueError("Run должен быть numeric id или индексом из последнего списка.")

    def _resolve_job(self, args: list[str]) -> JobSummary:
        if not args:
            raise ValueError("Нужно указать job.")
        token = args[0]
        if token.isdigit() and int(token) in self.session.job_index:
            return self.session.job_index[int(token)]
        if token.isdigit():
            job_id = int(token)
            for job in self.session.job_index.values():
                if job.id == job_id:
                    return job
        raise ValueError("Job должен быть индексом из последнего списка /jobs.")

    def _resolve_artifacts(self, selectors: list[str], artifacts: list[ArtifactSummary]) -> list[ArtifactSummary]:
        if selectors == ["all"]:
            return artifacts
        by_id = {artifact.id: artifact for artifact in artifacts}
        by_name = {artifact.name: artifact for artifact in artifacts}
        resolved: list[ArtifactSummary] = []
        for selector in selectors:
            if selector.isdigit() and int(selector) in self.session.artifact_index:
                resolved.append(self.session.artifact_index[int(selector)])
                continue
            if selector.isdigit() and int(selector) in by_id:
                resolved.append(by_id[int(selector)])
                continue
            if selector in by_name:
                resolved.append(by_name[selector])
                continue
            raise ValueError(f"Артефакт {selector} не найден.")
        return resolved

    def _load_workflow_inputs(self, workflow: WorkflowSummary):
        yaml_text = self.github_client.get_workflow_file_content(workflow.path, self._default_ref())
        return extract_workflow_dispatch_inputs(yaml_text)

    def _latest_run_id_for_workflow(self, workflow_id: int) -> int | None:
        runs = self.github_client.get_workflow_runs(workflow_id, limit=1)
        return runs[0].id if runs else None

    def _write_text_output(self, content: str, target_file: str | None) -> None:
        if not target_file:
            return
        path = Path(target_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        render_message(self.console, f"Лог сохранен в {path}", style="green")

    @staticmethod
    def _option_enabled(options: dict[str, str], key: str) -> bool:
        value = options.get(key)
        if value is None:
            return False
        return value.lower() in {"1", "true", "yes", "on"}

    def _default_ref(self) -> str:
        if self.config.default_branch:
            return self.config.default_branch
        repository = self.github_client.get_repository()
        return str(repository.get("default_branch") or "main")

    def _workflow_dispatch_target(self, workflow: WorkflowSummary) -> str:
        return Path(workflow.path).name

    def _load_job_logs(self, run_id: int):
        jobs = self.github_client.list_jobs(run_id)
        for index, job in list(self.session.job_index.items()):
            for fresh_job in jobs:
                if fresh_job.id == job.id:
                    self.session.job_index[index] = fresh_job
        archive = self.github_client.download_run_logs(run_id)
        return extract_job_logs(archive, jobs)

    @staticmethod
    def _runner_pressure(queued: int, in_progress: int) -> str:
        if queued >= 2 or queued + in_progress >= 4:
            return "Перегружено"
        if queued >= 1 or in_progress >= 2:
            return "Умеренно"
        return "Свободно"

    @staticmethod
    def _normalize_input_value(input_type: str, value: str, options: list[str]) -> str:
        if input_type == "boolean":
            normalized = value.lower()
            if normalized not in {"true", "false"}:
                raise ValueError("Boolean input должен быть true или false.")
            return normalized
        if input_type == "number":
            float(value)
            return value
        if input_type == "choice" and options and value not in options:
            raise ValueError(f"Допустимые значения: {', '.join(options)}")
        return value
