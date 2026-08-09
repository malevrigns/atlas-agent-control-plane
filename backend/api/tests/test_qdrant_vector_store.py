import asyncio
import json
import unittest
from uuid import uuid4

import httpx

from app.core.exceptions import AppException
from app.domain.rag.vector_store import VectorRecord
from app.infrastructure.rag.vector_stores.qdrant import QdrantVectorStore


class QdrantVectorStoreTests(unittest.TestCase):
    """通过 MockTransport 验证 REST 协议编排，不依赖真实 Qdrant。"""

    def _store(self, handler) -> QdrantVectorStore:
        return QdrantVectorStore(
            base_url="http://qdrant.test:6333",
            api_key="secret",
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )

    def test_ensure_ready_creates_collection_once(self) -> None:
        requests: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"result": True})

        store = self._store(handler)
        kb_id = uuid4()
        asyncio.run(store.ensure_ready(knowledge_base_id=kb_id, embedding_dim=128))
        self.assertIn(("PUT", f"/collections/{store.collection_name(kb_id)}"), requests)

    def test_upsert_sends_points_with_payload(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "PUT":
                captured.update(json.loads(request.content))
            return httpx.Response(200, json={"result": {}})

        store = self._store(handler)
        kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()
        count = asyncio.run(
            store.upsert(
                [
                    VectorRecord(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        knowledge_base_id=kb_id,
                        embedding=[0.1, 0.2],
                        metadata={"seq": 0},
                    )
                ]
            )
        )
        self.assertEqual(count, 1)
        point = captured["points"][0]
        self.assertEqual(point["id"], str(chunk_id))
        self.assertEqual(point["payload"]["document_id"], str(doc_id))

    def test_query_maps_scores_to_unit_interval(self) -> None:
        kb_id, doc_id, chunk_id = uuid4(), uuid4(), uuid4()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": str(chunk_id),
                            "score": 1.0,
                            "payload": {"document_id": str(doc_id)},
                        }
                    ]
                },
            )

        store = self._store(handler)
        matches = asyncio.run(
            store.query(knowledge_base_id=kb_id, embedding=[0.1], top_k=3)
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].chunk_id, chunk_id)
        self.assertAlmostEqual(matches[0].score, 1.0)

    def test_server_error_becomes_app_exception(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        store = self._store(handler)
        with self.assertRaises(AppException) as context:
            asyncio.run(store.query(knowledge_base_id=uuid4(), embedding=[0.1], top_k=1))
        self.assertEqual(context.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
