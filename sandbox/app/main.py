from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    # ===================== 第1步：初始化日志格式 =====================
    configure_logging()

    # ===================== 第2步：创建独立的 Sandbox FastAPI 应用 =====================
    app = FastAPI(
        title=settings.sandbox_app_name,
        version=settings.sandbox_version,
    )

    # ===================== 第3步：注册统一异常，并挂载 /api 路由 =====================
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.sandbox_api_prefix)
    return app


app = create_app()
