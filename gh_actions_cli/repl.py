from __future__ import annotations

import importlib
from types import ModuleType

from rich.console import Console

from gh_actions_cli.app import App


def enable_line_editing() -> ModuleType | None:
    try:
        readline = importlib.import_module("readline")
    except ImportError:
        return None
    readline.parse_and_bind("tab: complete")
    return readline


def run_repl(app: App, console: Console) -> int:
    readline = enable_line_editing()
    console.print("Введите /help для списка команд.")
    while True:
        try:
            line = console.input("[bold cyan]gh-actions> [/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        if not line.strip():
            continue
        if readline is not None:
            readline.add_history(line)
        if not app.handle_line(line):
            return 0
