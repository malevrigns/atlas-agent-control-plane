"""create rag knowledge tables and activate skill registry

Revision ID: 202608090001
Revises: 202608010001
Create Date: 2026-08-09 12:00:00

本迁移做两件事：

1. 创建 RAG 知识库三张表（knowledge_bases / knowledge_documents /
   knowledge_chunks），以及 pgvector 后端使用的向量表
   knowledge_chunk_embeddings。向量列的类型在运行时探测：
   数据库装有 pgvector 扩展时使用原生 ``vector`` 类型并建 HNSW 索引；
   没有扩展时降级为 JSONB，向量检索退回应用层余弦计算，
   保证任何 PostgreSQL 实例都能完成迁移。

2. 激活第 45 章预留的 skills 表：补充展示名、指引正文、标签、
   启用开关与审计时间，使其成为完整的技能注册中心。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202608090001"
down_revision: str | None = "202608010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def _pgvector_available() -> bool:
    """探测当前数据库能否安装 pgvector 扩展。

    离线生成 SQL（alembic upgrade --sql）时没有连接，按不可用处理，
    离线脚本会输出可移植的 JSONB 版本。
    """

    bind = op.get_bind()
    if bind is None or getattr(bind, "engine", None) is None:
        return False
    try:
        row = bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).fetchone()
    except Exception:  # pragma: no cover - 离线模式或权限受限
        return False
    return row is not None


def upgrade() -> None:
    # ===================== 第1步：知识库主表 =====================
    op.create_table(
        "knowledge_bases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(128), nullable=False, server_default="default"),
        sa.Column("embedding_provider", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_bases_project", "knowledge_bases", ["project_id", "deleted_at"])

    # ===================== 第2步：文档表（含同库去重指纹） =====================
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("knowledge_base_id", UUID, nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(512), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("knowledge_base_id", "content_sha256", name="uq_knowledge_document_sha"),
    )
    op.create_index(
        "ix_knowledge_documents_kb_status",
        "knowledge_documents",
        ["knowledge_base_id", "status"],
    )

    # ===================== 第3步：chunk 表（检索正文的事实源） =====================
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("knowledge_base_id", UUID, nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_start", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("char_end", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "seq", name="uq_knowledge_chunk_seq"),
    )
    op.create_index("ix_knowledge_chunks_kb", "knowledge_chunks", ["knowledge_base_id"])

    # ===================== 第4步：pgvector 向量表（带优雅降级） =====================
    if _pgvector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(
            """
            CREATE TABLE knowledge_chunk_embeddings (
                chunk_id UUID PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
                document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                embedding vector NOT NULL,
                embedding_dim INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # 无类型修饰的 vector 列不能直接建 ANN 索引；按库内主流维度
        # 建索引的工作由 PgVectorStore.ensure_ready 在首次写入时完成。
    else:
        op.execute(
            """
            CREATE TABLE knowledge_chunk_embeddings (
                chunk_id UUID PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
                document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                embedding JSONB NOT NULL,
                embedding_dim INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    op.create_index(
        "ix_knowledge_chunk_embeddings_kb",
        "knowledge_chunk_embeddings",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_chunk_embeddings_doc",
        "knowledge_chunk_embeddings",
        ["document_id"],
    )

    # ===================== 第5步：激活技能注册中心 =====================
    op.add_column("skills", sa.Column("name", sa.String(160), nullable=False, server_default=""))
    op.add_column("skills", sa.Column("instructions", sa.Text(), nullable=False, server_default=""))
    op.add_column("skills", sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("skills", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("skills", sa.Column("created_by", sa.String(128), nullable=False, server_default="system"))
    op.add_column("skills", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("skills", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    # 第 45 章的默认状态 candidate 并入新的 draft 生命周期。
    op.execute("UPDATE skills SET status = 'draft' WHERE status = 'candidate'")
    op.alter_column("skills", "status", server_default="draft")
    op.create_index("ix_skills_key_status", "skills", ["skill_key", "status", "enabled"])


def downgrade() -> None:
    op.drop_index("ix_skills_key_status", table_name="skills")
    op.execute("UPDATE skills SET status = 'candidate' WHERE status = 'draft'")
    op.alter_column("skills", "status", server_default="candidate")
    for column in ["deleted_at", "updated_at", "created_by", "enabled", "tags", "instructions", "name"]:
        op.drop_column("skills", column)

    op.drop_index("ix_knowledge_chunk_embeddings_doc", table_name="knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunk_embeddings_kb", table_name="knowledge_chunk_embeddings")
    op.drop_table("knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunks_kb", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_kb_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_knowledge_bases_project", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
