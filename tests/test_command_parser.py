import pytest

from gh_actions_cli.commands import CommandError, parse_command


def test_parse_run_command_with_ref_and_inputs() -> None:
    command = parse_command("/run 3 ref=main foo=bar dry_run=true")

    assert command.name == "run"
    assert command.args == ["3"]
    assert command.options == {"ref": "main", "foo": "bar", "dry_run": "true"}


def test_parse_step_log_command_with_name_argument() -> None:
    command = parse_command("/step-log 11 build")

    assert command.name == "step-log"
    assert command.args == ["11", "build"]
    assert command.options == {}


def test_parse_runs_command_extracts_limit_option() -> None:
    command = parse_command("/runs 4 limit=20")

    assert command.name == "runs"
    assert command.args == ["4"]
    assert command.options == {"limit": "20"}


def test_parse_runner_load_command_without_arguments() -> None:
    command = parse_command("/runner-load")

    assert command.name == "runner-load"
    assert command.args == []
    assert command.options == {}


def test_parse_command_rejects_unknown_commands() -> None:
    with pytest.raises(CommandError, match="Неизвестная команда"):
        parse_command("/wat")


def test_parse_command_requires_slash_prefix() -> None:
    with pytest.raises(CommandError, match="начинаться с /"):
        parse_command("run 1")
