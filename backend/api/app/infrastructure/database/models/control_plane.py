from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonValue, UtcDateTime, UuidValue, json_default


class AgentTaskModel(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    session_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("sessions.id", ondelete="SET NULL"))
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")
    progress: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False, default=dict, server_default=json_default("{\"done\":[],\"doing\":[],\"blocked\":[]}"))
    known_failures: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    open_questions: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    next_actions: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    must_preserve: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    environment_ref: Mapped[UUID | None] = mapped_column(UuidValue)
    artifact_refs: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    current_event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    state_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class TaskRequirementModel(Base):
    __tablename__ = "task_requirements"
    __table_args__ = (UniqueConstraint("task_id", "requirement_key", name="uq_task_requirement_key"),)

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(64), nullable=False)
    text_value: Mapped[str] = mapped_column("text", Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    source_event_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("session_events.id", ondelete="SET NULL"))
    evidence: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class TaskDecisionModel(Base):
    __tablename__ = "task_decisions"
    __table_args__ = (UniqueConstraint("task_id", "decision_key", name="uq_task_decision_key"),)

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False)
    decision_key: Mapped[str] = mapped_column(String(64), nullable=False)
    text_value: Mapped[str] = mapped_column("text", Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", server_default="active")
    evidence: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False)
    parent_checkpoint_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("checkpoints.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="incremental", server_default="incremental")
    covered_event_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    covered_event_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False)
    state_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    validator_report: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="SET NULL"))
    source_event_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("session_events.id", ondelete="SET NULL"))
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JsonValue, nullable=False, default=dict, server_default=json_default("{}"))
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="internal", server_default="internal")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class EnvironmentSnapshotModel(Base):
    __tablename__ = "environment_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "fingerprint", name="uq_environment_fingerprint"),)

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    task_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="SET NULL"))
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(72), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(32), nullable=False, default="confidential", server_default="confidential")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class RetrievalTraceModel(Base):
    __tablename__ = "retrieval_traces"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    task_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="SET NULL"))
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False)
    candidates: Mapped[list[object]] = mapped_column(JsonValue, nullable=False)
    selected_memory_ids: Mapped[list[object]] = mapped_column(JsonValue, nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())


class ToolInvocationModel(Base):
    __tablename__ = "tool_invocations"
    __table_args__ = (UniqueConstraint("tool_name", "idempotency_key", name="uq_tool_invocation_idempotency"),)

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("agent_tasks.id", ondelete="SET NULL"))
    session_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("sessions.id", ondelete="SET NULL"))
    project_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    permissions: Mapped[list[object]] = mapped_column(JsonValue, nullable=False, default=list, server_default=json_default("[]"))
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[dict[str, object]] = mapped_column(JsonValue, nullable=False)
    output_preview: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    artifact_id: Mapped[UUID | None] = mapped_column(UuidValue, ForeignKey("artifacts.id", ondelete="SET NULL"))
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
