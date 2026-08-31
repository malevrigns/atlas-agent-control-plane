"""可移植的 SQL 向量存储适配器。

挂在既有的 ``VectorStore`` 端口下，不新增抽象。存在的理由：
``PgVectorStore`` 的降级分支用了 ``CAST(... AS jsonb)``，那是 PostgreSQL
语法，SQLite 上直接报错。这里把「用普通 SQL 表存向量、在应用层算余弦」
这条路径写成方言中立的实现，让 RAG 链路在 SQLite 上也完整可用。

和 pgvector 的分工很清楚：

- 有 pgvector：``PgVectorStore`` 走 HNSW 近似最近邻，规模大也快；
- 没有：本适配器全表扫描 + 精确余弦。正确性相同，性能随向量数线性下降。

因此 ``health()`` 会如实上报 ``mode: exact_scan`` 和向量条数——运维看一眼
就知道当前是不是在吃全表扫描。
"""

import json
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rag.vector_store import VectorMatch, VectorRecord, cosine_similarity


class SqlVectorStore:
    """方言中立的向量存储：向量以 JSON 文本存放，检索在应用层完成。"""

    backend_name = "sql"

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def ensure_ready(
        self,
        *,
        knowledge_base_id: UUID,
        embedding_dim: int,
    ) -> None:
        """建表（若不存在）。

        不建 ANN 索引：没有向量扩展可用，索引也帮不上余弦排序。只按
        knowledge_base_id 建普通索引，缩小扫描范围。
        """

        await self.db_session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS knowledge_chunk_embeddings (
                    chunk_id CHAR(36) PRIMARY KEY,
                    document_id CHAR(36) NOT NULL,
                    knowledge_base_id CHAR(36) NOT NULL,
                    embedding TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        await self.db_session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_kce_kb "
                "ON knowledge_chunk_embeddings (knowledge_base_id)"
            )
        )

    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        # 先删后插：避免依赖各方言不同的 upsert 语法
        # （PostgreSQL 的 ON CONFLICT 与 MySQL 的 ON DUPLICATE KEY 不通用）。
        for record in records:
            await self.db_session.execute(
                text("DELETE FROM knowledge_chunk_embeddings WHERE chunk_id = :chunk_id"),
                {"chunk_id": str(record.chunk_id)},
            )
            await self.db_session.execute(
                text(
                    """
                    INSERT INTO knowledge_chunk_embeddings
                        (chunk_id, document_id, knowledge_base_id, embedding, embedding_dim)
                    VALUES
                        (:chunk_id, :document_id, :knowledge_base_id, :embedding, :embedding_dim)
                    """
                ),
                {
                    "chunk_id": str(record.chunk_id),
                    "document_id": str(record.document_id),
                    "knowledge_base_id": str(record.knowledge_base_id),
                    "embedding": json.dumps(record.embedding),
                    "embedding_dim": len(record.embedding),
                },
            )
        return len(records)

    async def query(
        self,
        *,
        knowledge_base_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> list[VectorMatch]:
        result = await self.db_session.execute(
            text(
                """
                SELECT chunk_id, document_id, embedding
                FROM knowledge_chunk_embeddings
                WHERE knowledge_base_id = :knowledge_base_id
                  AND embedding_dim = :dim
                """
            ),
            {"knowledge_base_id": str(knowledge_base_id), "dim": len(embedding)},
        )
        matches = [
            VectorMatch(
                chunk_id=self._as_uuid(row[0]),
                document_id=self._as_uuid(row[1]),
                score=cosine_similarity(embedding, self._as_vector(row[2])),
            )
            for row in result.fetchall()
        ]
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    async def delete_document(
        self,
        *,
        knowledge_base_id: UUID,
        document_id: UUID,
    ) -> int:
        result = await self.db_session.execute(
            text(
                """
                DELETE FROM knowledge_chunk_embeddings
                WHERE knowledge_base_id = :knowledge_base_id AND document_id = :document_id
                """
            ),
            {
                "knowledge_base_id": str(knowledge_base_id),
                "document_id": str(document_id),
            },
        )
        return int(cast(CursorResult, result).rowcount or 0)

    async def delete_knowledge_base(self, *, knowledge_base_id: UUID) -> int:
        result = await self.db_session.execute(
            text(
                "DELETE FROM knowledge_chunk_embeddings "
                "WHERE knowledge_base_id = :knowledge_base_id"
            ),
            {"knowledge_base_id": str(knowledge_base_id)},
        )
        return int(cast(CursorResult, result).rowcount or 0)

    async def health(self) -> dict[str, object]:
        result = await self.db_session.execute(
            text("SELECT count(*) FROM knowledge_chunk_embeddings")
        )
        count = int(result.scalar_one())
        return {
            "backend": self.backend_name,
            "native_vector": False,
            # 如实上报检索方式：全表精确扫描，随数据量线性变慢。
            "mode": "exact_scan",
            "vector_count": count,
        }

    @staticmethod
    def _as_uuid(value: object) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _as_vector(stored: object) -> list[float]:
        raw = json.loads(stored) if isinstance(stored, str) else stored
        return [float(item) for item in (raw or [])]
