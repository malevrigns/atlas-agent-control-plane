from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.agent_task_runner import AgentTaskRunner
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.task_queue import RedisAgentTaskQueue, create_redis_client
from app.presentation.http.router import api_router


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

    try:
        yield
    finally:
        # ===================== 第3步：应用关闭时释放后台任务和 Redis 连接 =====================
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
