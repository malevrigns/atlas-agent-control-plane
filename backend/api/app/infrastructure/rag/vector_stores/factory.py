"""VectorStore 工厂。

按 RAG_VECTOR_BACKEND 配置选择实现：

- pgvector（默认）：与业务数据同库，运维最简；
- qdrant：独立向量服务，检索规模与过滤能力更强。

应用服务只调用这个工厂，切换后端不改一行业务代码。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.infrastructure.rag.vector_stores.pgvector import PgVectorStore
from app.infrastructure.rag.vector_stores.qdrant import QdrantVectorStore


def build_vector_store(db_session: AsyncSession):
    backend = settings.rag_vector_backend.strip().lower()
    if backend == "pgvector":
        return PgVectorStore(db_session)
    if backend == "qdrant":
        return QdrantVectorStore()
    raise AppException(
        message=f"unsupported RAG vector backend: {settings.rag_vector_backend}",
        code=500,
        status_code=500,
    )
