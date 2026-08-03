from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TaskStateStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    blocked = "blocked"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class CheckpointKind(StrEnum):
    incremental = "incremental"
    full = "full"


class ArtifactKind(StrEnum):
    tool_output = "tool_output"
    file = "file"
    log = "log"
    patch = "patch"
    test_report = "test_report"
    screenshot = "screenshot"
    other = "other"


@dataclass(slots=True)
class TaskState:
    id: UUID
    title: str
    goal: str
    acceptance_criteria: list[str]
    status: TaskStateStatus
    project_id: str
    session_id: UUID | None = None
    requirements: list[dict[str, object]] = field(default_factory=list)
    decisions: list[dict[str, object]] = field(default_factory=list)
    progress: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    known_failures: list[dict[str, object]] = field(default_factory=list)
    open_questions: list[dict[str, object]] = field(default_factory=list)
    next_actions: list[dict[str, object]] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    environment_ref: UUID | None = None
    artifact_refs: list[str] = field(default_factory=list)
    current_event_seq: int = 0
    version: int = 1
    state_hash: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Checkpoint:
    id: UUID
    task_id: UUID
    parent_checkpoint_id: UUID | None
    kind: CheckpointKind
    covered_event_start: int
    covered_event_end: int
    snapshot: dict[str, object]
    state_hash: str
    validator_report: dict[str, object]
    created_at: datetime | None = None


@dataclass(slots=True)
class Artifact:
    id: UUID
    sha256: str
    kind: ArtifactKind
    media_type: str
    size_bytes: int
    storage_path: str
    project_id: str
    task_id: UUID | None = None
    source_event_id: UUID | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    sensitivity: str = "internal"
    created_at: datetime | None = None


@dataclass(slots=True)
class CheckpointValidation:
    valid: bool
    errors: list[str]
    warnings: list[str]
    inherited_constraints: list[str]
