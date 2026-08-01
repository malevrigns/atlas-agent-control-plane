from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TaskStateCreateRequest(BaseModel):
    session_id: UUID | None = None
    project_id: str = Field(default="default", min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    goal: str = Field(min_length=1, max_length=8000)
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: str = "pending"
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    progress: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {"done": [], "doing": [], "blocked": []}
    )
    known_failures: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    environment_ref: UUID | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    current_event_seq: int = Field(default=0, ge=0)


class TaskStateUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    goal: str | None = Field(default=None, min_length=1, max_length=8000)
    acceptance_criteria: list[str] | None = None
    status: str | None = None
    requirements: list[dict[str, Any]] | None = None
    decisions: list[dict[str, Any]] | None = None
    progress: dict[str, list[dict[str, Any]]] | None = None
    known_failures: list[dict[str, Any]] | None = None
    open_questions: list[dict[str, Any]] | None = None
    next_actions: list[dict[str, Any]] | None = None
    must_preserve: list[str] | None = None
    environment_ref: UUID | None = None
    artifact_refs: list[str] | None = None
    current_event_seq: int | None = Field(default=None, ge=0)


class TaskStateResponse(TaskStateCreateRequest):
    id: UUID
    version: int
    state_hash: str
    created_at: datetime
    updated_at: datetime


class TaskStateListResponse(BaseModel):
    items: list[TaskStateResponse]


class CheckpointCreateRequest(BaseModel):
    kind: str = "incremental"
    parent_checkpoint_id: UUID | None = None
    covered_event_start: int = Field(ge=0)
    covered_event_end: int = Field(ge=0)


class CheckpointResponse(BaseModel):
    id: UUID
    task_id: UUID
    parent_checkpoint_id: UUID | None
    kind: str
    covered_event_start: int
    covered_event_end: int
    snapshot: dict[str, Any]
    state_hash: str
    validator_report: dict[str, Any]
    created_at: datetime


class CheckpointListResponse(BaseModel):
    items: list[CheckpointResponse]


class ArtifactResponse(BaseModel):
    id: UUID
    sha256: str
    kind: str
    media_type: str
    size_bytes: int
    project_id: str
    task_id: UUID | None
    source_event_id: UUID | None
    metadata: dict[str, Any]
    sensitivity: str
    created_at: datetime


class EnvironmentSnapshotRequest(BaseModel):
    project_id: str = "default"
    task_id: UUID | None = None
    snapshot: dict[str, Any]


class EnvironmentSnapshotResponse(BaseModel):
    id: UUID
    task_id: UUID | None
    project_id: str
    fingerprint: str
    snapshot: dict[str, Any]
    sensitivity: str
    created_at: datetime


class ToolInvocationResponse(BaseModel):
    id: UUID
    tool_name: str
    tool_version: str
    task_id: UUID | None
    session_id: UUID | None
    project_id: str
    idempotency_key: str | None
    request_hash: str
    risk_level: str
    permissions: list[str]
    decision: str
    decision_reason: str
    status: str
    arguments: dict[str, Any]
    output_preview: str
    artifact_id: UUID | None
    error: str | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None


class ToolInvocationListResponse(BaseModel):
    items: list[ToolInvocationResponse]
