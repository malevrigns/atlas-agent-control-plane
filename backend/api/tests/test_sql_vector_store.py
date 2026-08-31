"""SqlVectorStore 的行为验证（真实 SQLite，不打桩）。

用真库而不是替身，是因为这个适配器的价值恰恰在于「SQL 是方言中立的」。
如果把 SQLAlchemy 也 mock 掉，那就等于没验证要验证的东西。
"""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.rag.vector_store import VectorRecord
from app.infrastructure.rag.vector_stores.factory import (
    available_vector_backends,
    build_vector_store,
    resolve_backend_name,
)
from app.infrastructure.rag.vector_stores.sql import SqlVectorStore


class SqlVectorStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        path = Path(self._tempdir.name) / "rag.db"
        self._engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        self.addAsyncCleanup(self._engine.dispose)
        self._session_factory = async_sessionmaker(bind=self._engine, expire_on_commit=False)
        self.knowledge_base_id = uuid4()

    async def _store(self, db_session) -> SqlVectorStore:
        store = SqlVectorStore(db_session)
        await store.ensure_ready(
            knowledge_base_id=self.knowledge_base_id,
            embedding_dim=3,
        )
        return store

    def _record(self, embedding: list[float]) -> VectorRecord:
        return VectorRecord(
            chunk_id=uuid4(),
            document_id=uuid4(),
            knowledge_base_id=self.knowledge_base_id,
            embedding=embedding,
        )

    # ===================== 写入后能按相似度召回 =====================
    async def test_query_ranks_by_cosine_similarity(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            near = self._record([1.0, 0.0, 0.0])
            far = self._record([-1.0, 0.0, 0.0])
            await store.upsert([near, far])

            matches = await store.query(
                knowledge_base_id=self.knowledge_base_id,
                embedding=[1.0, 0.0, 0.0],
                top_k=2,
            )

            self.assertEqual([match.chunk_id for match in matches], [near.chunk_id, far.chunk_id])
            self.assertGreater(matches[0].score, matches[1].score)

    # ===================== upsert 覆盖同一 chunk 而不是插重复行 =====================
    async def test_upsert_replaces_existing_chunk(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            record = self._record([1.0, 0.0, 0.0])
            await store.upsert([record])
            record.embedding = [0.0, 1.0, 0.0]
            await store.upsert([record])

            health = await store.health()
            self.assertEqual(health["vector_count"], 1)

    # ===================== 维度不同的向量不会互相污染 =====================
    async def test_query_ignores_other_dimensions(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            await store.upsert([self._record([1.0, 0.0, 0.0])])
            await store.upsert([self._record([1.0, 0.0])])

            matches = await store.query(
                knowledge_base_id=self.knowledge_base_id,
                embedding=[1.0, 0.0],
                top_k=5,
            )

            self.assertEqual(len(matches), 1)

    # ===================== 知识库之间互相隔离 =====================
    async def test_query_is_scoped_to_knowledge_base(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            await store.upsert([self._record([1.0, 0.0, 0.0])])
            other = VectorRecord(
                chunk_id=uuid4(),
                document_id=uuid4(),
                knowledge_base_id=uuid4(),
                embedding=[1.0, 0.0, 0.0],
            )
            await store.upsert([other])

            matches = await store.query(
                knowledge_base_id=self.knowledge_base_id,
                embedding=[1.0, 0.0, 0.0],
                top_k=5,
            )

            self.assertEqual(len(matches), 1)

    # ===================== 删除文档与删除知识库 =====================
    async def test_delete_document_and_knowledge_base(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            record = self._record([1.0, 0.0, 0.0])
            await store.upsert([record, self._record([0.0, 1.0, 0.0])])

            removed = await store.delete_document(
                knowledge_base_id=self.knowledge_base_id,
                document_id=record.document_id,
            )
            self.assertEqual(removed, 1)

            removed_all = await store.delete_knowledge_base(
                knowledge_base_id=self.knowledge_base_id
            )
            self.assertEqual(removed_all, 1)
            health = await store.health()
            self.assertEqual(health["vector_count"], 0)

    # ===================== health 如实上报降级模式 =====================
    async def test_health_reports_exact_scan(self) -> None:
        async with self._session_factory() as db_session:
            store = await self._store(db_session)
            health = await store.health()

            self.assertEqual(health["backend"], "sql")
            self.assertFalse(health["native_vector"])
            self.assertEqual(health["mode"], "exact_scan")


class VectorStoreFactoryTests(unittest.IsolatedAsyncioTestCase):
    """auto 解析必须跟着方言走，否则会在 SQLite 上生成 PostgreSQL 语法。"""

    async def test_auto_resolves_to_sql_on_sqlite(self) -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        self.addAsyncCleanup(engine.dispose)
        async with async_sessionmaker(bind=engine)() as db_session:
            self.assertEqual(resolve_backend_name(db_session), "sql")
            self.assertEqual(build_vector_store(db_session).backend_name, "sql")

    def test_registry_exposes_known_backends(self) -> None:
        self.assertEqual(
            available_vector_backends(),
            ("pgvector", "qdrant", "sql"),
        )


if __name__ == "__main__":
    unittest.main()
