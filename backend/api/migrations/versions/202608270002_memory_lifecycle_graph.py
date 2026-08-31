"""add memory lifecycle, usage tracking, graph links and audit events

Revision ID: 202608270002
Revises: 202608270001
Create Date: 2026-08-27 00:00:00

为长期记忆升级生命周期能力：
- related_ids：记忆图谱关联边（JSONB，存关联记忆的 uuid 字符串）。
- access_count / last_accessed_at：检索命中统计，作为艾宾浩斯衰减的时间锚点。
- memory_audit_events：冲突消解、巩固等自动化动作的审计事件表。
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from migrations.portable import JSONB, UUID, json_server_default

revision: str = "202608270002"
down_revision: str | None = "202608270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None



def upgrade() -> None:
    # 1. 记忆主体新增使用统计与图谱关联字段。
    op.add_column(
        "agent_memories",
        sa.Column("related_ids", JSONB, nullable=False, server_default=json_server_default("[]")),
    )
    op.add_column(
        "agent_memories",
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_memories",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. 记忆生命周期审计事件表。
    op.create_table(
        "memory_audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "memory_id",
            UUID,
            sa.ForeignKey("agent_memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=json_server_default("{}")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_memory_audit_events_memory_id",
        "memory_audit_events",
        ["memory_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_audit_events_memory_id", table_name="memory_audit_events")
    op.drop_table("memory_audit_events")
    op.drop_column("agent_memories", "last_accessed_at")
    op.drop_column("agent_memories", "access_count")
    op.drop_column("agent_memories", "related_ids")
