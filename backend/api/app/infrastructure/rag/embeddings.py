"""Embedding 基础设施实现。

提供两个实现：

- OpenAICompatibleEmbeddingClient：调用任何 OpenAI 兼容 /embeddings
  端点（OpenAI、通义千问、智谱、硅基流动、Ollama 等）；
- HashingEmbeddingProvider：确定性的本地 n-gram 哈希向量，
  未配置模型服务时的教学兜底，保证整条 RAG 链路离线可跑。

工厂函数 build_embedding_provider 依据配置选择实现。
"""

import hashlib
import math
import os
import re

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.llm_config import load_llm_config


class OpenAICompatibleEmbeddingClient:
    """OpenAI 兼容 embedding 客户端。

    与聊天客户端一样，只依赖 HTTP 协议约定，不绑定具体服务商。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        dim: int,
        timeout_seconds: float,
        batch_size: int = 16,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider_name = "openai_compatible"
        self.model_name = model
        self.dim = dim
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        # 测试可注入 httpx.MockTransport，不发真实网络请求。
        self._transport = transport

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # ===================== 第1步：分批请求，避免超过服务商单次上限 =====================
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        result = await self._embed_batch([text])
        return result[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        # ===================== 第2步：组装 /embeddings 请求体 =====================
        payload: dict[str, object] = {"model": self.model_name, "input": texts}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"embedding request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        if response.status_code >= 400:
            raise AppException(
                message=f"embedding provider returned HTTP {response.status_code}",
                code=502,
                status_code=502,
            )

        # ===================== 第3步：按 index 还原顺序并校验维度 =====================
        data = response.json().get("data") or []
        if len(data) != len(texts):
            raise AppException(
                message="embedding provider returned mismatched batch size",
                code=502,
                status_code=502,
            )
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors: list[list[float]] = []
        for item in ordered:
            vector = [float(value) for value in (item.get("embedding") or [])]
            if not vector:
                raise AppException(
                    message="embedding provider returned empty vector",
                    code=502,
                    status_code=502,
                )
            vectors.append(vector)
        # 首次调用时从真实返回值学习维度，配置里的 dim 只作校验提示。
        if self.dim <= 0:
            self.dim = len(vectors[0])
        return vectors


class HashingEmbeddingProvider:
    """确定性本地哈希向量。

    把中英文 n-gram 哈希散列到固定维度并做 L2 归一化。它没有语义
    理解能力，但满足三个教学与降级需求：同文本向量稳定、相近文本
    共享 n-gram 因而相似度更高、全流程无外部依赖。
    """

    _TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")
    _CHINESE_PATTERN = re.compile(r"[一-鿿]+")

    def __init__(self, *, dim: int = 256) -> None:
        self.provider_name = "local_hash"
        self.model_name = f"hashing-{dim}d"
        self.dim = dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for term in self._terms(text):
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[slot] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def _terms(self, text: str) -> list[str]:
        normalized = text.lower()
        terms = self._TOKEN_PATTERN.findall(normalized)
        for block in self._CHINESE_PATTERN.findall(normalized):
            for size in (1, 2, 3):
                if len(block) < size:
                    continue
                terms.extend(
                    block[index : index + size]
                    for index in range(len(block) - size + 1)
                )
        return terms


def build_embedding_provider():
    """按配置构建 embedding 实现。

    优先级：
    1. 显式配置 RAG_EMBEDDING_PROVIDER=local_hash 时强制使用本地实现；
    2. llm.yaml 中存在 embedding 节点且对应密钥存在时，使用远端服务；
    3. 其余情况降级为本地哈希向量并保持整条链路可用。
    """

    if settings.rag_embedding_provider == "local_hash":
        return HashingEmbeddingProvider(dim=settings.rag_embedding_dim)

    config = load_llm_config()
    embedding_config = config.embedding
    if embedding_config is not None:
        provider = config.providers.get(embedding_config.provider)
        if provider is not None:
            api_key = os.environ.get(provider.api_key_env or "", "")
            if api_key:
                return OpenAICompatibleEmbeddingClient(
                    api_key=api_key,
                    base_url=embedding_config.base_url or provider.base_url,
                    model=embedding_config.model,
                    dim=embedding_config.dim,
                    timeout_seconds=provider.timeout_seconds,
                    batch_size=embedding_config.batch_size,
                )
    return HashingEmbeddingProvider(dim=settings.rag_embedding_dim)
