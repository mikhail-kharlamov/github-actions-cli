from __future__ import annotations

import builtins
from collections.abc import Iterator
from contextlib import contextmanager
import importlib
import signal
from types import ModuleType

from rich.console import Console

from gh_actions_cli.app import App

COMMAND_INTERRUPT_SIGNAL = getattr(signal, "SIGQUIT", None)
READLINE_PROMPT = "\001\033[1;36m\002gh-actions> \001\033[0m\002"
RICH_PROMPT = "[bold cyan]gh-actions> [/bold cyan]"


class CommandInterrupted(RuntimeError):
    """Raised when the user stops only the currently running command."""


def _raise_command_interrupted(_signal_number: int, _frame: object) -> None:
    raise CommandInterrupted


@contextmanager
def command_interrupts_enabled() -> Iterator[None]:
    if COMMAND_INTERRUPT_SIGNAL is None:
        yield
        return

    previous_handler = signal.signal(COMMAND_INTERRUPT_SIGNAL, _raise_command_interrupted)
    try:
        yield
    finally:
        signal.signal(COMMAND_INTERRUPT_SIGNAL, previous_handler)


def enable_line_editing() -> ModuleType | None:
    try:
        readline = importlib.import_module("readline")
    except ImportError:
        return None
    readline.parse_and_bind("tab: complete")
    return readline


def read_command_line(console: Console, readline: ModuleType | None) -> str:
    if readline is None:
        return console.input(RICH_PROMPT)
    return builtins.input(READLINE_PROMPT)


def run_repl(app: App, console: Console) -> int:
    readline = enable_line_editing()
    console.print(r"Введите /help для списка команд. Ctrl+\ останавливает текущую команду, Ctrl+C выходит.")
    with command_interrupts_enabled():
        while True:
            try:
                line = read_command_line(console, readline)
            except CommandInterrupted:
                console.print()
                continue
            except (EOFError, KeyboardInterrupt):
                console.print()
                return 0
            if not line.strip():
                continue
            if readline is not None:
                readline.add_history(line)
            try:
                if not app.handle_line(line):
                    return 0
            except CommandInterrupted:
                console.print("\nКоманда остановлена.")
