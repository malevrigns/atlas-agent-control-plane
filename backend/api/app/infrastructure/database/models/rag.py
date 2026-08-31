from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import JsonValue, UtcDateTime, UuidValue, json_default


class KnowledgeBaseModel(Base):
    """知识库数据库模型。

    注意：这里不出现 embedding 列。向量数据由 VectorStore 层
    独立管理（pgvector 后端写入 knowledge_chunk_embeddings 表，
    Qdrant 后端写入外部 collection），保证 ORM 模型对向量后端零感知。
    """

    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    # 建库时冻结 embedding 配置：换模型必须重建索引，不能混用维度。
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JsonValue,
        nullable=False,
        default=dict,
        server_default=json_default("{}"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    def to_entity(self) -> KnowledgeBase:
        return KnowledgeBase(
            id=self.id,
            name=self.name,
            description=self.description,
            project_id=self.project_id,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            embedding_dim=self.embedding_dim,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            document_count=self.document_count,
            chunk_count=self.chunk_count,
            metadata=dict(self.metadata_json or {}),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
        )


class KnowledgeDocumentModel(Base):
    """知识文档数据库模型。content_sha256 用于同库去重。"""

    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    knowledge_base_id: Mapped[UUID] = mapped_column(
        UuidValue,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JsonValue,
        nullable=False,
        default=dict,
        server_default=json_default("{}"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_entity(self) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=self.id,
            knowledge_base_id=self.knowledge_base_id,
            title=self.title,
            source_type=KnowledgeSourceType(self.source_type),
            source_ref=self.source_ref,
            content=self.content,
            content_sha256=self.content_sha256,
            status=KnowledgeDocumentStatus(self.status),
            chunk_count=self.chunk_count,
            error=self.error,
            metadata=dict(self.metadata_json or {}),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class KnowledgeChunkModel(Base):
    """chunk 数据库模型。检索命中后从这里取正文与引用位置。"""

    __tablename__ = "knowledge_chunks"

    id: Mapped[UUID] = mapped_column(UuidValue, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        UuidValue,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        UuidValue,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 父文档检索：子块所属父块序号；单级切分的旧数据保持 NULL。
    parent_seq: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JsonValue,
        nullable=False,
        default=dict,
        server_default=json_default("{}"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, server_default=func.now()
    )

    def to_entity(self) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=self.id,
            document_id=self.document_id,
            knowledge_base_id=self.knowledge_base_id,
            seq=self.seq,
            content=self.content,
            char_start=self.char_start,
            char_end=self.char_end,
            token_estimate=self.token_estimate,
            parent_seq=self.parent_seq,
            metadata=dict(self.metadata_json or {}),
            created_at=self.created_at,
        )
