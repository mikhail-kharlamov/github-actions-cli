from __future__ import annotations

import builtins
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
import importlib
import signal
from types import ModuleType

from rich.console import Console

from gh_actions_cli.app import App
from gh_actions_cli.i18n import t

COMMAND_INTERRUPT_SIGNAL = getattr(signal, "SIGQUIT", None)
ANSI_PROMPT = "\033[1;36mgh-actions> \033[0m"
READLINE_PROMPT = "\001\033[1;36m\002gh-actions> \001\033[0m\002"
RICH_PROMPT = "[bold cyan]gh-actions> [/bold cyan]"
PROMPT_PLAIN = "gh-actions> "
TIMESTAMP_FORMAT = "%y-%m-%d @ %H:%M"


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


def readline_prompt(readline: ModuleType) -> str:
    if "libedit" in (readline.__doc__ or ""):
        return ANSI_PROMPT
    return READLINE_PROMPT


def read_command_line(console: Console, readline: ModuleType | None) -> str:
    if readline is None:
        return console.input(RICH_PROMPT)
    return builtins.input(readline_prompt(readline))


def _terminal_width(console: Console) -> int:
    return console.size.width or 80


def print_command_timestamp(console: Console, line: str) -> None:
    """Print the current time at the right edge of the just-entered command line.

    Falls back to a plain right-justified line below the command when the
    command text is long enough that overwriting in place would overlap it.
    """
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    width = _terminal_width(console)
    total_len = len(PROMPT_PLAIN) + len(line)
    last_row_len = total_len % width or width
    available = width - last_row_len
    gap = 1
    if available >= len(timestamp) + gap:
        console.file.write(
            f"\033[1A\033[{last_row_len + 1}G"
            f"{' ' * gap}\033[2;33m{timestamp}\033[0m"
            "\033[1B\033[1G"
        )
        console.file.flush()
    else:
        console.print(timestamp, style="dim yellow", justify="right", highlight=False)


def run_repl(app: App, console: Console) -> int:
    readline = enable_line_editing()
    console.print(t("repl.welcome"))
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
            print_command_timestamp(console, line)
            if readline is not None:
                readline.add_history(line)
            try:
                if not app.handle_line(line):
                    return 0
            except CommandInterrupted:
                console.print(t("repl.command_stopped"))
