import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from gh_actions_cli.config import AppConfig
from gh_actions_cli.github_api import GitHubActionsClient, GitHubAPIError


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        github_pat="token",
        github_repository="owner/repo",
        owner="owner",
        repo="repo",
        github_api_url="https://api.github.com",
        poll_interval=5,
        default_branch=None,
    )


def test_list_workflows(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows",
        json={
            "workflows": [
                {
                    "id": 1,
                    "name": "Build",
                    "path": ".github/workflows/build.yml",
                    "state": "active",
                }
            ]
        },
    )

    with GitHubActionsClient(config) as client:
        workflows = client.list_workflows()

    assert len(workflows) == 1
    assert workflows[0].id == 1
    assert workflows[0].path.endswith("build.yml")


def test_dispatch_workflow_posts_expected_payload(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows/build.yml/dispatches",
        status_code=204,
    )

    with GitHubActionsClient(config) as client:
        client.dispatch_workflow("build.yml", "main", {"foo": "bar"})

    request = httpx_mock.get_request()
    assert request.method == "POST"
    assert request.content == b'{"ref":"main","inputs":{"foo":"bar"}}'


def test_list_jobs_returns_jobs_and_steps(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/jobs",
        json={
            "jobs": [
                {
                    "id": 100,
                    "run_id": 10,
                    "name": "test",
                    "status": "completed",
                    "conclusion": "success",
                    "steps": [
                        {
                            "number": 1,
                            "name": "Checkout",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ],
                }
            ]
        },
    )

    with GitHubActionsClient(config) as client:
        jobs = client.list_jobs(10)

    assert jobs[0].id == 100
    assert jobs[0].steps[0].name == "Checkout"


def test_get_workflow_file_content_decodes_base64(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    encoded = base64.b64encode(b"name: Build").decode("ascii")
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/contents/.github/workflows/build.yml?ref=main",
        json={"content": encoded, "encoding": "base64"},
    )

    with GitHubActionsClient(config) as client:
        content = client.get_workflow_file_content(".github/workflows/build.yml", "main")

    assert content == "name: Build"


def test_raises_github_api_error_for_http_failure(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/workflows",
        status_code=401,
        json={"message": "Bad credentials"},
    )

    with GitHubActionsClient(config) as client:
        with pytest.raises(GitHubAPIError, match="Bad credentials"):
            client.list_workflows()


def test_download_run_logs_returns_zip_bytes(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/logs",
        content=b"zip-bytes",
        headers={"content-type": "application/zip"},
    )

    with GitHubActionsClient(config) as client:
        content = client.download_run_logs(10)

    assert content == b"zip-bytes"


def test_download_run_logs_follows_redirect(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/logs",
        status_code=302,
        headers={"location": "https://objects.example/logs.zip"},
    )
    httpx_mock.add_response(
        url="https://objects.example/logs.zip",
        content=b"zip-bytes",
        headers={"content-type": "application/zip"},
    )

    with GitHubActionsClient(config) as client:
        content = client.download_run_logs(10)

    assert content == b"zip-bytes"


def test_list_run_artifacts(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/artifacts",
        json={
            "artifacts": [
                {
                    "id": 501,
                    "name": "eval-agent-result",
                    "size_in_bytes": 4096,
                    "expired": False,
                    "archive_download_url": "https://api.github.com/repos/owner/repo/actions/artifacts/501/zip",
                }
            ]
        },
    )

    with GitHubActionsClient(config) as client:
        artifacts = client.list_run_artifacts(10)

    assert len(artifacts) == 1
    assert artifacts[0].id == 501
    assert artifacts[0].name == "eval-agent-result"


def test_download_artifact_zip_follows_redirect(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/artifacts/501/zip",
        status_code=302,
        headers={"location": "https://objects.example/artifact.zip"},
    )
    httpx_mock.add_response(
        url="https://objects.example/artifact.zip",
        content=b"artifact-zip",
        headers={"content-type": "application/zip"},
    )

    with GitHubActionsClient(config) as client:
        content = client.download_artifact_zip(501)

    assert content == b"artifact-zip"


def test_cancel_run_posts_expected_request(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs/10/cancel",
        status_code=202,
    )

    with GitHubActionsClient(config) as client:
        client.cancel_run(10)

    request = httpx_mock.get_request()
    assert request.method == "POST"
    assert request.url.path == "/repos/owner/repo/actions/runs/10/cancel"


def test_list_repository_runs(httpx_mock: HTTPXMock, config: AppConfig) -> None:
    httpx_mock.add_response(
        url="https://api.github.com/repos/owner/repo/actions/runs?per_page=50",
        json={
            "workflow_runs": [
                {
                    "id": 10,
                    "workflow_id": 1,
                    "name": "Build",
                    "status": "queued",
                    "conclusion": None,
                    "head_branch": "main",
                },
                {
                    "id": 11,
                    "workflow_id": 2,
                    "name": "Deploy",
                    "status": "in_progress",
                    "conclusion": None,
                    "head_branch": "release",
                },
            ]
        },
    )

    with GitHubActionsClient(config) as client:
        runs = client.list_repository_runs(limit=50)

    assert len(runs) == 2
    assert runs[0].status == "queued"
    assert runs[1].workflow_id == 2


def test_wraps_timeout_errors_as_github_api_error(config: AppConfig) -> None:
    with GitHubActionsClient(config) as client:
        assert client._client is not None
        client._client.request = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
            httpx.ConnectTimeout("timed out")
        )

        with pytest.raises(GitHubAPIError, match="timed out"):
            client.list_workflows()
