"""add memory and tool control plane

Revision ID: 202608010001
Revises: 202606230001
Create Date: 2026-08-01 12:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from migrations.portable import JSONB, UUID, json_server_default

revision: str = "202608010001"
down_revision: str | None = "202606230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None



def upgrade() -> None:
    # Enrich the compatible memory table instead of replacing it.
    op.add_column("agent_memories", sa.Column("scope", sa.String(32), nullable=False, server_default="project"))
    op.add_column("agent_memories", sa.Column("status", sa.String(32), nullable=False, server_default="verified"))
    op.add_column("agent_memories", sa.Column("subject", sa.Text(), nullable=False, server_default=""))
    op.add_column("agent_memories", sa.Column("predicate", sa.String(128), nullable=False, server_default="states"))
    op.add_column("agent_memories", sa.Column("value", JSONB, nullable=False, server_default=json_server_default("{}")))
    op.add_column("agent_memories", sa.Column("confidence", sa.Float(), nullable=False, server_default="1"))
    op.add_column("agent_memories", sa.Column("authority", sa.String(32), nullable=False, server_default="explicit_user"))
    op.add_column("agent_memories", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_memories", sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_memories", sa.Column("ttl_seconds", sa.Integer(), nullable=True))
    op.add_column("agent_memories", sa.Column("provenance", JSONB, nullable=False, server_default=json_server_default("[]")))
    op.add_column("agent_memories", sa.Column("supersedes", UUID, nullable=True))
    op.add_column("agent_memories", sa.Column("sensitivity", sa.String(32), nullable=False, server_default="internal"))
    op.add_column("agent_memories", sa.Column("project_id", sa.String(128), nullable=True))
    op.add_column("agent_memories", sa.Column("task_id", UUID, nullable=True))
    op.add_column("agent_memories", sa.Column("user_id", sa.String(128), nullable=True))
    op.add_column("agent_memories", sa.Column("created_by", sa.String(128), nullable=False, server_default="legacy"))
    op.add_column("agent_memories", sa.Column("verification", JSONB, nullable=False, server_default=json_server_default("{}")))
    # SQLite 不支持 ALTER ADD CONSTRAINT，batch 模式在 PostgreSQL 上仍走
    # 普通 ALTER（SQL 与改造前一致），在 SQLite 上自动改用重建表策略。
    with op.batch_alter_table("agent_memories") as batch:
        batch.create_foreign_key(
            "fk_agent_memories_supersedes",
            "agent_memories",
            ["supersedes"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_agent_memories_scope_status", "agent_memories", ["project_id", "scope", "status"])
    op.create_index("ix_agent_memories_validity", "agent_memories", ["valid_from", "valid_to"])

    op.create_table(
        "agent_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("session_id", UUID, nullable=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("progress", JSONB, nullable=False, server_default=json_server_default("{\"done\":[],\"doing\":[],\"blocked\":[]}")),
        sa.Column("known_failures", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("open_questions", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("next_actions", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("must_preserve", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("environment_ref", UUID, nullable=True),
        sa.Column("artifact_refs", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("current_event_seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state_hash", sa.String(72), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_agent_tasks_project_status", "agent_tasks", ["project_id", "status"])

    op.create_table(
        "task_requirements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("requirement_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("source_event_id", UUID, nullable=True),
        sa.Column("evidence", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["session_events.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("task_id", "requirement_key", name="uq_task_requirement_key"),
    )
    op.create_table(
        "task_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("decision_key", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("evidence", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "decision_key", name="uq_task_decision_key"),
    )
    op.create_table(
        "checkpoints",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("parent_checkpoint_id", UUID, nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="incremental"),
        sa.Column("covered_event_start", sa.BigInteger(), nullable=False),
        sa.Column("covered_event_end", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("state_hash", sa.String(72), nullable=False),
        sa.Column("validator_report", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_checkpoint_id"], ["checkpoints.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_checkpoints_task_created", "checkpoints", ["task_id", "created_at"])

    op.create_table(
        "artifacts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("task_id", UUID, nullable=True),
        sa.Column("source_event_id", UUID, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default=json_server_default("{}")),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="internal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_event_id"], ["session_events.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_artifacts_project_task", "artifacts", ["project_id", "task_id"])

    op.create_table(
        "memory_relations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source_memory_id", UUID, nullable=False),
        sa.Column("target_memory_id", UUID, nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("evidence", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_memory_id"], ["agent_memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_memory_id"], ["agent_memories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_memory_id", "target_memory_id", "relation", name="uq_memory_relation"),
    )

    op.create_table(
        "environment_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, nullable=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(72), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="confidential"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_environment_fingerprint"),
    )

    op.create_table(
        "skills",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("skill_key", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("test_record", JSONB, nullable=False, server_default=json_server_default("{}")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("skill_key", "version", name="uq_skill_version"),
    )
    op.create_table(
        "skill_executions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("skill_id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=False, server_default=json_server_default("{}")),
        sa.Column("verification", JSONB, nullable=False, server_default=json_server_default("{}")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "retrieval_traces",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, nullable=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("plan", JSONB, nullable=False),
        sa.Column("candidates", JSONB, nullable=False),
        sa.Column("selected_memory_ids", JSONB, nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_retrieval_traces_project_task", "retrieval_traces", ["project_id", "task_id"])

    op.create_table(
        "tool_invocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("tool_version", sa.String(32), nullable=False),
        sa.Column("task_id", UUID, nullable=True),
        sa.Column("session_id", UUID, nullable=True),
        sa.Column("project_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("request_hash", sa.String(72), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("permissions", JSONB, nullable=False, server_default=json_server_default("[]")),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("arguments", JSONB, nullable=False),
        sa.Column("output_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("artifact_id", UUID, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tool_name", "idempotency_key", name="uq_tool_invocation_idempotency"),
    )
    op.create_index("ix_tool_invocations_task_started", "tool_invocations", ["task_id", "started_at"])
    op.create_index("ix_tool_invocations_status_risk", "tool_invocations", ["status", "risk_level"])

    with op.batch_alter_table("agent_memories") as batch:
        batch.create_foreign_key(
            "fk_agent_memories_task",
            "agent_tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_memories") as batch:
        batch.drop_constraint("fk_agent_memories_task", type_="foreignkey")
    for table in [
        "tool_invocations",
        "retrieval_traces",
        "skill_executions",
        "skills",
        "environment_snapshots",
        "memory_relations",
        "artifacts",
        "checkpoints",
        "task_decisions",
        "task_requirements",
        "agent_tasks",
    ]:
        op.drop_table(table)
    op.drop_index("ix_agent_memories_validity", table_name="agent_memories")
    op.drop_index("ix_agent_memories_scope_status", table_name="agent_memories")
    with op.batch_alter_table("agent_memories") as batch:
        batch.drop_constraint("fk_agent_memories_supersedes", type_="foreignkey")
    for column in [
        "verification", "created_by", "user_id", "task_id", "project_id",
        "sensitivity", "supersedes", "provenance", "ttl_seconds", "valid_to",
        "valid_from", "authority", "confidence", "value", "predicate", "subject",
        "status", "scope",
    ]:
        op.drop_column("agent_memories", column)
