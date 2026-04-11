from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowDispatchInput:
    name: str
    description: str = ""
    required: bool = False
    default: Any = None
    type: str = "string"
    options: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedCommand:
    name: str
    args: list[str]
    options: dict[str, str]


@dataclass(slots=True)
class WorkflowSummary:
    id: int
    name: str
    path: str
    state: str


@dataclass(slots=True)
class StepSummary:
    number: int
    name: str
    status: str
    conclusion: str | None = None


@dataclass(slots=True)
class JobSummary:
    id: int
    run_id: int
    name: str
    status: str
    conclusion: str | None = None
    steps: list[StepSummary] = field(default_factory=list)


@dataclass(slots=True)
class WorkflowRunSummary:
    id: int
    workflow_id: int | None
    name: str
    status: str
    conclusion: str | None
    head_branch: str | None = None


@dataclass(slots=True)
class ArtifactSummary:
    id: int
    run_id: int
    name: str
    size_in_bytes: int
    expired: bool
    archive_download_url: str


@dataclass(slots=True)
class RunInvocation:
    run_id: int | None
    workflow_identifier: str
    workflow_name: str
    ref: str
    inputs: dict[str, str] = field(default_factory=dict)
    source: str = "local-cli"


@dataclass(slots=True)
class SessionState:
    workflow_index: dict[int, WorkflowSummary] = field(default_factory=dict)
    run_index: dict[int, WorkflowRunSummary] = field(default_factory=dict)
    job_index: dict[int, JobSummary] = field(default_factory=dict)
    artifact_index: dict[int, ArtifactSummary] = field(default_factory=dict)
    recent_invocations: list[RunInvocation] = field(default_factory=list)
