"""EmbeddingProvider 抽象接口。

embedding 服务与聊天模型解耦：聊天可以走 DeepSeek，向量化可以走
任何 OpenAI 兼容 /embeddings 端点（OpenAI、通义、智谱、硅基流动等）。
未配置密钥时降级为本地哈希向量，保证教学环境零依赖可运行。
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """向量化协议。实现必须保证同一文本返回稳定同维向量。"""

    provider_name: str
    model_name: str
    dim: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。返回值与输入一一对应。"""

        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        """查询向量化。部分模型对 query/document 使用不同前缀。"""

        raise NotImplementedError
