"""add workspace_dir and full_access to sessions

Revision ID: 202608200001
Revises: 202608090001
Create Date: 2026-08-20 00:00:00

为会话增加本地工作区目录与「最高权限」开关：
- workspace_dir：工作区目录（相对沙箱挂载根）。
- full_access：为 True 时文件/Shell 工具可访问整个挂载根，否则仅限工作区。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202608200001"
down_revision: str | None = "202608090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("workspace_dir", sa.String(length=512), nullable=False, server_default=""),
    )
    op.add_column(
        "sessions",
        sa.Column("full_access", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("sessions", "full_access")
    op.drop_column("sessions", "workspace_dir")
