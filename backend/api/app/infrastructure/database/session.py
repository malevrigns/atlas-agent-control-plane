from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def create_database_engine(url: str, *, echo: bool = False):
    """Build the async engine with dialect-specific pooling.

    PostgreSQL keeps a checked pool with pre-ping. SQLite (standalone /
    quickstart) cannot share QueuePool connections across greenlets; NullPool
    plus WAL/busy_timeout lets the API and the in-process task runner coexist
    on one file without "database is locked".
    """

    if is_sqlite_url(url):
        engine = create_async_engine(
            url,
            echo=echo,
            poolclass=NullPool,
            connect_args={"timeout": 30},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

        return engine

    return create_async_engine(url, echo=echo, pool_pre_ping=True)


engine = create_database_engine(settings.database_url, echo=settings.database_echo)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
