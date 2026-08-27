"""add parent_seq to knowledge_chunks for parent-document retrieval

Revision ID: 202608270001
Revises: 202608200001
Create Date: 2026-08-27 22:30:00

父文档检索（small-to-big）的数据模型升级：

1. knowledge_chunks 增加可空的 parent_seq 列，记录子块所属父块
   的序号。两级切分管线（split_with_parents）产出的子块写入该列；
   传统单级切分的存量数据保持 NULL，检索侧据此决定走"父块拼回"
   还是"邻块扩展"，完全向后兼容，无需重建任何已有知识库。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202608270001"
down_revision: str | None = "202608200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("parent_seq", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "parent_seq")
