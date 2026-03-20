import os

import pytest

from gh_actions_cli.config import ConfigError, load_config


def test_load_config_reads_required_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PAT", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    config = load_config()

    assert config.github_pat == "token"
    assert config.owner == "owner"
    assert config.repo == "repo"
    assert config.github_api_url == "https://api.github.com"
    assert config.poll_interval == 5


def test_load_config_requires_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    with pytest.raises(ConfigError, match="GITHUB_PAT"):
        load_config()


def test_load_config_requires_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PAT", "token")
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    with pytest.raises(ConfigError, match="GITHUB_REPOSITORY"):
        load_config()


def test_load_config_rejects_invalid_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PAT", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "repo-only")

    with pytest.raises(ConfigError, match="owner/repo"):
        load_config()
