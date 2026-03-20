from __future__ import annotations

from rich.console import Console

from gh_actions_cli.app import App
from gh_actions_cli.config import ConfigError, load_config
from gh_actions_cli.github_api import GitHubActionsClient
from gh_actions_cli.repl import run_repl


def main() -> int:
    console = Console()
    try:
        config = load_config()
    except ConfigError as error:
        console.print(f"[red]{error}[/red]")
        return 1

    with GitHubActionsClient(config) as client:
        app = App(config=config, console=console, github_client=client)
        return run_repl(app, console)


if __name__ == "__main__":
    raise SystemExit(main())
