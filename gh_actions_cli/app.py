from __future__ import annotations

import time
from pathlib import Path
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


HELP_TEXT = """\
/help                        показать список команд
/workflows                   получить список workflow
/workflow <workflow>         показать детали workflow
/dispatch-inputs <workflow>  показать workflow_dispatch inputs
/run <workflow> [ref=...] [key=value ...]
/run-form <workflow>         интерактивный запуск workflow
/runs <workflow> [limit=10]  последние run-ы workflow
/run-status <run-id>         статус конкретного run
/follow <run-id>             следить за статусом run
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
/clear                       очистить экран
/quit                        выйти

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
            self._handle_follow(args)
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
        inputs = {key: value for key, value in options.items() if key != "ref"}
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

    def _handle_follow(self, args: list[str]) -> None:
        run = self._resolve_run(args)
        while True:
            current = self.github_client.get_run(run.id)
            render_message(
                self.console,
                f"Run {current.id}: {current.conclusion or current.status}",
                style="yellow" if current.status != "completed" else "green",
            )
            if current.status == "completed":
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

    def _handle_runner_load(self, options: dict[str, str]) -> None:
        limit = int(options.get("limit", "100"))
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
        summary = RunnerLoadSummary(
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
        render_runner_load(self.console, summary)

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
