"""Qdrant 向量存储实现。

可选后端：适合向量规模超出单库承载、或需要独立扩缩容的场景。
通过 REST API 对接（不引入 qdrant-client 依赖），每个知识库
对应一个独立 collection，天然实现租户隔离。

启用方式：docker compose --profile qdrant up -d，
并设置 RAG_VECTOR_BACKEND=qdrant。
"""

from uuid import UUID

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.rag.vector_store import VectorMatch, VectorRecord


class QdrantVectorStore:
    """基于 Qdrant REST API 的向量存储。"""

    backend_name = "qdrant"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or settings.qdrant_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.qdrant_api_key.get_secret_value()
        self.timeout_seconds = timeout_seconds or settings.qdrant_timeout_seconds
        self._transport = transport

    @staticmethod
    def collection_name(knowledge_base_id: UUID) -> str:
        return f"atlas_kb_{str(knowledge_base_id).replace('-', '')}"

    def _client(self) -> httpx.AsyncClient:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self._transport,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        allow_missing: bool = False,
    ) -> dict:
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"qdrant request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc
        if response.status_code == 404 and allow_missing:
            return {}
        if response.status_code >= 400:
            raise AppException(
                message=f"qdrant returned HTTP {response.status_code}: {response.text[:200]}",
                code=502,
                status_code=502,
            )
        return response.json() if response.content else {}

    # ===================== 第1步：为知识库准备 collection =====================
    async def ensure_ready(
        self,
        *,
        knowledge_base_id: UUID,
        embedding_dim: int,
    ) -> None:
        name = self.collection_name(knowledge_base_id)
        existing = await self._request("GET", f"/collections/{name}", allow_missing=True)
        if existing.get("result"):
            return
        await self._request(
            "PUT",
            f"/collections/{name}",
            json_body={"vectors": {"size": embedding_dim, "distance": "Cosine"}},
        )

    # ===================== 第2步：写入向量点 =====================
    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        by_collection: dict[str, list[VectorRecord]] = {}
        for record in records:
            by_collection.setdefault(
                self.collection_name(record.knowledge_base_id), []
            ).append(record)
        for name, grouped in by_collection.items():
            await self._request(
                "PUT",
                f"/collections/{name}/points?wait=true",
                json_body={
                    "points": [
                        {
                            "id": str(record.chunk_id),
                            "vector": record.embedding,
                            "payload": {
                                "document_id": str(record.document_id),
                                "knowledge_base_id": str(record.knowledge_base_id),
                                **record.metadata,
                            },
                        }
                        for record in grouped
                    ]
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
        name = self.collection_name(knowledge_base_id)
        payload = await self._request(
            "POST",
            f"/collections/{name}/points/search",
            json_body={
                "vector": embedding,
                "limit": top_k,
                "with_payload": True,
            },
            allow_missing=True,
        )
        matches: list[VectorMatch] = []
        for point in payload.get("result") or []:
            point_payload = point.get("payload") or {}
            matches.append(
                VectorMatch(
                    chunk_id=UUID(str(point.get("id"))),
                    document_id=UUID(str(point_payload.get("document_id"))),
                    # Qdrant Cosine 相似度取值 [-1,1]，映射到 [0,1] 与其他后端对齐。
                    score=max(0.0, min(1.0, (float(point.get("score", 0.0)) + 1) / 2)),
                )
            )
        return matches

    # ===================== 第4步：删除与健康检查 =====================
    async def delete_document(
        self,
        *,
        knowledge_base_id: UUID,
        document_id: UUID,
    ) -> int:
        name = self.collection_name(knowledge_base_id)
        await self._request(
            "POST",
            f"/collections/{name}/points/delete?wait=true",
            json_body={
                "filter": {
                    "must": [
                        {"key": "document_id", "match": {"value": str(document_id)}}
                    ]
                }
            },
            allow_missing=True,
        )
        return 0

    async def delete_knowledge_base(self, *, knowledge_base_id: UUID) -> int:
        await self._request(
            "DELETE",
            f"/collections/{self.collection_name(knowledge_base_id)}",
            allow_missing=True,
        )
        return 0

    async def health(self) -> dict[str, object]:
        payload = await self._request("GET", "/collections", allow_missing=True)
        collections = [
            item.get("name")
            for item in (payload.get("result") or {}).get("collections") or []
        ]
        return {
            "backend": self.backend_name,
            "url": self.base_url,
            "collections": [name for name in collections if str(name).startswith("atlas_kb_")],
        }
