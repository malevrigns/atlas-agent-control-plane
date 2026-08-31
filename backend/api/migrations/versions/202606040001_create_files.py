"""create files

Revision ID: 202606040001
Revises: 202606030002
Create Date: 2026-06-04 00:00:01
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from migrations.portable import UUID

revision: str = "202606040001"
down_revision: str | None = "202606030002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", UUID, nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("files")
