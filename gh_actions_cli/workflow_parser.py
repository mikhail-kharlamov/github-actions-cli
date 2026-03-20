from __future__ import annotations

from collections import OrderedDict

import yaml

from gh_actions_cli.models import WorkflowDispatchInput


class WorkflowParseError(RuntimeError):
    """Raised when workflow YAML cannot be parsed."""


def extract_workflow_dispatch_inputs(yaml_text: str) -> list[WorkflowDispatchInput]:
    try:
        payload = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as error:
        raise WorkflowParseError("Не удалось распарсить workflow YAML.") from error

    on_section = payload.get("on") or payload.get(True) or {}
    if not isinstance(on_section, dict):
        return []

    dispatch = on_section.get("workflow_dispatch") or {}
    if not isinstance(dispatch, dict):
        return []

    inputs = dispatch.get("inputs") or OrderedDict()
    if not isinstance(inputs, dict):
        return []

    result: list[WorkflowDispatchInput] = []
    for name, spec in inputs.items():
        spec = spec or {}
        options = spec.get("options") or []
        result.append(
            WorkflowDispatchInput(
                name=name,
                description=str(spec.get("description", "")),
                required=bool(spec.get("required", False)),
                default=spec.get("default"),
                type=str(spec.get("type", "string")),
                options=[str(option) for option in options],
            )
        )
    return result
