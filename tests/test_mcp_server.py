from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from gh_actions_cli import mcp_server


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PAT", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_ACTIONS_DEFAULT_BRANCH", "main")


def test_list_workflows(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows",
        json={"workflows": [{"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"}]},
    )

    result = mcp_server.list_workflows()

    assert result == [{"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"}]


def test_dispatch_workflow_resolves_workflow_and_ref(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows",
        json={"workflows": [{"id": 1, "name": "Build", "path": ".github/workflows/build.yml", "state": "active"}]},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows/build.yml/dispatches",
        status_code=204,
    )

    result = mcp_server.dispatch_workflow("build.yml", inputs={"foo": "bar"})

    assert result["dispatched"] is True
    assert result["ref"] == "main"
    request = httpx_mock.get_requests()[-1]
    assert request.method == "POST"
    assert request.content == b'{"ref":"main","inputs":{"foo":"bar"}}'


def test_get_runner_load_computes_pressure(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs?per_page=100",
        json={
            "workflow_runs": [
                {"id": 1, "workflow_id": 1, "name": "Build", "status": "queued", "conclusion": None},
                {"id": 2, "workflow_id": 1, "name": "Build", "status": "queued", "conclusion": None},
                {"id": 3, "workflow_id": 2, "name": "Deploy", "status": "in_progress", "conclusion": None},
            ]
        },
    )

    result = mcp_server.get_runner_load()

    assert result["queued"] == 2
    assert result["in_progress"] == 1
    assert result["pressure"] == "overloaded"
    assert result["workflows"][0]["workflow_name"] == "Build"


def test_get_job_log_matches_job_by_name(httpx_mock: HTTPXMock) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("test.txt", "hello world")
    zip_bytes = buffer.getvalue()

    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/jobs",
        json={
            "jobs": [
                {"id": 100, "run_id": 10, "name": "test", "status": "completed", "conclusion": "success", "steps": []}
            ]
        },
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/logs",
        content=zip_bytes,
    )

    result = mcp_server.get_job_log(10, "test")

    assert result["job_id"] == 100
    assert result["content"] == "hello world"


def test_find_workflow_raises_for_unknown_token() -> None:
    with pytest.raises(ValueError, match="not found"):
        mcp_server._find_workflow([], "missing.yml")
