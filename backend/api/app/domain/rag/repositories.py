from typing import Protocol
from uuid import UUID

from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)


class KnowledgeBaseRepository(Protocol):
    """知识库仓库协议。应用服务只依赖协议，不依赖 SQLAlchemy。"""

    async def add(
        self,
        *,
        name: str,
        description: str,
        project_id: str,
        embedding_provider: str,
        embedding_model: str,
        embedding_dim: int,
        chunk_size: int,
        chunk_overlap: int,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeBase:
        raise NotImplementedError

    async def get(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        raise NotImplementedError

    async def list_active(
        self,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        raise NotImplementedError

    async def update(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeBase | None:
        raise NotImplementedError

    async def refresh_statistics(
        self,
        knowledge_base_id: UUID,
        *,
        document_count: int,
        chunk_count: int,
    ) -> KnowledgeBase | None:
        raise NotImplementedError

    async def soft_delete(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        raise NotImplementedError


class KnowledgeDocumentRepository(Protocol):
    """知识文档仓库协议。"""

    async def add(
        self,
        *,
        knowledge_base_id: UUID,
        title: str,
        source_type: KnowledgeSourceType,
        source_ref: str,
        content: str,
        content_sha256: str,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeDocument:
        raise NotImplementedError

    async def get(self, document_id: UUID) -> KnowledgeDocument | None:
        raise NotImplementedError

    async def find_by_sha256(
        self,
        *,
        knowledge_base_id: UUID,
        content_sha256: str,
    ) -> KnowledgeDocument | None:
        raise NotImplementedError

    async def list_by_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        status: KnowledgeDocumentStatus | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        raise NotImplementedError

    async def count_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        raise NotImplementedError

    async def set_status(
        self,
        document_id: UUID,
        *,
        status: KnowledgeDocumentStatus,
        chunk_count: int | None = None,
        error: str | None = None,
    ) -> KnowledgeDocument | None:
        raise NotImplementedError

    async def delete(self, document_id: UUID) -> KnowledgeDocument | None:
        raise NotImplementedError


class KnowledgeChunkRepository(Protocol):
    """知识 chunk 仓库协议。chunk 表是检索正文的事实源。"""

    async def add_many(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        raise NotImplementedError

    async def get_many(self, chunk_ids: list[UUID]) -> list[KnowledgeChunk]:
        raise NotImplementedError

    async def count_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        raise NotImplementedError

    async def delete_by_document(self, document_id: UUID) -> int:
        raise NotImplementedError

    async def delete_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        raise NotImplementedError
