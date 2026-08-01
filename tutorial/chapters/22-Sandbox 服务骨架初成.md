# 第二十二章. Sandbox 服务骨架初成

## 22.1 本章目标
​        学完本章后，你应该能把 Agent 系统里的“业务编排”和“执行环境”分开看待。
​        前面章节已经让主 API 拥有了会话、任务、计划、事件和上下文能力，但这些能力仍然主要发生在业务层。真正的 Agent 一旦开始执行工具，就会碰到文件、命令、浏览器、截图、下载和进程管理。它们不适合直接塞进主 API 进程里，因为执行环境越复杂，主 API 越容易被阻塞、污染或拖垮。
​        因此，本章的目标不是马上做一个很强的工具系统，而是先搭出 Sandbox 服务骨架。你会创建一个独立的 FastAPI 沙箱服务，为它准备 `pydantic-settings` 配置、统一响应、统一异常、状态检查接口和 Supervisor 状态接口，再把它接入 Docker Compose 与 Nginx。到这一章结束时，项目会从“一个主 API 加前端”走向“主 API 负责调度，Sandbox 负责执行环境”的多服务架构。

## 22.2 最终效果
​        本章结束后，项目会新增一个独立服务：

```Plain
sandbox/
```

​        本地访问：

```Plain
http://localhost:8100/api/status
http://localhost:8100/api/supervisor/services
```

​        通过 Nginx 访问：

```Plain
http://localhost:8088/sandbox-api/status
http://localhost:8088/sandbox-api/supervisor/services
```

​        返回格式仍然使用统一响应：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "service": "AtlasAgent Sandbox",
    "environment": "development",
    "status": "ok",
    "version": "0.1.0",
    "workspace_dir": "/workspace"
  }
}
```

## 22.3 本章要解决的问题
​        前面章节的 Agent 已经能生成计划、执行步骤、管理任务和整理上下文。
​        但真正的 Agent 不只是在内存里“想”和“写事件”，它还需要和外部环境交互：

```Plain
读写文件
执行 Shell 命令
运行 Python / Node.js 代码
打开浏览器
截图
下载文件
```

​        这些动作不能直接放在主 API 服务里随便执行。
​        Shell 命令可能长时间运行，甚至因为外部进程卡住而占住请求；文件操作必须被限制在明确的工作目录里，否则 Agent 很容易越过项目边界；浏览器自动化又需要 Chrome、Xvfb、VNC、websockify 等额外进程配合。主 API 如果同时承担这些职责，就会从业务调度中心变成一个混杂的执行容器，后续排查问题也会非常困难。
​        所以从本章开始，项目进入第 5 阶段：沙箱与内置工具。本章先搭建沙箱服务骨架，不急着实现文件和 Shell。先把服务边界、配置、响应、异常、Docker 和网关跑通，后面章节再在这个骨架上逐步加入真正的执行能力。

## 22.4 本章技术方案
​        本章新增一个独立 FastAPI 应用：

```Plain
浏览器 / 主 API
  |
  v
Nginx
  |
  +-- /api         -> api:8000
  +-- /sandbox-api -> sandbox:8100
```

​        沙箱服务自身结构：

```Plain
sandbox/app
  |
  +-- core       配置、日志、异常
  +-- schemas    响应模型
  +-- services   Supervisor 状态读取
  +-- api        路由
  +-- main.py    FastAPI 入口
