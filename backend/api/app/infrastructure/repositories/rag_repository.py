from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)
from app.domain.rag.repositories import (
    KnowledgeBaseRepository,
    KnowledgeChunkRepository,
    KnowledgeDocumentRepository,
)
from app.infrastructure.database.models.rag import (
    KnowledgeBaseModel,
    KnowledgeChunkModel,
    KnowledgeDocumentModel,
)


class SqlAlchemyKnowledgeBaseRepository(KnowledgeBaseRepository):
    """使用 SQLAlchemy 实现知识库读写。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

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
        model = KnowledgeBaseModel(
            name=name,
            description=description,
            project_id=project_id,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata_json=metadata or {},
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        stmt = (
            select(KnowledgeBaseModel)
            .where(KnowledgeBaseModel.id == knowledge_base_id)
            .where(KnowledgeBaseModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_active(
        self,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBaseModel).where(KnowledgeBaseModel.deleted_at.is_(None))
        if project_id:
            stmt = stmt.where(KnowledgeBaseModel.project_id == project_id)
        stmt = stmt.order_by(KnowledgeBaseModel.updated_at.desc()).limit(limit)
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def update(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeBase | None:
        model = await self._get_model(knowledge_base_id)
        if model is None:
            return None
        if name is not None:
            model.name = name
        if description is not None:
            model.description = description
        if metadata is not None:
            model.metadata_json = metadata
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def refresh_statistics(
        self,
        knowledge_base_id: UUID,
        *,
        document_count: int,
        chunk_count: int,
    ) -> KnowledgeBase | None:
        model = await self._get_model(knowledge_base_id)
        if model is None:
            return None
        model.document_count = document_count
        model.chunk_count = chunk_count
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def soft_delete(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        model = await self._get_model(knowledge_base_id)
        if model is None:
            return None
        model.deleted_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def _get_model(self, knowledge_base_id: UUID) -> KnowledgeBaseModel | None:
        stmt = (
            select(KnowledgeBaseModel)
            .where(KnowledgeBaseModel.id == knowledge_base_id)
            .where(KnowledgeBaseModel.deleted_at.is_(None))
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()


class SqlAlchemyKnowledgeDocumentRepository(KnowledgeDocumentRepository):
    """使用 SQLAlchemy 实现知识文档读写。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

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
        model = KnowledgeDocumentModel(
            knowledge_base_id=knowledge_base_id,
            title=title,
            source_type=source_type.value,
            source_ref=source_ref,
            content=content,
            content_sha256=content_sha256,
            status=KnowledgeDocumentStatus.pending.value,
            metadata_json=metadata or {},
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def get(self, document_id: UUID) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def find_by_sha256(
        self,
        *,
        knowledge_base_id: UUID,
        content_sha256: str,
    ) -> KnowledgeDocument | None:
        stmt = (
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.knowledge_base_id == knowledge_base_id)
            .where(KnowledgeDocumentModel.content_sha256 == content_sha256)
        )
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        return model.to_entity() if model else None

    async def list_by_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        status: KnowledgeDocumentStatus | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocumentModel).where(
            KnowledgeDocumentModel.knowledge_base_id == knowledge_base_id
        )
        if status is not None:
            stmt = stmt.where(KnowledgeDocumentModel.status == status.value)
        stmt = stmt.order_by(KnowledgeDocumentModel.created_at.desc()).limit(limit)
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def count_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        stmt = select(func.count(KnowledgeDocumentModel.id)).where(
            KnowledgeDocumentModel.knowledge_base_id == knowledge_base_id
        )
        result = await self.db_session.execute(stmt)
        return int(result.scalar_one())

    async def set_status(
        self,
        document_id: UUID,
        *,
        status: KnowledgeDocumentStatus,
        chunk_count: int | None = None,
        error: str | None = None,
    ) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.status = status.value
        if chunk_count is not None:
            model.chunk_count = chunk_count
        if error is not None:
            model.error = error
        model.updated_at = datetime.now(UTC)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def delete(self, document_id: UUID) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.id == document_id)
        result = await self.db_session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        entity = model.to_entity()
        await self.db_session.delete(model)
        await self.db_session.flush()
        return entity


class SqlAlchemyKnowledgeChunkRepository(KnowledgeChunkRepository):
    """使用 SQLAlchemy 实现 chunk 读写。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def add_many(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        models = [
            KnowledgeChunkModel(
                id=chunk.id or uuid4(),
                document_id=chunk.document_id,
                knowledge_base_id=chunk.knowledge_base_id,
                seq=chunk.seq,
                content=chunk.content,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                token_estimate=chunk.token_estimate,
                metadata_json=chunk.metadata,
            )
            for chunk in chunks
        ]
        self.db_session.add_all(models)
        await self.db_session.flush()
        return [model.to_entity() for model in models]

    async def get_many(self, chunk_ids: list[UUID]) -> list[KnowledgeChunk]:
        if not chunk_ids:
            return []
        stmt = select(KnowledgeChunkModel).where(KnowledgeChunkModel.id.in_(chunk_ids))
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]

    async def count_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        stmt = select(func.count(KnowledgeChunkModel.id)).where(
            KnowledgeChunkModel.knowledge_base_id == knowledge_base_id
        )
        result = await self.db_session.execute(stmt)
        return int(result.scalar_one())

    async def delete_by_document(self, document_id: UUID) -> int:
        result = await self.db_session.execute(
            delete(KnowledgeChunkModel).where(KnowledgeChunkModel.document_id == document_id)
        )
        return int(cast(CursorResult, result).rowcount or 0)

    async def delete_by_knowledge_base(self, knowledge_base_id: UUID) -> int:
        result = await self.db_session.execute(
            delete(KnowledgeChunkModel).where(
                KnowledgeChunkModel.knowledge_base_id == knowledge_base_id
            )
        )
        return int(cast(CursorResult, result).rowcount or 0)
