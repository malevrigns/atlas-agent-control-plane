"""VectorStore 工厂与后端注册表。

按 RAG_VECTOR_BACKEND 配置选择实现：

- ``auto``（推荐）：连 PostgreSQL 时用 pgvector，其他方言用可移植 SQL 实现；
- ``pgvector``：与业务数据同库，运维最简；
- ``qdrant``：独立向量服务，检索规模与过滤能力更强；
- ``sql``：方言中立，应用层精确余弦，单机 / SQLite 场景。

应用服务只调用这个工厂，切换后端不改一行业务代码。新增后端用
``register_vector_backend`` 注册，不必修改本文件。
"""

from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.rag.vector_store import VectorStore

VectorStoreBuilder = Callable[[AsyncSession], VectorStore]

_BACKENDS: dict[str, VectorStoreBuilder] = {}


def register_vector_backend(name: str, builder: VectorStoreBuilder) -> None:
    """注册一个向量后端实现。"""

    _BACKENDS[name.strip().lower()] = builder


def available_vector_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


def _build_pgvector(db_session: AsyncSession) -> VectorStore:
    from app.infrastructure.rag.vector_stores.pgvector import PgVectorStore

    return PgVectorStore(db_session)


def _build_qdrant(db_session: AsyncSession) -> VectorStore:
    from app.infrastructure.rag.vector_stores.qdrant import QdrantVectorStore

    return QdrantVectorStore()


def _build_sql(db_session: AsyncSession) -> VectorStore:
    from app.infrastructure.rag.vector_stores.sql import SqlVectorStore

    return SqlVectorStore(db_session)


register_vector_backend("pgvector", _build_pgvector)
register_vector_backend("qdrant", _build_qdrant)
register_vector_backend("sql", _build_sql)


def resolve_backend_name(db_session: AsyncSession) -> str:
    """把 ``auto`` 解析成具体后端。

    判据是数据库方言而不是「有没有装 pgvector 扩展」：扩展探测由
    PgVectorStore 自己在运行时做，并在扩展缺失时降级为应用层余弦。
    这里只需要保证不在非 PostgreSQL 方言上生成 PostgreSQL 语法。
    """

    configured = settings.rag_vector_backend.strip().lower()
    if configured != "auto":
        return configured
    dialect = _dialect_name(db_session)
    return "pgvector" if dialect == "postgresql" else "sql"


def _dialect_name(db_session: AsyncSession) -> str:
    """尽力探测方言名；拿不到时按空串处理。

    ``AsyncSession.bind`` 在未绑定引擎的会话上会抛异常（测试里注入的
    替身会话就是这种情况），所以这里不能假设它一定可读。
    """

    try:
        bind = db_session.get_bind()
    except Exception:  # noqa: BLE001 —— 探测失败按未知方言处理。
        return ""
    dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", "") or ""


def build_vector_store(db_session: AsyncSession) -> VectorStore:
    backend = resolve_backend_name(db_session)
    builder = _BACKENDS.get(backend)
    if builder is None:
        raise AppException(
            message=(
                f"unsupported RAG vector backend: {settings.rag_vector_backend}. "
                f"available: {', '.join(available_vector_backends())}, auto"
            ),
            code=500,
            status_code=500,
        )
    return builder(db_session)
