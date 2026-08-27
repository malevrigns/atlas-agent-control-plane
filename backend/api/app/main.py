import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.agent_task_runner import AgentTaskRunner
from app.core.auth import ApiKeyMiddleware
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.domain.memories.lifecycle import MemoryLifecycleService
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.repositories.memory_repository import SqlAlchemyAgentMemoryRepository
from app.infrastructure.task_queue import RedisAgentTaskQueue, create_redis_client
from app.presentation.http.router import api_router

_LOGGER = logging.getLogger(__name__)


async def _reset_stale_running_sessions() -> None:
    """启动时把上次异常退出遗留的 running 会话重置回 idle。"""

    try:
        from sqlalchemy import update

        from app.infrastructure.database.models.session import SessionModel

        async with AsyncSessionLocal() as db_session:
            await db_session.execute(
                update(SessionModel)
                .where(SessionModel.status == "running")
                .values(status="idle")
            )
            await db_session.commit()
    except Exception:  # noqa: BLE001 —— 清理失败不阻断启动。
        return

async def _memory_lifecycle_loop(session_factory) -> None:
    """后台周期性执行记忆衰减与巩固。

    参考 AgentTaskRunner 的后台任务模式：启动时注册 asyncio 任务，
    关闭时取消。单次执行失败只记日志，不中断循环。
    """
    while True:
        await asyncio.sleep(settings.memory_lifecycle_interval_seconds)
        try:
            async with session_factory() as db_session:
                service = MemoryLifecycleService(
                    SqlAlchemyAgentMemoryRepository(db_session),
                    commit=db_session.commit,
                )
                await service.run_lifecycle()
        except Exception:  # noqa: BLE001 —— 生命周期任务失败不阻断应用。
            _LOGGER.exception("memory lifecycle run failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===================== 第1步：创建 Redis 连接和任务队列 =====================
    redis = create_redis_client()
    queue = RedisAgentTaskQueue(redis)

    # ===================== 第2步：启动 AgentTaskRunner 后台循环 =====================
    runner = AgentTaskRunner(queue=queue, session_factory=AsyncSessionLocal)
    app.state.task_queue = queue
    app.state.task_runner = runner
    await redis.ping()
    runner.start()
    await _reset_stale_running_sessions()

    # ===================== 第3步：注册记忆生命周期后台任务 =====================
    memory_lifecycle_task: asyncio.Task | None = None
    if settings.memory_decay_enabled:
        memory_lifecycle_task = asyncio.create_task(_memory_lifecycle_loop(AsyncSessionLocal))
        app.state.memory_lifecycle_task = memory_lifecycle_task

    try:
        yield
    finally:
        # ===================== 第4步：应用关闭时释放后台任务和 Redis 连接 =====================
        if memory_lifecycle_task is not None:
            memory_lifecycle_task.cancel()
            try:
                await memory_lifecycle_task
            except asyncio.CancelledError:
                pass
        await runner.stop()
        await redis.aclose()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.api_app_name,
        version=settings.api_version,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(ApiKeyMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
