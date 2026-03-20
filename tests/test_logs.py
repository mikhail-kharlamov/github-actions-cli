from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from gh_actions_cli.logs import LogFormatError, StepLogResult, extract_job_logs, extract_step_log
from gh_actions_cli.models import JobSummary, StepSummary


def _build_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "test.txt",
            "\n".join(
                [
                    "2026-03-19T10:00:00Z Current runner version: 2.1",
                    "2026-03-19T10:00:01Z ##[group]Run Checkout",
                    "2026-03-19T10:00:02Z cloning repo",
                    "2026-03-19T10:00:03Z ##[endgroup]",
                    "2026-03-19T10:00:04Z ##[group]Run Build",
                    "2026-03-19T10:00:05Z make test",
                    "2026-03-19T10:00:06Z ##[endgroup]",
                ]
            ),
        )
    return buffer.getvalue()


def test_extract_job_logs_returns_mapping_by_job_name() -> None:
    jobs = [JobSummary(id=1, run_id=10, name="test", status="completed")]

    logs = extract_job_logs(_build_zip(), jobs)

    assert logs[1].job_name == "test"
    assert "make test" in logs[1].content


def test_extract_job_logs_prefers_longer_matching_log_when_multiple_files_exist() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("test.txt", "short header")
        archive.writestr(
            "test_2.txt",
            "\n".join(
                [
                    "2026-03-19T10:00:01Z ##[group]Run Build",
                    "2026-03-19T10:00:02Z compiling",
                    "2026-03-19T10:00:03Z tests failed",
                    "2026-03-19T10:00:04Z ##[endgroup]",
                ]
            ),
        )

    jobs = [JobSummary(id=1, run_id=10, name="test", status="completed")]

    logs = extract_job_logs(buffer.getvalue(), jobs)

    assert logs[1].source_path == "test_2.txt"
    assert "tests failed" in logs[1].content


def test_extract_step_log_returns_matching_step_content() -> None:
    job = JobSummary(
        id=1,
        run_id=10,
        name="test",
        status="completed",
        steps=[
            StepSummary(number=1, name="Checkout", status="completed"),
            StepSummary(number=2, name="Build", status="completed"),
        ],
    )
    logs = extract_job_logs(_build_zip(), [job])

    result = extract_step_log(logs[1].content, job, "2")

    assert isinstance(result, StepLogResult)
    assert result.fallback_used is False
    assert "make test" in result.content


def test_extract_step_log_falls_back_to_full_job_log() -> None:
    job = JobSummary(
        id=1,
        run_id=10,
        name="test",
        status="completed",
        steps=[StepSummary(number=1, name="Missing", status="completed")],
    )
    logs = extract_job_logs(_build_zip(), [job])

    result = extract_step_log(logs[1].content, job, "1")

    assert result.fallback_used is True
    assert "Current runner version" in result.content


def test_extract_job_logs_raises_clean_error_for_non_zip_content() -> None:
    with pytest.raises(LogFormatError, match="Не удалось прочитать архив логов"):
        extract_job_logs(b"not-a-zip", [JobSummary(id=1, run_id=10, name="test", status="completed")])
