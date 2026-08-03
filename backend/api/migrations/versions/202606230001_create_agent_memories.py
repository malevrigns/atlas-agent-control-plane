"""create agent memories

Revision ID: 202606230001
Revises: 202606040002
Create Date: 2026-06-23 00:00:01
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606230001"
down_revision: str | None = "202606040002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_event_id"],
            ["session_events.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_memories_kind_enabled",
        "agent_memories",
        ["kind", "enabled"],
    )
    op.create_index(
        "ix_agent_memories_importance_updated",
        "agent_memories",
        ["importance", "updated_at"],
    )
    op.create_index(
        "ix_agent_memories_source_session",
        "agent_memories",
        ["source_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_memories_source_session", table_name="agent_memories")
    op.drop_index("ix_agent_memories_importance_updated", table_name="agent_memories")
    op.drop_index("ix_agent_memories_kind_enabled", table_name="agent_memories")
    op.drop_table("agent_memories")