```

​        本章会先把最小可运行链路打通。`GET /api/status` 用来确认沙箱服务已经启动并能读取配置，`GET /api/supervisor/services` 用来提前固定进程状态接口的返回结构，`sandbox/Dockerfile` 负责构建独立镜像，`docker-compose.yml` 负责把 `sandbox` 放进整体服务编排，`nginx/default.conf` 则负责把外部的 `/sandbox-api` 转发到沙箱容器内部的 `/api`。
​        本章也会刻意保留边界，不在这里实现文件 API、Shell API、真实 Supervisor、Chrome 或 VNC。这些能力都依赖一个稳定的沙箱服务入口，提前把它们全塞进来只会让第一版边界变得模糊。先让服务能独立启动、独立配置、独立被网关访问，后续章节再逐步把工具能力接上来。

## 22.5 新增和修改的文件

```Plain
.env.example
README.md
docker-compose.yml
docs/course/chapters/22-sandbox-service.md
nginx/README.md
nginx/default.conf
sandbox/.dockerignore
sandbox/Dockerfile
sandbox/README.md
sandbox/pyproject.toml
sandbox/uv.lock
sandbox/app/__init__.py
sandbox/app/api/__init__.py
sandbox/app/api/router.py
sandbox/app/api/routes/__init__.py
sandbox/app/api/routes/status.py
sandbox/app/api/routes/supervisor.py
sandbox/app/core/config.py
sandbox/app/core/exceptions.py
sandbox/app/core/handlers.py
sandbox/app/core/logging.py
sandbox/app/main.py
sandbox/app/schemas/common.py
sandbox/app/schemas/status.py
sandbox/app/schemas/supervisor.py
sandbox/app/services/__init__.py
sandbox/app/services/supervisor_service.py
```

## 22.6 实施步骤
### 22.6.1 创建 Sandbox 依赖配置
​        在 `sandbox/` 目录创建 `pyproject.toml`：

```TOML
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "atlas-agents-sandbox"
version = "0.1.0"
description = "Sandbox API service for AtlasAgent."
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115,<1.0",
  "pydantic-settings>=2.7,<3.0",
  "uvicorn[standard]>=0.34,<1.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

​        进入 `sandbox` 目录生成锁文件：

```Bash
cd sandbox
uv lock
```

​        执行后会生成：

```Plain
sandbox/uv.lock
```

#### 22.6.1.1 字段含义
​        `name` 写成 `atlas-agents-sandbox`，是为了和主 API 的 Python 包区分开。它不是主 API 的一个子模块，而是一个可以独立安装、独立启动、独立构建镜像的服务。
​        `requires-python` 约束运行时版本，`dependencies` 只放本章真正需要的 FastAPI、配置读取和 Uvicorn。这里暂时不引入文件、Shell、浏览器相关依赖，是为了让骨架阶段保持轻量。`where = ["."]` 和 `include = ["app*"]` 则告诉 setuptools 只从当前 `sandbox` 目录收集 `app` 包，避免把仓库里其他服务误纳入沙箱包。

#### 22.6.1.2 为什么这样设计
​        沙箱服务和主 API 是两个独立应用。
​        它们以后会有不同依赖：主 API 关注数据库、Redis、LLM；沙箱会关注文件、Shell、浏览器和进程管理。
​        所以本章不复用 `api/pyproject.toml`，而是给 `sandbox/` 自己创建一套依赖配置。

### 22.6.2 创建沙箱配置
​        创建 `sandbox/app/__init__.py`：

```Python
"""AtlasAgent sandbox service."""
```

​        创建 `sandbox/app/core/config.py`：

```Python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----- 基础服务信息：用于 /api/status 和接口文档 -----
    sandbox_app_name: str = "AtlasAgent Sandbox"
    sandbox_env: str = "development"
    sandbox_version: str = "0.1.0"
    sandbox_api_prefix: str = "/api"
    log_level: str = "INFO"

    # ----- 沙箱工作目录：后续文件、Shell、浏览器下载都限制在这里 -----
    workspace_dir: str = "/workspace"

    # ----- Supervisor：本章先固定接口形状，后续再接真实进程管理 -----
    supervisor_enabled: bool = False
    supervisor_services: list[str] = ["sandbox-api"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # 配置对象只创建一次，避免每次请求都重新解析环境变量。
    return Settings()


settings = get_settings()
```

#### 22.6.2.1 字段含义
​        这些配置先把沙箱服务的身份写清楚。`sandbox_app_name`、`sandbox_env` 和 `sandbox_version` 会体现在状态接口里，后续排查 Docker 镜像、环境变量或网关代理时，可以直接从接口返回判断当前访问到的是哪一个服务、哪一个环境、哪一个版本。
​        `sandbox_api_prefix` 表示沙箱服务内部的 API 前缀，本章保持为 `/api`。外部用户通过 Nginx 访问的是 `/sandbox-api`，容器内部服务看到的仍然是 `/api`，这可以让沙箱代码不用关心网关层路径。`workspace_dir` 是后续文件读写和 Shell 执行的根目录，先把它固定下来，之后所有执行能力才有边界可依。`supervisor_enabled` 和 `supervisor_services` 则为进程管理预留入口，本章先让它返回可解释状态，后面再接真实 Supervisor。

