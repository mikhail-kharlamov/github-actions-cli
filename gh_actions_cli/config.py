from __future__ import annotations

import os
from dataclasses import dataclass

from gh_actions_cli.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, set_language, t


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(slots=True)
class AppConfig:
    github_pat: str
    github_repository: str
    owner: str
    repo: str
    github_api_url: str
    poll_interval: int
    default_branch: str | None
    # AI diagnosis settings
    ai_command: str = "codex"
    ai_command_args: str = "exec --skip-git-repo-check --color never"
    diagnose_output_dir: str = "~/.gh-actions-diagnoses"
    max_log_lines_per_job: int = 150
    ai_timeout: int = 120


def load_config() -> AppConfig:
    language = os.environ.get("GH_ACTIONS_LANG", DEFAULT_LANGUAGE).strip().lower()
    set_language(language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)

    github_pat = os.environ.get("GITHUB_PAT")
    if not github_pat:
        raise ConfigError(t("config.missing_pat"))

    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        raise ConfigError(t("config.missing_repo"))

    owner, repo = _parse_repository(repository)
    github_api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    poll_interval = int(os.environ.get("GH_ACTIONS_POLL_INTERVAL", "5"))
    default_branch = os.environ.get("GH_ACTIONS_DEFAULT_BRANCH")

    return AppConfig(
        github_pat=github_pat,
        github_repository=repository,
        owner=owner,
        repo=repo,
        github_api_url=github_api_url,
        poll_interval=poll_interval,
        default_branch=default_branch,
        ai_command=os.environ.get("GH_ACTIONS_AI_COMMAND", "codex"),
        ai_command_args=os.environ.get("GH_ACTIONS_AI_COMMAND_ARGS", "exec --skip-git-repo-check --color never"),
        diagnose_output_dir=os.environ.get("GH_ACTIONS_DIAGNOSE_DIR", "~/.gh-actions-diagnoses"),
        max_log_lines_per_job=int(os.environ.get("GH_ACTIONS_MAX_LOG_LINES", "150")),
        ai_timeout=int(os.environ.get("GH_ACTIONS_AI_TIMEOUT", "120")),
    )


def _parse_repository(value: str) -> tuple[str, str]:
    parts = value.split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ConfigError(t("config.bad_repo_format"))
    return parts[0], parts[1]
