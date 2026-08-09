import asyncio
import unittest
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.exceptions import AppException
from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
)
from app.domain.rag.vector_store import VectorMatch, VectorRecord, cosine_similarity
from app.application.rag_service import RagService
from app.infrastructure.rag.embeddings import HashingEmbeddingProvider


class InMemoryVectorStore:
    """内存向量存储：验证 VectorStore 协议在服务层的使用方式。"""

    backend_name = "in_memory"

    def __init__(self) -> None:
        self.records: dict[UUID, VectorRecord] = {}
        self.ready_calls: list[int] = []

    async def ensure_ready(self, *, knowledge_base_id, embedding_dim) -> None:
        self.ready_calls.append(embedding_dim)

    async def upsert(self, records) -> int:
        for record in records:
            self.records[record.chunk_id] = record
        return len(records)

    async def query(self, *, knowledge_base_id, embedding, top_k):
        matches = [
            VectorMatch(
                chunk_id=record.chunk_id,
                document_id=record.document_id,
                score=cosine_similarity(embedding, record.embedding),
            )
            for record in self.records.values()
            if record.knowledge_base_id == knowledge_base_id
        ]
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    async def delete_document(self, *, knowledge_base_id, document_id) -> int:
        doomed = [
            chunk_id
            for chunk_id, record in self.records.items()
            if record.document_id == document_id
        ]
        for chunk_id in doomed:
            del self.records[chunk_id]
        return len(doomed)

    async def delete_knowledge_base(self, *, knowledge_base_id) -> int:
        doomed = [
            chunk_id
            for chunk_id, record in self.records.items()
            if record.knowledge_base_id == knowledge_base_id
        ]
        for chunk_id in doomed:
            del self.records[chunk_id]
        return len(doomed)

    async def health(self) -> dict[str, object]:
        return {"backend": self.backend_name, "vector_count": len(self.records)}


class FakeKnowledgeBaseRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, KnowledgeBase] = {}

    async def add(self, **kwargs) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(
            id=uuid4(),
            name=kwargs["name"],
            description=kwargs["description"],
            project_id=kwargs["project_id"],
            embedding_provider=kwargs["embedding_provider"],
            embedding_model=kwargs["embedding_model"],
            embedding_dim=kwargs["embedding_dim"],
            chunk_size=kwargs["chunk_size"],
            chunk_overlap=kwargs["chunk_overlap"],
            metadata=kwargs.get("metadata") or {},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.items[knowledge_base.id] = knowledge_base
        return knowledge_base

    async def get(self, knowledge_base_id):
        knowledge_base = self.items.get(knowledge_base_id)
        if knowledge_base and knowledge_base.deleted_at is None:
            return knowledge_base
        return None

    async def list_active(self, *, project_id=None, limit=100):
        return [kb for kb in self.items.values() if kb.deleted_at is None][:limit]

    async def update(self, knowledge_base_id, **kwargs):
        return self.items.get(knowledge_base_id)

    async def refresh_statistics(self, knowledge_base_id, *, document_count, chunk_count):
        knowledge_base = self.items.get(knowledge_base_id)
        if knowledge_base:
            knowledge_base.document_count = document_count
            knowledge_base.chunk_count = chunk_count
        return knowledge_base

    async def soft_delete(self, knowledge_base_id):
        knowledge_base = self.items.get(knowledge_base_id)
        if knowledge_base:
            knowledge_base.deleted_at = datetime.now(UTC)
        return knowledge_base


class FakeKnowledgeDocumentRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, KnowledgeDocument] = {}

    async def add(self, **kwargs) -> KnowledgeDocument:
        document = KnowledgeDocument(
            id=uuid4(),
            knowledge_base_id=kwargs["knowledge_base_id"],
            title=kwargs["title"],
            source_type=kwargs["source_type"],
            source_ref=kwargs["source_ref"],
            content=kwargs["content"],
            content_sha256=kwargs["content_sha256"],
            status=KnowledgeDocumentStatus.pending,
            metadata=kwargs.get("metadata") or {},
            created_at=datetime.now(UTC),
        )
        self.items[document.id] = document
        return document

    async def get(self, document_id):
        return self.items.get(document_id)

    async def find_by_sha256(self, *, knowledge_base_id, content_sha256):
        for document in self.items.values():
            if (
                document.knowledge_base_id == knowledge_base_id
                and document.content_sha256 == content_sha256
            ):
                return document
        return None

    async def list_by_knowledge_base(self, knowledge_base_id, *, status=None, limit=200):
        documents = [
            document
            for document in self.items.values()
            if document.knowledge_base_id == knowledge_base_id
            and (status is None or document.status is status)
        ]
        return documents[:limit]

    async def count_by_knowledge_base(self, knowledge_base_id) -> int:
        return len(await self.list_by_knowledge_base(knowledge_base_id))

    async def set_status(self, document_id, *, status, chunk_count=None, error=None):
        document = self.items.get(document_id)
        if document is None:
            return None
        document.status = status
        if chunk_count is not None:
            document.chunk_count = chunk_count
        if error is not None:
            document.error = error
        return document

    async def delete(self, document_id):
        return self.items.pop(document_id, None)


class FakeKnowledgeChunkRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, KnowledgeChunk] = {}

    async def add_many(self, chunks):
        for chunk in chunks:
            self.items[chunk.id] = chunk
        return list(chunks)

    async def get_many(self, chunk_ids):
        return [self.items[chunk_id] for chunk_id in chunk_ids if chunk_id in self.items]

    async def count_by_knowledge_base(self, knowledge_base_id) -> int:
        return sum(
            1 for chunk in self.items.values() if chunk.knowledge_base_id == knowledge_base_id
        )

    async def delete_by_document(self, document_id) -> int:
        doomed = [
            chunk_id
            for chunk_id, chunk in self.items.items()
            if chunk.document_id == document_id
        ]
        for chunk_id in doomed:
            del self.items[chunk_id]
        return len(doomed)

    async def delete_by_knowledge_base(self, knowledge_base_id) -> int:
        doomed = [
            chunk_id
            for chunk_id, chunk in self.items.items()
            if chunk.knowledge_base_id == knowledge_base_id
        ]
        for chunk_id in doomed:
            del self.items[chunk_id]
        return len(doomed)


class FakeControlPlaneRepository:
    def __init__(self) -> None:
        self.traces: list[dict] = []

    async def record_retrieval_trace(self, payload: dict) -> None:
        self.traces.append(payload)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.db_session = None
        self.knowledge_bases = FakeKnowledgeBaseRepository()
        self.knowledge_documents = FakeKnowledgeDocumentRepository()
        self.knowledge_chunks = FakeKnowledgeChunkRepository()
        self.control_plane = FakeControlPlaneRepository()
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


def build_service() -> tuple[RagService, FakeUnitOfWork, InMemoryVectorStore]:
    uow = FakeUnitOfWork()
    store = InMemoryVectorStore()
    service = RagService(
        uow,
        vector_store=store,
        embedding_provider=HashingEmbeddingProvider(dim=128),
    )
    return service, uow, store


class RagServiceTests(unittest.TestCase):
    """覆盖摄取 → 检索 → 引用 → 删除的完整闭环。"""

    def test_ingest_marks_document_ready_and_indexes_chunks(self) -> None:
        async def scenario() -> None:
            service, uow, store = build_service()
            knowledge_base = await service.create_knowledge_base(name="工程知识库")
            document = await service.ingest_document(
                knowledge_base.id,
                title="部署手册",
                content="生产部署使用 Docker Compose。\n\n数据库迁移由 Alembic 负责。",
            )
            self.assertIs(document.status, KnowledgeDocumentStatus.ready)
            self.assertGreater(document.chunk_count, 0)
            self.assertEqual(len(store.records), document.chunk_count)
            refreshed = await service.get_knowledge_base(knowledge_base.id)
            self.assertEqual(refreshed.document_count, 1)

        asyncio.run(scenario())

    def test_duplicate_content_is_rejected(self) -> None:
        async def scenario() -> None:
            service, _, _ = build_service()
            knowledge_base = await service.create_knowledge_base(name="去重")
            await service.ingest_document(
                knowledge_base.id, title="A", content="同样的内容"
            )
            with self.assertRaises(AppException) as context:
                await service.ingest_document(
                    knowledge_base.id, title="B", content="同样的内容"
                )
            self.assertEqual(context.exception.status_code, 409)

        asyncio.run(scenario())

    def test_query_returns_cited_chunks_and_records_trace(self) -> None:
        async def scenario() -> None:
            service, uow, _ = build_service()
            knowledge_base = await service.create_knowledge_base(name="检索")
            await service.ingest_document(
                knowledge_base.id,
                title="数据库运维",
                content="数据库迁移使用 Alembic 管理，回滚需要 downgrade 脚本。",
            )
            await service.ingest_document(
                knowledge_base.id,
                title="前端规范",
                content="组件命名使用大驼峰，样式使用设计令牌。",
            )
            result = await service.query(
                knowledge_base.id, query="Alembic 数据库迁移怎么回滚", top_k=3
            )
            self.assertGreater(len(result.chunks), 0)
            top = result.chunks[0]
            self.assertEqual(top.document_title, "数据库运维")
            self.assertTrue(top.citation.startswith("[1]"))
            self.assertIn("[1]", result.context_text)
            self.assertEqual(len(uow.control_plane.traces), 1)
            self.assertEqual(uow.control_plane.traces[0]["plan"]["channels"], ["vector", "lexical"])

        asyncio.run(scenario())

    def test_failed_ingestion_marks_document_failed(self) -> None:
        async def scenario() -> None:
            class ExplodingStore(InMemoryVectorStore):
                async def upsert(self, records) -> int:
                    raise RuntimeError("vector backend down")

            uow = FakeUnitOfWork()
            service = RagService(
                uow,
                vector_store=ExplodingStore(),
                embedding_provider=HashingEmbeddingProvider(dim=64),
            )
            knowledge_base = await service.create_knowledge_base(name="失败路径")
            document = await service.ingest_document(
                knowledge_base.id, title="doc", content="任何内容"
            )
            self.assertIs(document.status, KnowledgeDocumentStatus.failed)
            self.assertIn("vector backend down", document.error)

        asyncio.run(scenario())

    def test_delete_document_removes_vectors(self) -> None:
        async def scenario() -> None:
            service, _, store = build_service()
            knowledge_base = await service.create_knowledge_base(name="删除")
            document = await service.ingest_document(
                knowledge_base.id, title="doc", content="要被删除的内容"
            )
            self.assertGreater(len(store.records), 0)
            await service.delete_document(document.id)
            self.assertEqual(len(store.records), 0)

        asyncio.run(scenario())

    def test_query_ignores_documents_that_are_not_ready(self) -> None:
        async def scenario() -> None:
            service, uow, _ = build_service()
            knowledge_base = await service.create_knowledge_base(name="状态过滤")
            document = await service.ingest_document(
                knowledge_base.id, title="doc", content="唯一内容片段"
            )
            await uow.knowledge_documents.set_status(
                document.id, status=KnowledgeDocumentStatus.failed
            )
            result = await service.query(knowledge_base.id, query="唯一内容片段")
            self.assertEqual(result.chunks, [])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