#### 22.6.2.2 代码讲解
​        `Settings` 和主 API 的配置方式保持一致，都是用 `pydantic-settings` 从环境变量读取配置。
​        `get_settings()` 使用 `lru_cache`，表示配置只创建一次。后续路由和服务都可以直接使用同一个 `settings` 对象，不需要每次请求重新解析环境变量。
​        `workspace_dir` 是第 22 章最重要的配置之一。虽然本章还没有文件 API，但后续所有文件读写都必须落在这个目录下，避免 Agent 随意访问容器里的任意路径。

### 22.6.3 创建统一响应和异常处理
​        创建 `sandbox/app/schemas/common.py`：

```Python
from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    code: int = 200
    message: str = "success"
    data: DataT | None = None
```

​        创建 `sandbox/app/core/exceptions.py`：

```Python
class SandboxException(Exception):
    def __init__(
        self,
        message: str,
        code: int = 400,
        status_code: int = 400,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)
```

​        创建 `sandbox/app/core/logging.py`：

```Python
import logging

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
```

​        创建 `sandbox/app/core/handlers.py`：

```Python
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.exceptions import SandboxException
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)


def build_error_response(code: int, message: str, status_code: int) -> JSONResponse:
    payload = ApiResponse[None](code=code, message=message, data=None)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def sandbox_exception_handler(
    request: Request,
    exc: SandboxException,
) -> JSONResponse:
    logger.warning("sandbox business error: %s %s", request.url.path, exc.message)
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    logger.warning("sandbox http error: %s %s", request.url.path, exc.detail)
    return build_error_response(
        code=exc.status_code,
        message=str(exc.detail),
        status_code=exc.status_code,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning("sandbox validation error: %s %s", request.url.path, exc.errors())
    return build_error_response(
        code=422,
        message="request validation failed",
        status_code=422,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("sandbox unhandled error: %s", request.url.path)
    return build_error_response(
        code=500,
        message="internal server error",
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SandboxException, sandbox_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
```

#### 22.6.3.1 字段含义
​        统一响应里有两层含义。`code` 和 `message` 是业务层的表达，告诉调用方这次请求在应用语义上是否成功；`data` 承载真正的返回数据，异常时通常就是 `null`。HTTP 的 `status_code` 则保留在响应对象之外，用来控制客户端看到的协议层状态。
​        这样设计的好处是，主 API、前端和后续工具调用都能用同一种方式理解沙箱结果。比如文件工具调用失败时，主 API 不需要猜测沙箱到底返回了什么结构，只需要读取 `code`、`message` 和 `data`，再决定是否把错误写入 Agent 事件流。

#### 22.6.3.2 代码讲解
​        这套结构和主 API 保持一致。
​        原因是前端或主 API 调用沙箱服务时，不需要适配另一套奇怪的错误格式。
​        统一响应不是为了“好看”，而是为了降低联调成本。比如后续主 API 调用沙箱文件接口失败时，可以直接读取：

```Plain
code
message
data
```

​        而不是每个接口都猜一次错误结构。

### 22.6.4 创建状态接口
​        创建 `sandbox/app/schemas/status.py`：

```Python
from pydantic import BaseModel


class SandboxStatusResponse(BaseModel):
    service: str  # 确认当前访问的是 Sandbox 服务，而不是主 API。
    environment: str  # 当前运行环境，例如 development。
    status: str  # 健康状态，本章正常时固定返回 ok。
    version: str  # 沙箱服务版本，方便排查镜像是否更新。
    workspace_dir: str  # 沙箱工作目录，后续文件和 Shell 都围绕它运行。
```

​        创建 `sandbox/app/api/__init__.py`：

```Python
"""Sandbox API routes."""
```

​        创建 `sandbox/app/api/routes/__init__.py`：

```Python
"""Sandbox route modules."""
```

​        创建 `sandbox/app/api/routes/status.py`：

