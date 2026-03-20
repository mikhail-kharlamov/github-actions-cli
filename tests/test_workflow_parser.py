import pytest

from gh_actions_cli.workflow_parser import WorkflowParseError, extract_workflow_dispatch_inputs


def test_extracts_workflow_dispatch_inputs() -> None:
    yaml_text = """
on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        default: staging
        type: choice
        options:
          - staging
          - production
      dry_run:
        description: Run without deployment
        required: false
        type: boolean
"""

    inputs = extract_workflow_dispatch_inputs(yaml_text)

    assert [item.name for item in inputs] == ["environment", "dry_run"]
    assert inputs[0].required is True
    assert inputs[0].default == "staging"
    assert inputs[0].type == "choice"
    assert inputs[0].options == ["staging", "production"]
    assert inputs[1].type == "boolean"


def test_returns_empty_list_when_dispatch_not_defined() -> None:
    yaml_text = """
on:
  push:
    branches:
      - main
"""

    assert extract_workflow_dispatch_inputs(yaml_text) == []


def test_raises_workflow_parse_error_for_invalid_yaml() -> None:
    with pytest.raises(WorkflowParseError):
        extract_workflow_dispatch_inputs("on: [")
