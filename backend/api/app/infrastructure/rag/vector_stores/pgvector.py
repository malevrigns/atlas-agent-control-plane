"""pgvector 向量存储实现。

默认后端：向量与业务数据同库存放，复用既有的备份、迁移与运维体系。
实现要点：

- 向量数据只通过本类的原生 SQL 读写，ORM 模型对向量零感知；
- 启动时探测 pgvector 扩展是否可用：可用时走 ``<=>`` 余弦距离
  并在首次写入时按维度补建 HNSW 索引；不可用时 embedding 列为
  JSONB，检索退回应用层余弦计算（正确性不变，性能降级）。
"""

import json
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rag.vector_store import VectorMatch, VectorRecord, cosine_similarity


class PgVectorStore:
    """基于 PostgreSQL 的向量存储。"""

    backend_name = "pgvector"

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self._native: bool | None = None

    # ===================== 第1步：探测原生 vector 列是否可用 =====================
    async def _is_native(self) -> bool:
        if self._native is not None:
            return self._native
        result = await self.db_session.execute(
            text(
                """
                SELECT udt_name FROM information_schema.columns
                WHERE table_name = 'knowledge_chunk_embeddings'
                  AND column_name = 'embedding'
                """
            )
        )
        row = result.fetchone()
        self._native = bool(row and row[0] == "vector")
        return self._native

    async def ensure_ready(
        self,
        *,
        knowledge_base_id: UUID,
        embedding_dim: int,
    ) -> None:
        """原生模式下按维度补建 HNSW 索引（存在则跳过）。

        向量表的 embedding 列是无类型修饰的 ``vector``，可以容纳
        不同知识库的不同维度；ANN 索引则按具体维度用表达式索引建立。
        """

        if not await self._is_native():
            return
        index_name = f"ix_kce_hnsw_{embedding_dim}"
        await self.db_session.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON knowledge_chunk_embeddings
                USING hnsw ((embedding::vector({int(embedding_dim)})) vector_cosine_ops)
                WHERE embedding_dim = {int(embedding_dim)}
                """
            )
        )

    # ===================== 第2步：写入向量记录 =====================
    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        native = await self._is_native()
        statement = text(
            """
            INSERT INTO knowledge_chunk_embeddings
                (chunk_id, document_id, knowledge_base_id, embedding, embedding_dim)
            VALUES
                (:chunk_id, :document_id, :knowledge_base_id, {placeholder}, :embedding_dim)
            ON CONFLICT (chunk_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_dim = EXCLUDED.embedding_dim
            """.format(placeholder="CAST(:embedding AS vector)" if native else "CAST(:embedding AS jsonb)")
        )
        for record in records:
            await self.db_session.execute(
                statement,
                {
                    "chunk_id": record.chunk_id,
                    "document_id": record.document_id,
                    "knowledge_base_id": record.knowledge_base_id,
                    "embedding": json.dumps(record.embedding),
                    "embedding_dim": len(record.embedding),
                },
            )
        return len(records)

    # ===================== 第3步：相似度查询 =====================
    async def query(
        self,
        *,
        knowledge_base_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> list[VectorMatch]:
        if await self._is_native():
            return await self._query_native(
                knowledge_base_id=knowledge_base_id,
                embedding=embedding,
                top_k=top_k,
            )
        return await self._query_fallback(
            knowledge_base_id=knowledge_base_id,
            embedding=embedding,
            top_k=top_k,
        )

    async def _query_native(
        self,
        *,
        knowledge_base_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> list[VectorMatch]:
        """使用 pgvector 的余弦距离算子，距离越小越相似。"""

        dim = len(embedding)
        result = await self.db_session.execute(
            text(
                f"""
                SELECT chunk_id, document_id,
                       1 - (embedding::vector({dim}) <=> CAST(:query AS vector({dim}))) AS cosine
                FROM knowledge_chunk_embeddings
                WHERE knowledge_base_id = :knowledge_base_id
                  AND embedding_dim = :dim
                ORDER BY embedding::vector({dim}) <=> CAST(:query AS vector({dim}))
                LIMIT :top_k
                """
            ),
            {
                "query": json.dumps(embedding),
                "knowledge_base_id": knowledge_base_id,
                "dim": dim,
                "top_k": top_k,
            },
        )
        return [
            VectorMatch(
                chunk_id=row[0],
                document_id=row[1],
                # pgvector 的余弦相似度取值 [-1,1]，映射到 [0,1] 与其他后端对齐。
                score=max(0.0, min(1.0, (float(row[2]) + 1) / 2)),
            )
            for row in result.fetchall()
        ]

    async def _query_fallback(
        self,
        *,
        knowledge_base_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> list[VectorMatch]:
        """无 pgvector 扩展时在应用层计算余弦，保证正确性。"""

        result = await self.db_session.execute(
            text(
                """
                SELECT chunk_id, document_id, embedding
                FROM knowledge_chunk_embeddings
                WHERE knowledge_base_id = :knowledge_base_id
                  AND embedding_dim = :dim
                """
            ),
            {"knowledge_base_id": knowledge_base_id, "dim": len(embedding)},
        )
        matches: list[VectorMatch] = []
        for row in result.fetchall():
            stored = row[2]
            vector = [float(v) for v in (json.loads(stored) if isinstance(stored, str) else stored)]
            matches.append(
                VectorMatch(
                    chunk_id=row[0],
                    document_id=row[1],
                    score=cosine_similarity(embedding, vector),
                )
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    # ===================== 第4步：删除与健康检查 =====================
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
            {"knowledge_base_id": knowledge_base_id, "document_id": document_id},
        )
        return int(cast(CursorResult, result).rowcount or 0)

    async def delete_knowledge_base(self, *, knowledge_base_id: UUID) -> int:
        result = await self.db_session.execute(
            text(
                "DELETE FROM knowledge_chunk_embeddings WHERE knowledge_base_id = :knowledge_base_id"
            ),
            {"knowledge_base_id": knowledge_base_id},
        )
        return int(cast(CursorResult, result).rowcount or 0)

    async def health(self) -> dict[str, object]:
        native = await self._is_native()
        result = await self.db_session.execute(
            text("SELECT count(*) FROM knowledge_chunk_embeddings")
        )
        return {
            "backend": self.backend_name,
            "native_vector": native,
            "mode": "hnsw_ann" if native else "app_side_cosine",
            "vector_count": int(result.scalar_one()),
        }