```Python
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.status import SandboxStatusResponse

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=ApiResponse[SandboxStatusResponse])
async def get_status() -> ApiResponse[SandboxStatusResponse]:
    # 状态接口只读取配置，不访问文件系统或外部进程，适合作为最小健康检查。
    return ApiResponse(
        data=SandboxStatusResponse(
            service=settings.sandbox_app_name,
            environment=settings.sandbox_env,
            status="ok",
            version=settings.sandbox_version,
            workspace_dir=settings.workspace_dir,
        )
    )
```

#### 22.6.4.1 字段含义
​        状态接口返回的是沙箱服务的最小身份信息。`service` 用来确认当前命中的确实是 Sandbox，而不是主 API 或前端页面；`environment` 和 `version` 用来定位运行环境和镜像版本；`status` 在本章固定为 `ok`，表示 FastAPI 应用已经启动并完成基础配置读取；`workspace_dir` 则提前暴露沙箱工作目录，方便后续验证文件 API 和 Shell API 是否都围绕同一个目录运行。

#### 22.6.4.2 代码讲解
​        `/api/status` 是最小健康检查。
​        它的价值不只是“返回 ok”。当这个接口能稳定响应时，至少说明 Sandbox 应用已经启动、配置对象可以正常创建，并且你当前访问的端口或网关路径确实落到了沙箱服务上。后续只要沙箱 Dockerfile、Compose 网络或 Nginx 代理出问题，都可以先用这个接口判断问题发生在哪一层。
​        后续每次沙箱 Dockerfile 或 Nginx 代理出问题，都可以先从这个接口查。

### 22.6.5 创建 Supervisor 状态接口
​        创建 `sandbox/app/schemas/supervisor.py`：

```Python
from pydantic import BaseModel


class SupervisorServiceResponse(BaseModel):
    name: str  # 被 Supervisor 管理的进程名，例如 sandbox-api、chrome。
    status: str  # 进程状态，本章可能是 not_configured 或 unavailable。
    description: str  # 状态说明，帮助调用方理解为什么不是 running。


class SupervisorStatusResponse(BaseModel):
    enabled: bool  # 是否启用真实 supervisorctl 状态读取。
    services: list[SupervisorServiceResponse]  # 当前沙箱关注的进程状态列表。
```

​        创建 `sandbox/app/services/__init__.py`：

```Python
"""Sandbox application services."""
```

​        创建 `sandbox/app/services/supervisor_service.py`：

```Python
import shutil
import subprocess

from app.core.config import settings
from app.schemas.supervisor import SupervisorServiceResponse, SupervisorStatusResponse


class SupervisorService:
    """读取沙箱容器内的进程管理状态。

    第 22 章先把接口形状固定下来。
    如果容器里暂时没有 supervisorctl，就返回配置中的服务占位状态。
    """

    def list_services(self) -> SupervisorStatusResponse:
        # ===================== 第1步：Supervisor 未启用时返回占位状态 =====================
        if not settings.supervisor_enabled:
            return SupervisorStatusResponse(
                enabled=False,
                services=[
                    SupervisorServiceResponse(
                        name=name,
                        status="not_configured",
                        description="Supervisor will be enabled in later sandbox chapters.",
                    )
                    for name in settings.supervisor_services
                ],
            )

        # ===================== 第2步：启用了配置，但镜像里还没安装 supervisorctl =====================
        supervisorctl = shutil.which("supervisorctl")
        if supervisorctl is None:
            return SupervisorStatusResponse(
                enabled=True,
                services=[
                    SupervisorServiceResponse(
                        name=name,
                        status="unavailable",
                        description="supervisorctl is not installed in this image.",
                    )
                    for name in settings.supervisor_services
                ],
            )

        # ===================== 第3步：真实读取 supervisorctl status 输出 =====================
        completed = subprocess.run(
            [supervisorctl, "status"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        services = [
            self._parse_status_line(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        return SupervisorStatusResponse(enabled=True, services=services)

    @staticmethod
    def _parse_status_line(line: str) -> SupervisorServiceResponse:
        # supervisorctl 的一行输出通常是：进程名 状态 描述。
        parts = line.split(maxsplit=2)
        name = parts[0] if parts else "unknown"
        status = parts[1] if len(parts) > 1 else "unknown"
        description = parts[2] if len(parts) > 2 else ""
        return SupervisorServiceResponse(
            name=name,
            status=status.lower(),
            description=description,
        )
```

