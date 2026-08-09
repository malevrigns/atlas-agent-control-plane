"""VectorStore 抽象接口。

应用层只依赖这个协议，不关心向量到底存在 PostgreSQL(pgvector)
还是独立的 Qdrant 服务。生产系统里这层抽象的价值在于：

- 可以按部署形态切换后端（内网单机用 pgvector，大规模用专用向量库）；
- 单元测试可以注入内存实现，不依赖任何外部服务；
- 迁移向量后端时业务代码零改动。
"""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(slots=True)
class VectorRecord:
    """写入向量存储的一条记录。

    只保存回链 id 与少量过滤字段，正文永远以数据库 chunk 表为准，
    避免向量库和事实源之间出现数据漂移。
    """

    chunk_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    embedding: list[float]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class VectorMatch:
    """一次相似度查询的命中项。score 统一为 0-1，越大越相似。"""

    chunk_id: UUID
    document_id: UUID
    score: float


class VectorStore(Protocol):
    """向量存储协议。所有实现必须保证按知识库隔离。"""

    backend_name: str

    async def ensure_ready(
        self,
        *,
        knowledge_base_id: UUID,
        embedding_dim: int,
    ) -> None:
        """准备好该知识库的存储结构（建表 / 建 collection / 建索引）。"""

        raise NotImplementedError

    async def upsert(self, records: list[VectorRecord]) -> int:
        """写入或覆盖向量记录，返回写入条数。"""

        raise NotImplementedError

    async def query(
        self,
        *,
        knowledge_base_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> list[VectorMatch]:
        """按余弦相似度返回 top_k 命中。"""

        raise NotImplementedError

    async def delete_document(
        self,
        *,
        knowledge_base_id: UUID,
        document_id: UUID,
    ) -> int:
        """删除某文档的全部向量，返回删除条数。"""

        raise NotImplementedError

    async def delete_knowledge_base(self, *, knowledge_base_id: UUID) -> int:
        """删除整个知识库的向量数据。"""

        raise NotImplementedError

    async def health(self) -> dict[str, object]:
        """返回后端健康信息，供状态接口与运维面板使用。"""

        raise NotImplementedError


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """纯 Python 余弦相似度，作为无 ANN 索引时的正确性兜底。"""

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 0.0
    # 余弦取值 [-1, 1]，线性映射到 [0, 1] 便于统一比较与展示。
    return (dot / (norm_left * norm_right) + 1) / 2
