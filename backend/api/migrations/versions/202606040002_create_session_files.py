"""create session files

Revision ID: 202606040002
Revises: 202606040001
Create Date: 2026-06-04 00:00:02
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from migrations.portable import UUID

revision: str = "202606040002"
down_revision: str | None = "202606040001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_files",
        sa.Column("id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("file_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "file_id", name="uq_session_files_session_file"),
    )
    op.create_index(
        "ix_session_files_session_created",
        "session_files",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_files_session_created", table_name="session_files")
    op.drop_table("session_files")