​        创建 `sandbox/app/api/routes/supervisor.py`：

```Python
from fastapi import APIRouter, Depends

from app.schemas.common import ApiResponse
from app.schemas.supervisor import SupervisorStatusResponse
from app.services.supervisor_service import SupervisorService

router = APIRouter(prefix="/supervisor", tags=["supervisor"])


def build_supervisor_service() -> SupervisorService:
    # 这里先直接创建 service；后续如果接入缓存或外部客户端，可以在这里统一替换。
    return SupervisorService()


@router.get(
    "/services",
    response_model=ApiResponse[SupervisorStatusResponse],
)
async def list_supervisor_services(
    service: SupervisorService = Depends(build_supervisor_service),
) -> ApiResponse[SupervisorStatusResponse]:
    # 返回统一响应，方便主 API 或前端用同一种格式消费沙箱状态。
    return ApiResponse(data=service.list_services())
```

#### 22.6.5.1 字段含义
​        `enabled` 表示沙箱是否尝试读取真实 Supervisor 状态。如果它是 `false`，说明当前只是占位接口，不会调用 `supervisorctl`。`services` 里的每一项描述一个被沙箱关注的进程，`name` 是进程名，`status` 是状态，`description` 则解释这个状态从哪里来。
​        本章常见状态是 `not_configured` 和 `unavailable`。前者表示配置上还没有启用真实 Supervisor，后者表示配置启用了，但当前镜像里没有安装 `supervisorctl`。等后续章节加入 Chrome、Xvfb、x11vnc 和 websockify 后，这个接口会开始返回更接近真实运行态的 `running`、`stopped` 等状态。

#### 22.6.5.2 代码讲解
​        本章没有真正安装 Supervisor，但先做接口。
​        原因是后续沙箱会越来越复杂，可能同时运行：

```Plain
sandbox-api
chrome
xvfb
x11vnc
websockify
```

​        这些进程不能只靠一个 Python 主进程管理。Supervisor 会负责拉起和管理它们。
​        本章先处理三种情况：

```Plain
supervisor_enabled = false
  -> 返回 not_configured

supervisor_enabled = true，但 supervisorctl 不存在
  -> 返回 unavailable

supervisor_enabled = true，且 supervisorctl 存在
  -> 执行 supervisorctl status
```

​        这样即使当前镜像还没安装 Supervisor，接口也不会报 500，而是返回可解释状态。

### 22.6.6 创建 API Router 和应用入口
​        创建 `sandbox/app/api/router.py`：

```Python
from fastapi import APIRouter

from app.api.routes import status, supervisor

api_router = APIRouter()
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
```

​        创建 `sandbox/app/main.py`：

```Python
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
```

#### 22.6.6.1 代码讲解
​        `api_router` 聚合所有沙箱路由。
​        `create_app()` 是沙箱服务的启动装配点。它先初始化日志格式，再创建独立的 FastAPI 实例，随后注册统一异常处理，并把聚合后的 `api_router` 挂载到配置里的 `/api` 前缀下。
​        这和主 API 的入口结构保持接近。这样后续读代码时，看到 `api/app/main.py` 和 `sandbox/app/main.py` 会有相同的理解方式。

### 22.6.7 编写 Sandbox Dockerfile
​        创建 `sandbox/.dockerignore`：

```Plain
.venv
__pycache__
*.pyc
.pytest_cache
*.log
```

​        创建 `sandbox/Dockerfile`：

```Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN uv sync --frozen --no-dev

EXPOSE 8100

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

#### 22.6.7.1 字段含义
​        这个 Dockerfile 的重点是让沙箱服务能以最小镜像独立运行。`PYTHONDONTWRITEBYTECODE` 避免容器里生成无意义的 `.pyc` 文件，`PYTHONUNBUFFERED` 让日志可以及时进入 `docker logs`，`UV_COMPILE_BYTECODE` 和 `UV_LINK_MODE=copy` 则让 `uv` 的依赖安装更适合容器层缓存。
​        镜像构建时先复制 `pyproject.toml`、`uv.lock` 和 `README.md`，再执行一次不安装项目本身的依赖同步，最后复制 `app/` 并完成最终同步。这样依赖层和代码层分开，后续只改业务代码时，不必每次都重新解析完整依赖。`EXPOSE 8100` 表示容器内的沙箱服务监听 8100 端口，Compose 和 Nginx 会围绕这个端口完成内部转发。

#### 22.6.7.2 代码讲解
​        这个 Dockerfile 和主 API 的结构类似，但更简单。
​        本章沙箱还没有 migrations、config、数据库等内容，所以镜像里只放入：

```Plain
pyproject.toml
uv.lock
README.md
app/
```

​        如果执行构建时报 `ghcr.io/astral-sh/uv:0.11.15` 拉取失败，那是网络访问 GitHub Container Registry 的问题，不是沙箱代码错误。可以先用本地 `uv run` 验证服务。

### 22.6.8 接入 Docker Compose
​        打开 `.env.example`，加入：

```Plain
# Sandbox service defaults.
SANDBOX_APP_NAME=AtlasAgent Sandbox
SANDBOX_ENV=development
SANDBOX_VERSION=0.1.0
SANDBOX_API_PREFIX=/api
SANDBOX_WORKSPACE_DIR=/workspace
SUPERVISOR_ENABLED=false
SUPERVISOR_SERVICES=["sandbox-api"]
```

​        打开 `docker-compose.yml`，在 `services` 下新增：

```YAML
  sandbox:
    build:
      context: ./sandbox
    container_name: atlas-sandbox
    restart: unless-stopped
    environment:
      SANDBOX_APP_NAME: ${SANDBOX_APP_NAME:-AtlasAgent Sandbox}
      SANDBOX_ENV: ${SANDBOX_ENV:-development}
      SANDBOX_VERSION: ${SANDBOX_VERSION:-0.1.0}
      SANDBOX_API_PREFIX: ${SANDBOX_API_PREFIX:-/api}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      WORKSPACE_DIR: ${SANDBOX_WORKSPACE_DIR:-/workspace}
      SUPERVISOR_ENABLED: ${SUPERVISOR_ENABLED:-false}
      SUPERVISOR_SERVICES: ${SUPERVISOR_SERVICES:-["sandbox-api"]}
    volumes:
      - sandbox_workspace:/workspace
    expose:
      - "8100"
    networks:
      - atlas-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/status').read()"]
      interval: 10s
      timeout: 5s
      retries: 5
```

​        在 `nginx.depends_on` 中加入：

```YAML
    depends_on:
      - ui
      - api
      - sandbox
```

​        在 `volumes` 中加入：

```YAML
sandbox_workspace:
```

#### 22.6.8.1 代码讲解
​        `sandbox_workspace` 是沙箱工作目录卷。
​        后续文件 API 和 Shell API 都会围绕 `/workspace` 运行。把它做成 Docker volume，是为了让沙箱工作目录拥有稳定的生命周期：容器重启时目录内容不会因为容器层被重建而消失，同时所有文件操作都集中在一个明确挂载点上。等 Agent 开始写文件、下载文件或运行命令时，这个目录就是执行结果最重要的边界。
​        `expose: "8100"` 表示这个端口只暴露给 Docker 网络里的其他服务。浏览器不直接访问 `8100`，而是通过 Nginx 的 `/sandbox-api` 访问。

### 22.6.9 接入 Nginx 网关
​        打开 `nginx/default.conf`，在 `/api` 规则后面加入：

```Nginx
location = /sandbox-api {
    proxy_pass http://sandbox:8100/api;
}

