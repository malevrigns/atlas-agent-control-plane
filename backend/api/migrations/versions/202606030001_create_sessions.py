"""create sessions table

Revision ID: 202606030001
Revises:
Create Date: 2026-06-03 00:00:01
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from migrations.portable import UUID

revision: str = "202606030001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_deleted_at", "sessions", ["deleted_at"])
    op.create_index("ix_sessions_updated_at", "sessions", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_updated_at", table_name="sessions")
    op.drop_index("ix_sessions_deleted_at", table_name="sessions")
    op.drop_table("sessions")
