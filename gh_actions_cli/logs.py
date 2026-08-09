from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from gh_actions_cli.i18n import t
from gh_actions_cli.models import JobSummary


@dataclass(slots=True)
class JobLog:
    job_name: str
    content: str
    source_path: str


@dataclass(slots=True)
class StepLogResult:
    content: str
    step_name: str
    fallback_used: bool


class LogFormatError(RuntimeError):
    """Raised when GitHub logs payload is not a valid archive."""


STEP_START_RE = re.compile(r"##\[group\]Run (?P<name>.+)")
STEP_END_RE = re.compile(r"##\[endgroup\]")


def extract_job_logs(archive_bytes: bytes, jobs: list[JobSummary]) -> dict[int, JobLog]:
    file_contents = _read_archive(archive_bytes)
    remaining_paths = list(file_contents.keys())
    results: dict[int, JobLog] = {}

    for job in jobs:
        match_path = _match_job_path(job.name, remaining_paths, file_contents)
        if match_path is None:
            continue
        remaining_paths.remove(match_path)
        results[job.id] = JobLog(job_name=job.name, content=file_contents[match_path], source_path=match_path)
    return results


def extract_step_log(job_log: str, job: JobSummary, step_selector: str) -> StepLogResult:
    target_name = _resolve_step_name(job, step_selector)
    if target_name is None:
        return StepLogResult(content=job_log, step_name=step_selector, fallback_used=True)

    groups = _split_step_groups(job_log)
    if target_name not in groups:
        return StepLogResult(content=job_log, step_name=target_name, fallback_used=True)
    return StepLogResult(content=groups[target_name], step_name=target_name, fallback_used=False)


def _read_archive(archive_bytes: bytes) -> dict[str, str]:
    results: dict[str, str] = {}
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            for path in archive.namelist():
                if path.endswith("/"):
                    continue
                results[path] = archive.read(path).decode("utf-8", errors="replace")
    except BadZipFile as error:
        raise LogFormatError(t("logs.archive_read_failed")) from error
    return results


def _match_job_path(job_name: str, available_paths: list[str], file_contents: dict[str, str]) -> str | None:
    if not available_paths:
        return None
    normalized_name = _normalize(job_name)
    ranked_paths = sorted(
        available_paths,
        key=lambda path: _path_score(normalized_name, path, file_contents[path]),
        reverse=True,
    )
    return ranked_paths[0]


def _path_score(normalized_job_name: str, path: str, content: str) -> tuple[int, int, int]:
    stem = path.rsplit("/", maxsplit=1)[-1].rsplit(".", maxsplit=1)[0]
    normalized_stem = _normalize(stem)
    normalized_base = re.sub(r"\d+$", "", normalized_stem)
    exact_match = int(normalized_stem == normalized_job_name or normalized_base == normalized_job_name)
    prefix_match = int(normalized_stem.startswith(normalized_job_name) or normalized_job_name in normalized_stem)
    content_length = len(content)
    return exact_match, prefix_match, content_length


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _resolve_step_name(job: JobSummary, step_selector: str) -> str | None:
    if step_selector.isdigit():
        number = int(step_selector)
        for step in job.steps:
            if step.number == number:
                return step.name
        return None
    for step in job.steps:
        if step.name == step_selector:
            return step.name
    return None


def _split_step_groups(job_log: str) -> dict[str, str]:
    groups: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in job_log.splitlines():
        start_match = STEP_START_RE.search(line)
        if start_match:
            current_name = start_match.group("name").strip()
            current_lines = [line]
            continue
        if current_name is not None:
            current_lines.append(line)
            if STEP_END_RE.search(line):
                groups[current_name] = "\n".join(current_lines)
                current_name = None
                current_lines = []
    return groups