location /sandbox-api/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_pass http://sandbox:8100/api/;
}
```

​        同时更新 `nginx/README.md`：

```Plain
/sandbox-api   -> sandbox:8100/api
/sandbox-api/* -> sandbox:8100/api/*
```

#### 22.6.9.1 代码讲解
​        浏览器请求：

```Plain
http://localhost:8088/sandbox-api/status
```

​        Nginx 会转发到：

```Plain
http://sandbox:8100/api/status
```

​        这里故意把外部路径设计成 `/sandbox-api`，避免和主 API 的 `/api` 混在一起。
​        后续主 API 调用沙箱服务时，可以直接在 Docker 网络里请求：

```Plain
http://sandbox:8100/api/...
```

​        浏览器调试时则通过：

```Plain
/sandbox-api/...
```

## 22.7 关键理解
​        本章最重要的是服务边界。
​        主 API 负责的是业务编排：

```Plain
会话
任务
Agent 编排
数据库
LLM
```

​        Sandbox 负责的是执行环境：

```Plain
文件环境
Shell 环境
浏览器环境
进程状态
```

​        不要把 Shell、Chrome、VNC 这些执行环境塞进主 API。主 API 应该像调度中心，沙箱才是执行现场。
​        第二个重点是 Supervisor 接口先于真实 Supervisor 出现。
​        这不是多余代码，而是为了先固定协议：

```Plain
前端或主 API 问：沙箱里哪些服务在跑？
Sandbox 回答：enabled + services
```

​        后续安装真实 Supervisor 后，只需要替换服务状态来源，不需要改接口形状。

## 22.8 技术难点与亮点
​        本章的难点不在代码量，而在边界意识。Sandbox 是独立服务，就必须拥有自己的依赖配置、环境变量、启动入口、异常处理和健康检查。它不能一边声称独立，一边继续依赖主 API 的内部模块，否则后续工具执行出了问题，还是会牵扯到主 API 的运行环境。
​        另一个容易出错的地方是 Nginx 路径映射。外部路径是 `/sandbox-api`，沙箱服务内部路径是 `/api`，两者必须在网关层准确转换。如果这里写错，浏览器可能拿到 UI 的 404，也可能请求到主 API。Supervisor 接口同样体现了工程上的提前设计：即使本章还没安装 Supervisor，也要让调用方得到可解释状态，而不是让接口直接报 500。
​        这一章的亮点，是项目正式从单 API 架构扩展为多服务架构。Sandbox 有自己的统一响应、统一异常、健康检查、Dockerfile、Compose 服务和网关入口。后续文件工具、Shell 工具和浏览器工具不是凭空加到主 API 里，而是会落在这个已经划好边界的执行服务上。

## 22.9 面试考点
​        面试里如果被问到这一章，重点不是背出文件名，而是讲清服务拆分背后的理由。沙箱服务之所以要从主 API 中拆出去，是因为工具执行会带来文件系统、进程、浏览器和命令运行等复杂副作用，这些副作用应该被限制在专门的执行环境里。
​        `/api` 和 `/sandbox-api` 的区别也很容易被追问。`/api` 是服务内部前缀，主 API 和 Sandbox 都可以在各自服务内使用它；`/sandbox-api` 是网关对外暴露的路径，用来让浏览器和调试命令清楚区分访问目标。Docker Compose 里的 `expose` 只把端口暴露给内部网络，`ports` 才会映射到宿主机，这正好符合本章设计：外部统一走 Nginx，容器之间通过内部网络通信。
​        Supervisor 状态接口提前出现，是为了先固定协议形状。真实 Supervisor 可以晚一点安装，但主 API 和前端应该提前知道如何询问沙箱内的服务状态。`/workspace` 也是同样的道理，它不是随便取的目录，而是后续文件读写、命令执行和浏览器下载共同依赖的工作边界。

## 22.10 运行验证
​        下面命令默认在项目根目录执行。

### 22.10.1 检查沙箱代码编译

```Bash
cd sandbox
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

### 22.10.2 本地运行沙箱服务

```Bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8100
```

​        访问：

```Bash
curl http://localhost:8100/api/status
curl http://localhost:8100/api/supervisor/services
```

​        预期 `/api/status` 返回 `AtlasAgent Sandbox`。
​        预期 `/api/supervisor/services` 返回：

```Plain
enabled: false
status: not_configured
```

### 22.10.3 检查 Compose 配置
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose config
```

​        预期能看到：

```Plain
atlas-sandbox
sandbox_workspace
```

### 22.10.4 Docker Compose 运行
​        如果网络可以拉取 `ghcr.io/astral-sh/uv:0.11.15`：

```Bash
docker compose build sandbox
docker compose up -d sandbox nginx
```

​        通过 Nginx 验证：

```Bash
curl http://localhost:8088/sandbox-api/status
curl http://localhost:8088/sandbox-api/supervisor/services
```

​        如果构建时提示 `ghcr.io/astral-sh/uv:0.11.15` 拉取失败，先用本地 `uv run uvicorn` 验证本章代码。等网络恢复后再构建 Docker 镜像。

## 22.11 常见问题

### 22.11.1 为什么本章不直接做文件读写？
​        文件 API 依赖工作目录、安全边界和沙箱服务入口。如果服务本身还没有独立启动，也没有稳定网关路径，就急着加入读写接口，那么后续排查问题时很难判断错误到底来自文件逻辑、容器路径还是服务代理。
​        所以本章只先把 Sandbox 骨架跑通。等第 23 章实现文件 API 时，读者已经知道请求从浏览器到 Nginx，再到沙箱内部 `/api` 的完整路径，文件能力就可以专注在目录边界和读写语义上。

### 22.11.2 `/sandbox-api/status` 返回 502 怎么办？
​        502 通常说明 Nginx 已经收到了请求，但它转发到后端服务时失败了。第一步应该检查 `atlas-sandbox` 容器是否启动，第二步查看沙箱容器日志确认 Uvicorn 有没有正常监听 8100 端口。
​        如果 sandbox 镜像还没有构建成功，可以先在 `sandbox` 目录用 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8100` 验证代码本身。代码能本地启动后，再回到 Docker Compose 排查镜像构建、容器网络和 Nginx 重启问题。

### 22.11.3 `/sandbox-api/status` 返回 Next.js 的 404 页面怎么办？
​        这通常说明请求没有命中 Nginx 里的 `/sandbox-api` 代理规则，而是落到了最后的 UI 转发规则上。最常见原因是 Nginx 容器还在使用旧配置，或者修改了 `nginx/default.conf` 之后没有重启容器。
​        处理方式是执行 `docker compose restart nginx`，然后重新请求 `curl http://localhost:8088/sandbox-api/status`。如果仍然返回前端 404，就继续检查 `location = /sandbox-api` 和 `location /sandbox-api/` 两段配置是否都存在。

### 22.11.4 为什么 Supervisor 状态是 `not_configured`？
​        `not_configured` 是本章的正常状态。它表示 `SUPERVISOR_ENABLED=false`，沙箱服务没有尝试调用真实 `supervisorctl`，只是按照配置里的 `SUPERVISOR_SERVICES` 返回占位服务列表。
​        这个状态不是错误，而是接口协议的第一版。后续章节安装 Supervisor 后，只需要把配置打开并让镜像具备 `supervisorctl`，同一个接口就能返回真实进程状态。

### 22.11.5 为什么沙箱服务端口是 `8100`？
​        主 API 已经使用 `8000`，UI 使用 `3000`，沙箱如果继续复用这些端口，调试时很容易混淆请求目标。`8100` 作为沙箱内部端口，可以让 Compose、日志和健康检查都更清楚地识别当前服务。
​        对浏览器来说，真正需要记住的不是 `8100`，而是 Nginx 暴露出来的 `/sandbox-api`。端口属于容器内部通信细节，外部访问仍然保持统一网关入口。

## 22.12 本章小结
​        本章完成了 Sandbox 服务骨架。项目里新增了独立的 `sandbox` Python 应用，它有自己的依赖配置、配置读取、日志初始化、统一响应、统一异常、状态接口和 Supervisor 状态接口。随后，我们又为它准备了 Dockerfile，把它加入 Docker Compose，并通过 Nginx 的 `/sandbox-api` 对外暴露。
​        从这一章开始，AtlasAgent 不再只是主 API 里的一组业务服务，而是拥有了独立执行环境的基础。这个基础暂时还不执行命令，也不读写文件，但它已经回答了一个关键工程问题：Agent 后续要做的危险、阻塞、依赖外部进程的事情，应该发生在 Sandbox，而不是发生在主 API 里。下一章会在这个基础上实现沙箱文件 API，并把主 API 的 FileTool 接到沙箱能力上。

## 22.13 下一章预告
​        第 23 章会实现 Sandbox 文件 API 与 FileTool，包括文件读取、写入、列表、删除和主 API 工具调用封装。

## 22.14 代码
​        暂时无法在飞书文档外展示此内容
