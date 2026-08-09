from __future__ import annotations

import shlex

from gh_actions_cli.i18n import t
from gh_actions_cli.models import ParsedCommand


KNOWN_COMMANDS = {
    "help",
    "lang",
    "quit",
    "clear",
    "workflows",
    "workflow",
    "dispatch-inputs",
    "run",
    "run-form",
    "runs",
    "run-status",
    "follow",
    "jobs",
    "steps",
    "logs",
    "step-log",
    "follow-logs",
    "artifacts",
    "download-artifacts",
    "cancel-run",
    "run-args",
    "runner-load",
    "diagnose",
}


class CommandError(RuntimeError):
    """Raised when user enters an invalid command."""


def parse_command(raw: str) -> ParsedCommand:
    text = raw.strip()
    if not text.startswith("/"):
        raise CommandError(t("command.must_start_with_slash"))

    parts = shlex.split(text[1:])
    if not parts:
        raise CommandError(t("command.empty"))

    name = parts[0]
    if name not in KNOWN_COMMANDS:
        raise CommandError(t("command.unknown", name=name))

    args: list[str] = []
    options: dict[str, str] = {}
    for token in parts[1:]:
        if "=" in token:
            key, value = token.split("=", maxsplit=1)
            options[key] = value
        else:
            args.append(token)
    return ParsedCommand(name=name, args=args, options=options)
