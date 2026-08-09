import asyncio
import json
import unittest

import httpx

from app.core.exceptions import AppException
from app.infrastructure.rag.embeddings import (
    HashingEmbeddingProvider,
    OpenAICompatibleEmbeddingClient,
)


class HashingEmbeddingProviderTests(unittest.TestCase):
    """本地哈希向量：确定性、归一化、相近文本更相似。"""

    def setUp(self) -> None:
        self.provider = HashingEmbeddingProvider(dim=128)

    def test_same_text_produces_identical_vectors(self) -> None:
        first = asyncio.run(self.provider.embed_query("PostgreSQL 连接池配置"))
        second = asyncio.run(self.provider.embed_query("PostgreSQL 连接池配置"))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 128)

    def test_vectors_are_normalized(self) -> None:
        vector = asyncio.run(self.provider.embed_query("归一化检查"))
        norm = sum(value * value for value in vector) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_similar_texts_score_higher_than_unrelated(self) -> None:
        base = asyncio.run(self.provider.embed_query("数据库迁移使用 Alembic 管理"))
        similar = asyncio.run(self.provider.embed_query("Alembic 负责数据库迁移"))
        unrelated = asyncio.run(self.provider.embed_query("周末去爬山看日出"))

        def dot(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=True))

        self.assertGreater(dot(base, similar), dot(base, unrelated))

    def test_batch_matches_single(self) -> None:
        batch = asyncio.run(self.provider.embed_texts(["文本一", "文本二"]))
        single = asyncio.run(self.provider.embed_query("文本二"))
        self.assertEqual(batch[1], single)


class OpenAICompatibleEmbeddingClientTests(unittest.TestCase):
    """OpenAI 兼容客户端：批量、顺序还原与错误转换。"""

    def _client(self, handler) -> OpenAICompatibleEmbeddingClient:
        return OpenAICompatibleEmbeddingClient(
            api_key="test-key",
            base_url="https://embedding.example/v1",
            model="test-model",
            dim=0,
            timeout_seconds=5,
            batch_size=2,
            transport=httpx.MockTransport(handler),
        )

    def test_batches_and_restores_order(self) -> None:
        calls: list[list[str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            calls.append(payload["input"])
            # 故意乱序返回，客户端必须按 index 还原。
            data = [
                {"index": position, "embedding": [float(position), 1.0]}
                for position in reversed(range(len(payload["input"])))
            ]
            return httpx.Response(200, json={"data": data})

        client = self._client(handler)
        vectors = asyncio.run(client.embed_texts(["a", "b", "c"]))
        self.assertEqual(len(calls), 2)  # batch_size=2 → 两次请求
        self.assertEqual(vectors[0], [0.0, 1.0])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(client.dim, 2)  # dim=0 时从真实响应学习维度

    def test_provider_error_becomes_app_exception(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        client = self._client(handler)
        with self.assertRaises(AppException) as context:
            asyncio.run(client.embed_query("hello"))
        self.assertEqual(context.exception.status_code, 502)

    def test_mismatched_batch_size_is_rejected(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        client = self._client(handler)
        with self.assertRaises(AppException):
            asyncio.run(client.embed_query("hello"))


if __name__ == "__main__":
    unittest.main()
