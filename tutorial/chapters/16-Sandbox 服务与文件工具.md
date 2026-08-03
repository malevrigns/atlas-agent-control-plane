# 第十六章. Sandbox 服务与文件工具

## 16.1 合章说明

​        旧版教程把“Sandbox 服务骨架初成”与“Sandbox 文件 API 与 FileTool 成形”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 16.2 第一阶段：Sandbox 服务骨架初成

### 16.2.1 本阶段目标
​        学完本阶段后，你应该能把 Agent 系统里的“业务编排”和“执行环境”分开看待。
​        前面章节已经让主 API 拥有了会话、任务、计划、事件和上下文能力，但这些能力仍然主要发生在业务层。真正的 Agent 一旦开始执行工具，就会碰到文件、命令、浏览器、截图、下载和进程管理。它们不适合直接塞进主 API 进程里，因为执行环境越复杂，主 API 越容易被阻塞、污染或拖垮。
​        因此，本阶段的目标不是马上做一个很强的工具系统，而是先搭出 Sandbox 服务骨架。你会创建一个独立的 FastAPI 沙箱服务，为它准备 `pydantic-settings` 配置、统一响应、统一异常、状态检查接口和 Supervisor 状态接口，再把它接入 Docker Compose 与 Nginx。到这一阶段结束时，项目会从“一个主 API 加前端”走向“主 API 负责调度，Sandbox 负责执行环境”的多服务架构。

### 16.2.2 最终效果
​        本阶段结束后，项目会新增一个独立服务：

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

### 16.2.3 本阶段要解决的问题
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
​        所以从本阶段开始，项目进入第 5 阶段：沙箱与内置工具。本阶段先搭建沙箱服务骨架，不急着实现文件和 Shell。先把服务边界、配置、响应、异常、Docker 和网关跑通，后面章节再在这个骨架上逐步加入真正的执行能力。

### 16.2.4 本阶段技术方案
​        本阶段新增一个独立 FastAPI 应用：

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

​        本阶段会先把最小可运行链路打通。`GET /api/status` 用来确认沙箱服务已经启动并能读取配置，`GET /api/supervisor/services` 用来提前固定进程状态接口的返回结构，`sandbox/Dockerfile` 负责构建独立镜像，`docker-compose.yml` 负责把 `sandbox` 放进整体服务编排，`nginx/default.conf` 则负责把外部的 `/sandbox-api` 转发到沙箱容器内部的 `/api`。
​        本阶段也会刻意保留边界，不在这里实现文件 API、Shell API、真实 Supervisor、Chrome 或 VNC。这些能力都依赖一个稳定的沙箱服务入口，提前把它们全塞进来只会让第一版边界变得模糊。先让服务能独立启动、独立配置、独立被网关访问，后续章节再逐步把工具能力接上来。

### 16.2.5 新增和修改的文件

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

### 16.2.6 实施步骤
#### 16.2.6.1 创建 Sandbox 依赖配置
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

##### 16.2.6.1.1 字段含义
​        `name` 写成 `atlas-agents-sandbox`，是为了和主 API 的 Python 包区分开。它不是主 API 的一个子模块，而是一个可以独立安装、独立启动、独立构建镜像的服务。
​        `requires-python` 约束运行时版本，`dependencies` 只放本阶段真正需要的 FastAPI、配置读取和 Uvicorn。这里暂时不引入文件、Shell、浏览器相关依赖，是为了让骨架阶段保持轻量。`where = ["."]` 和 `include = ["app*"]` 则告诉 setuptools 只从当前 `sandbox` 目录收集 `app` 包，避免把仓库里其他服务误纳入沙箱包。

##### 16.2.6.1.2 为什么这样设计
​        沙箱服务和主 API 是两个独立应用。
​        它们以后会有不同依赖：主 API 关注数据库、Redis、LLM；沙箱会关注文件、Shell、浏览器和进程管理。
​        所以本阶段不复用 `api/pyproject.toml`，而是给 `sandbox/` 自己创建一套依赖配置。

#### 16.2.6.2 创建沙箱配置
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

##### 16.2.6.2.1 字段含义
​        这些配置先把沙箱服务的身份写清楚。`sandbox_app_name`、`sandbox_env` 和 `sandbox_version` 会体现在状态接口里，后续排查 Docker 镜像、环境变量或网关代理时，可以直接从接口返回判断当前访问到的是哪一个服务、哪一个环境、哪一个版本。
​        `sandbox_api_prefix` 表示沙箱服务内部的 API 前缀，本阶段保持为 `/api`。外部用户通过 Nginx 访问的是 `/sandbox-api`，容器内部服务看到的仍然是 `/api`，这可以让沙箱代码不用关心网关层路径。`workspace_dir` 是后续文件读写和 Shell 执行的根目录，先把它固定下来，之后所有执行能力才有边界可依。`supervisor_enabled` 和 `supervisor_services` 则为进程管理预留入口，本阶段先让它返回可解释状态，后面再接真实 Supervisor。

##### 16.2.6.2.2 代码讲解
​        `Settings` 和主 API 的配置方式保持一致，都是用 `pydantic-settings` 从环境变量读取配置。
​        `get_settings()` 使用 `lru_cache`，表示配置只创建一次。后续路由和服务都可以直接使用同一个 `settings` 对象，不需要每次请求重新解析环境变量。
​        `workspace_dir` 是本阶段最重要的配置之一。虽然本阶段还没有文件 API，但后续所有文件读写都必须落在这个目录下，避免 Agent 随意访问容器里的任意路径。

#### 16.2.6.3 创建统一响应和异常处理
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

##### 16.2.6.3.1 字段含义
​        统一响应里有两层含义。`code` 和 `message` 是业务层的表达，告诉调用方这次请求在应用语义上是否成功；`data` 承载真正的返回数据，异常时通常就是 `null`。HTTP 的 `status_code` 则保留在响应对象之外，用来控制客户端看到的协议层状态。
​        这样设计的好处是，主 API、前端和后续工具调用都能用同一种方式理解沙箱结果。比如文件工具调用失败时，主 API 不需要猜测沙箱到底返回了什么结构，只需要读取 `code`、`message` 和 `data`，再决定是否把错误写入 Agent 事件流。

##### 16.2.6.3.2 代码讲解
​        这套结构和主 API 保持一致。
​        原因是前端或主 API 调用沙箱服务时，不需要适配另一套奇怪的错误格式。
​        统一响应不是为了“好看”，而是为了降低联调成本。比如后续主 API 调用沙箱文件接口失败时，可以直接读取：

```Plain
code
message
data
```

​        而不是每个接口都猜一次错误结构。

#### 16.2.6.4 创建状态接口
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

##### 16.2.6.4.1 字段含义
​        状态接口返回的是沙箱服务的最小身份信息。`service` 用来确认当前命中的确实是 Sandbox，而不是主 API 或前端页面；`environment` 和 `version` 用来定位运行环境和镜像版本；`status` 在本阶段固定为 `ok`，表示 FastAPI 应用已经启动并完成基础配置读取；`workspace_dir` 则提前暴露沙箱工作目录，方便后续验证文件 API 和 Shell API 是否都围绕同一个目录运行。

##### 16.2.6.4.2 代码讲解
​        `/api/status` 是最小健康检查。
​        它的价值不只是“返回 ok”。当这个接口能稳定响应时，至少说明 Sandbox 应用已经启动、配置对象可以正常创建，并且你当前访问的端口或网关路径确实落到了沙箱服务上。后续只要沙箱 Dockerfile、Compose 网络或 Nginx 代理出问题，都可以先用这个接口判断问题发生在哪一层。
​        后续每次沙箱 Dockerfile 或 Nginx 代理出问题，都可以先从这个接口查。

#### 16.2.6.5 创建 Supervisor 状态接口
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

##### 16.2.6.5.1 字段含义
​        `enabled` 表示沙箱是否尝试读取真实 Supervisor 状态。如果它是 `false`，说明当前只是占位接口，不会调用 `supervisorctl`。`services` 里的每一项描述一个被沙箱关注的进程，`name` 是进程名，`status` 是状态，`description` 则解释这个状态从哪里来。
​        本阶段常见状态是 `not_configured` 和 `unavailable`。前者表示配置上还没有启用真实 Supervisor，后者表示配置启用了，但当前镜像里没有安装 `supervisorctl`。等后续章节加入 Chrome、Xvfb、x11vnc 和 websockify 后，这个接口会开始返回更接近真实运行态的 `running`、`stopped` 等状态。

##### 16.2.6.5.2 代码讲解
​        本阶段没有真正安装 Supervisor，但先做接口。
​        原因是后续沙箱会越来越复杂，可能同时运行：

```Plain
sandbox-api
chrome
xvfb
x11vnc
websockify
```

​        这些进程不能只靠一个 Python 主进程管理。Supervisor 会负责拉起和管理它们。
​        本阶段先处理三种情况：

```Plain
supervisor_enabled = false
  -> 返回 not_configured

supervisor_enabled = true，但 supervisorctl 不存在
  -> 返回 unavailable

supervisor_enabled = true，且 supervisorctl 存在
  -> 执行 supervisorctl status
```

​        这样即使当前镜像还没安装 Supervisor，接口也不会报 500，而是返回可解释状态。

#### 16.2.6.6 创建 API Router 和应用入口
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

##### 16.2.6.6.1 代码讲解
​        `api_router` 聚合所有沙箱路由。
​        `create_app()` 是沙箱服务的启动装配点。它先初始化日志格式，再创建独立的 FastAPI 实例，随后注册统一异常处理，并把聚合后的 `api_router` 挂载到配置里的 `/api` 前缀下。
​        这和主 API 的入口结构保持接近。这样后续读代码时，看到 `api/app/main.py` 和 `sandbox/app/main.py` 会有相同的理解方式。

#### 16.2.6.7 编写 Sandbox Dockerfile
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

##### 16.2.6.7.1 字段含义
​        这个 Dockerfile 的重点是让沙箱服务能以最小镜像独立运行。`PYTHONDONTWRITEBYTECODE` 避免容器里生成无意义的 `.pyc` 文件，`PYTHONUNBUFFERED` 让日志可以及时进入 `docker logs`，`UV_COMPILE_BYTECODE` 和 `UV_LINK_MODE=copy` 则让 `uv` 的依赖安装更适合容器层缓存。
​        镜像构建时先复制 `pyproject.toml`、`uv.lock` 和 `README.md`，再执行一次不安装项目本身的依赖同步，最后复制 `app/` 并完成最终同步。这样依赖层和代码层分开，后续只改业务代码时，不必每次都重新解析完整依赖。`EXPOSE 8100` 表示容器内的沙箱服务监听 8100 端口，Compose 和 Nginx 会围绕这个端口完成内部转发。

##### 16.2.6.7.2 代码讲解
​        这个 Dockerfile 和主 API 的结构类似，但更简单。
​        本阶段沙箱还没有 migrations、config、数据库等内容，所以镜像里只放入：

```Plain
pyproject.toml
uv.lock
README.md
app/
```

​        如果执行构建时报 `ghcr.io/astral-sh/uv:0.11.15` 拉取失败，那是网络访问 GitHub Container Registry 的问题，不是沙箱代码错误。可以先用本地 `uv run` 验证服务。

#### 16.2.6.8 接入 Docker Compose
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

##### 16.2.6.8.1 代码讲解
​        `sandbox_workspace` 是沙箱工作目录卷。
​        后续文件 API 和 Shell API 都会围绕 `/workspace` 运行。把它做成 Docker volume，是为了让沙箱工作目录拥有稳定的生命周期：容器重启时目录内容不会因为容器层被重建而消失，同时所有文件操作都集中在一个明确挂载点上。等 Agent 开始写文件、下载文件或运行命令时，这个目录就是执行结果最重要的边界。
​        `expose: "8100"` 表示这个端口只暴露给 Docker 网络里的其他服务。浏览器不直接访问 `8100`，而是通过 Nginx 的 `/sandbox-api` 访问。

#### 16.2.6.9 接入 Nginx 网关
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

##### 16.2.6.9.1 代码讲解
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

### 16.2.7 关键理解
​        本阶段最重要的是服务边界。
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

### 16.2.8 技术难点与亮点
​        本阶段的难点不在代码量，而在边界意识。Sandbox 是独立服务，就必须拥有自己的依赖配置、环境变量、启动入口、异常处理和健康检查。它不能一边声称独立，一边继续依赖主 API 的内部模块，否则后续工具执行出了问题，还是会牵扯到主 API 的运行环境。
​        另一个容易出错的地方是 Nginx 路径映射。外部路径是 `/sandbox-api`，沙箱服务内部路径是 `/api`，两者必须在网关层准确转换。如果这里写错，浏览器可能拿到 UI 的 404，也可能请求到主 API。Supervisor 接口同样体现了工程上的提前设计：即使本阶段还没安装 Supervisor，也要让调用方得到可解释状态，而不是让接口直接报 500。
​        这一阶段的亮点，是项目正式从单 API 架构扩展为多服务架构。Sandbox 有自己的统一响应、统一异常、健康检查、Dockerfile、Compose 服务和网关入口。后续文件工具、Shell 工具和浏览器工具不是凭空加到主 API 里，而是会落在这个已经划好边界的执行服务上。

### 16.2.9 面试考点
​        面试里如果被问到这一阶段，重点不是背出文件名，而是讲清服务拆分背后的理由。沙箱服务之所以要从主 API 中拆出去，是因为工具执行会带来文件系统、进程、浏览器和命令运行等复杂副作用，这些副作用应该被限制在专门的执行环境里。
​        `/api` 和 `/sandbox-api` 的区别也很容易被追问。`/api` 是服务内部前缀，主 API 和 Sandbox 都可以在各自服务内使用它；`/sandbox-api` 是网关对外暴露的路径，用来让浏览器和调试命令清楚区分访问目标。Docker Compose 里的 `expose` 只把端口暴露给内部网络，`ports` 才会映射到宿主机，这正好符合本阶段设计：外部统一走 Nginx，容器之间通过内部网络通信。
​        Supervisor 状态接口提前出现，是为了先固定协议形状。真实 Supervisor 可以晚一点安装，但主 API 和前端应该提前知道如何询问沙箱内的服务状态。`/workspace` 也是同样的道理，它不是随便取的目录，而是后续文件读写、命令执行和浏览器下载共同依赖的工作边界。

### 16.2.10 运行验证
​        下面命令默认在项目根目录执行。

#### 16.2.10.1 检查沙箱代码编译

```Bash
cd sandbox
uv run python -m compileall app
```

​        预期没有 Python 语法错误。

#### 16.2.10.2 本地运行沙箱服务

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

#### 16.2.10.3 检查 Compose 配置
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

#### 16.2.10.4 Docker Compose 运行
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

​        如果构建时提示 `ghcr.io/astral-sh/uv:0.11.15` 拉取失败，先用本地 `uv run uvicorn` 验证本阶段代码。等网络恢复后再构建 Docker 镜像。

### 16.2.11 阶段小结
​        本阶段完成了 Sandbox 服务骨架。项目里新增了独立的 `sandbox` Python 应用，它有自己的依赖配置、配置读取、日志初始化、统一响应、统一异常、状态接口和 Supervisor 状态接口。随后，我们又为它准备了 Dockerfile，把它加入 Docker Compose，并通过 Nginx 的 `/sandbox-api` 对外暴露。
​        从这一阶段开始，AtlasAgent 不再只是主 API 里的一组业务服务，而是拥有了独立执行环境的基础。这个基础暂时还不执行命令，也不读写文件，但它已经回答了一个关键工程问题：Agent 后续要做的危险、阻塞、依赖外部进程的事情，应该发生在 Sandbox，而不是发生在主 API 里。本章第二阶段会在这个基础上实现沙箱文件 API，并把主 API 的 FileTool 接到沙箱能力上。

### 16.2.12 代码
​        暂时无法在飞书文档外展示此内容

## 16.3 第二阶段：Sandbox 文件 API 与 FileTool 成形

### 16.3.1 本阶段目标
​        学完本阶段后，你将能够：
​        这一阶段要把本章第一阶段搭好的 Sandbox 骨架变成真正能工作的执行环境。文件能力是 Agent 工具链里的第一块地基，因为后续无论是写代码、保存搜索结果、下载产物，还是把浏览器截图交给模型分析，最终都会落到文件系统里。
​        学完本阶段后，你应该能解释为什么文件工具必须运行在沙箱工作目录内，也能在 Sandbox 服务中实现列表、读取、写入、替换、删除、上传和下载接口。更重要的是，你要理解路径归一化为什么必须放在服务端完成，`../` 这类路径穿越为什么不能交给模型或前端自觉避免。最后，我们会在主 API 中封装 `SandboxFileClient`，把沙箱文件能力注册成 Agent 可调用的 FileTool，并通过 `/sandbox-api/files` 和 `/api/agent-core/tools` 验证完整链路。

### 16.3.2 最终效果
​        本阶段结束后，Sandbox 服务会新增一组文件接口：

```Plain
GET    /api/files
GET    /api/files/read
POST   /api/files/write
POST   /api/files/replace
DELETE /api/files
POST   /api/files/upload
GET    /api/files/download
```

​        通过 Nginx 访问时，路径会变成：

```Plain
GET    /sandbox-api/files
GET    /sandbox-api/files/read
POST   /sandbox-api/files/write
POST   /sandbox-api/files/replace
DELETE /sandbox-api/files
POST   /sandbox-api/files/upload
GET    /sandbox-api/files/download
```

​        主 API 会新增 Sandbox 文件客户端，并把这些能力注册成工具：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

​        本阶段完成后，请求链路会变成：

```Plain
Agent / 主 API
  |
  |  SandboxFileClient
  v
Sandbox 文件 API
  |
  |  安全路径校验
  v
/workspace
```

### 16.3.3 本阶段要解决的问题
​        本章第一阶段已经把 Sandbox 服务独立出来，并通过 `/sandbox-api/status` 确认沙箱服务可以访问。
​        但此时沙箱还不能真正做事。Agent 要执行任务，最基础的能力之一就是操作文件。例如：

```Plain
读取需求文档
生成代码文件
替换配置内容
保存执行结果
下载产物文件
```

​        这些文件操作不能直接发生在主 API 容器里。主 API 负责业务和调度，沙箱负责执行和隔离。
​        所以本阶段先给 Sandbox 加文件 API，再让主 API 通过 FileTool 调用它。

### 16.3.4 本阶段技术方案
​        本阶段采用“Sandbox 提供文件 API，主 API 只通过客户端调用”的方案。
​        可选方案有三种：
​        一种做法是让主 API 直接读写宿主机文件，这样最快，但也最危险，因为业务服务和执行环境没有边界。另一种做法是让主 API 挂载并直接读写沙箱数据卷，这比直接碰宿主机好一些，却仍然把文件路径、目录结构和执行环境细节泄露给了主 API。第三种做法是让 Sandbox 服务提供文件 API，主 API 只通过 HTTP 客户端调用它。
​        本项目选择第三种。这样主 API 不需要知道沙箱容器里的真实路径，也不需要直接操作 `/workspace` 数据卷。所有文件读写都集中在 Sandbox 服务里，路径安全校验、大小限制、上传保存和下载响应都可以在同一层完成。后续如果引入多沙箱、多任务隔离或远程沙箱，主 API 也只需要把请求发给不同的 Sandbox 地址，而不用重写工具协议。
​        本阶段会先在 Sandbox 中定义文件请求和响应模型，再实现 `SandboxFileService` 和 `/api/files` 路由，同时给读取、写入、上传加入大小限制。主 API 侧会增加 `SandboxFileClient`，并把文件能力注册成 `file_list`、`file_read`、`file_write`、`file_replace` 和 `file_delete`。Shell 命令执行、多沙箱实例管理、文件权限系统、二进制文件预览，以及 Planner/ReAct 对 FileTool 的真实自动调用策略，都留到后续章节逐步补上。

### 16.3.5 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
docker-compose.yml
sandbox/README.md
docs/course/chapters/23-file-tool.md
sandbox/pyproject.toml
sandbox/uv.lock
sandbox/app/core/config.py
sandbox/app/schemas/files.py
sandbox/app/services/file_service.py
sandbox/app/api/routes/files.py
sandbox/app/api/router.py
api/app/core/config.py
api/app/infrastructure/sandbox/__init__.py
api/app/infrastructure/sandbox/file_client.py
api/app/infrastructure/agent_tools/sandbox_file.py
api/app/infrastructure/agent_tools/builtin.py
```

### 16.3.6 实施步骤
#### 16.3.6.1 为 Sandbox 加入文件上传依赖
​        打开 `sandbox/pyproject.toml`，在 `dependencies` 中加入：

```TOML
"python-multipart>=0.0.30",
```

​        完整依赖部分如下：

```TOML
dependencies = [
  "fastapi>=0.115,<1.0",
  "pydantic-settings>=2.7,<3.0",
  "python-multipart>=0.0.30",
  "uvicorn[standard]>=0.34,<1.0",
]
```

​        然后在 `sandbox` 目录执行：

```Bash
uv lock
```

##### 16.3.6.1.1 这一步的作用
​        FastAPI 接收普通 JSON 请求时不需要额外依赖。
​        但上传文件使用的是 `multipart/form-data` 格式。FastAPI 解析这种格式时需要 `python-multipart`。
​        本阶段的 `/api/files/upload` 会使用：

```Python
upload: UploadFile = File(...)
```

​        如果没有安装 `python-multipart`，应用启动或请求上传接口时会报错。

#### 16.3.6.2 补充 Sandbox 文件配置
​        打开 `sandbox/app/core/config.py`，把文件限制配置加到 `workspace_dir` 后面：

```Python
    # ----- 沙箱工作目录：后续文件、Shell、浏览器下载都限制在这里 -----
    workspace_dir: str = "workspace"
    max_file_read_bytes: int = 64 * 1024
    max_file_write_bytes: int = 512 * 1024
    max_upload_size: int = 10 * 1024 * 1024
```

##### 16.3.6.2.1 字段含义
​        `workspace_dir` 是文件 API 的根边界。本地运行时，它默认指向 `sandbox/workspace`，方便不用 Docker 也能调试；Docker Compose 运行时，它会被环境变量覆盖成容器里的 `/workspace`，也就是本章第一阶段挂载出来的沙箱工作目录。
​        另外三个配置都是为了限制工具调用的资源消耗。`max_file_read_bytes` 控制一次读取最多返回多少字节，避免大文件直接进入 Agent 上下文；`max_file_write_bytes` 控制文本写入大小，防止错误工具调用写出异常大文件；`max_upload_size` 控制上传文件大小，避免沙箱数据卷被意外填满。这里的限制不是为了让功能变弱，而是为了让后续自动化执行有明确边界。

##### 16.3.6.2.2 代码讲解
​        文件工具一定要有限制。
​        没有读取限制时，一个 Agent 可能把大文件一次性读进上下文，导致响应变慢，甚至后续 LLM 调用超出上下文预算。
​        没有写入和上传限制时，错误的工具调用可能把沙箱数据卷写满。
​        本阶段先用简单的字节数限制。后续如果要支持更复杂的文件策略，可以继续扩展成按任务、按用户、按沙箱实例的配额。

#### 16.3.6.3 定义文件 API 的请求和响应模型
​        创建 `sandbox/app/schemas/files.py`：

```Python
from pydantic import BaseModel, Field

class FileEntryResponse(BaseModel):
    name: str  # 展示文件名，前端列表直接使用。
    path: str  # 相对 workspace 的路径，后续读取、下载、删除都用它。
    type: str  # file 或 directory，前端据此决定是否可以继续进入目录。
    size: int  # 文件字节数，目录固定返回 0。
    modified_at: float  # 文件最后修改时间戳，方便后续排序或展示。

class FileListResponse(BaseModel):
    current_path: str  # 当前正在浏览的目录路径。
    items: list[FileEntryResponse]  # 当前目录下的文件和子目录。

class FileReadResponse(BaseModel):
    path: str  # 被读取的文件路径。
    content: str  # 读取到的文本内容。
    size: int  # 文件真实字节数，不受截断影响。
    truncated: bool  # 是否因为超过读取上限被截断。

class FileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str
    create_parent: bool = True  # 父目录不存在时是否自动创建。

class FileWriteResponse(BaseModel):
    path: str  # 写入成功的文件路径。
    size: int  # 写入后的文件字节数。

class FileReplaceRequest(BaseModel):
    path: str = Field(min_length=1)
    old_text: str = Field(min_length=1)
    new_text: str

class FileReplaceResponse(BaseModel):
    path: str  # 完成替换的文件路径。
    replacements: int  # 实际替换次数，0 表示没有命中 old_text。
    content: str  # 替换后的完整文本，便于调用方立即查看结果。

class FileDeleteResponse(BaseModel):
    path: str  # 被删除的文件或目录路径。
    deleted: bool  # 删除成功时固定为 true。

class FileUploadResponse(BaseModel):
    path: str  # 上传后保存在 workspace 内的路径。
    original_name: str  # 用户上传时的原始文件名。
    size: int  # 上传文件大小。
```

##### 16.3.6.3.1 这段代码在流程中的位置
​        这些模型位于 Sandbox 服务的接口边界。
​        浏览器、主 API 或 FileTool 调用 Sandbox 文件接口时，请求和响应都会经过这些模型。

##### 16.3.6.3.2 输入和输出
​        写入文件时，输入是：

```JSON
{
  "path": "notes/hello.txt",
  "content": "hello sandbox",
  "create_parent": true
}
```

​        读取文件时，输出是：

```JSON
{
  "path": "notes/hello.txt",
  "content": "hello sandbox",
  "size": 13,
  "truncated": false
}
```

##### 16.3.6.3.3 为什么这样设计
​        文件列表、文件内容、写入结果、替换结果、删除结果分别使用不同响应模型，是为了让调用方知道每个接口到底返回什么。
​        `path` 使用相对路径，而不是绝对路径。调用方只知道 `notes/hello.txt`，不知道真实路径是 `sandbox/workspace/notes/hello.txt` 还是容器里的 `/workspace/notes/hello.txt`。这样可以减少沙箱实现细节暴露。
​        `truncated` 很重要。它告诉调用方内容是否被截断。后续 Agent 看到 `truncated=true` 时，可以选择分段读取，而不是误以为已经拿到完整文件。

##### 16.3.6.3.4 常见误区
​        不要把容器真实路径返回给前端或主 API。
​        如果返回 `/workspace/notes/hello.txt`，后续多沙箱实例、不同工作目录、远程沙箱都会变得更难迁移。

#### 16.3.6.4 实现 Sandbox 文件服务
​        创建 `sandbox/app/services/file_service.py`：

```Python
from pathlib import Path
from shutil import rmtree

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.files import (
    FileDeleteResponse,
    FileEntryResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteResponse,
)

class SandboxFileService:
    """把所有文件操作限制在 workspace 目录内。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace = Path(settings.workspace_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    # ===================== 第1步：浏览目录 =====================
    def list_files(self, path: str = ".") -> FileListResponse:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if not target.is_dir():
            raise SandboxException(message="path is not a directory")

        items = [self._to_entry(child) for child in sorted(target.iterdir())]
        return FileListResponse(current_path=self._to_relative_path(target), items=items)

    # ===================== 第2步：读取文本文件 =====================
    def read_file(self, path: str) -> FileReadResponse:
        target = self._resolve_existing_file(path)
        raw_content = target.read_bytes()
        truncated = len(raw_content) > self.settings.max_file_read_bytes
        preview = raw_content[: self.settings.max_file_read_bytes]
        content = preview.decode("utf-8", errors="replace")
        return FileReadResponse(
            path=self._to_relative_path(target),
            content=content,
            size=len(raw_content),
            truncated=truncated,
        )

    # ===================== 第3步：写入文本文件 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool,
    ) -> FileWriteResponse:
        encoded = content.encode("utf-8")
        if len(encoded) > self.settings.max_file_write_bytes:
            raise SandboxException(message="file content is too large", code=413, status_code=413)

        target = self._resolve_path(path)
        if target.exists() and target.is_dir():
            raise SandboxException(message="path is a directory")
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise SandboxException(message="parent directory not found", code=404, status_code=404)

        target.write_bytes(encoded)
        return FileWriteResponse(path=self._to_relative_path(target), size=len(encoded))

    # ===================== 第4步：替换文本内容 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> FileReplaceResponse:
        current = self.read_file(path)
        replacements = current.content.count(old_text)
        next_content = current.content.replace(old_text, new_text)
        self.write_file(path=path, content=next_content, create_parent=False)
        return FileReplaceResponse(
            path=current.path,
            replacements=replacements,
            content=next_content,
        )

    # ===================== 第5步：删除文件或目录 =====================
    def delete_path(self, path: str) -> FileDeleteResponse:
        target = self._resolve_path(path)
        if target == self.workspace:
            raise SandboxException(message="workspace root cannot be deleted")
        if not target.exists():
            raise SandboxException(message="path not found", code=404, status_code=404)
        if target.is_dir():
            rmtree(target)
        else:
            target.unlink()
        return FileDeleteResponse(path=path, deleted=True)

    # ===================== 第6步：保存上传文件 =====================
    async def save_upload(
        self,
        directory: str,
        upload: UploadFile,
    ) -> FileUploadResponse:
        filename = Path(upload.filename or "").name
        if not filename:
            raise SandboxException(message="filename is required")

        target_dir = self._resolve_path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target_dir.is_dir():
            raise SandboxException(message="upload target is not a directory")

        content = await upload.read()
        if len(content) > self.settings.max_upload_size:
            raise SandboxException(message="upload file is too large", code=413, status_code=413)

        target = self._resolve_path(str(Path(directory) / filename))
        target.write_bytes(content)
        return FileUploadResponse(
            path=self._to_relative_path(target),
            original_name=filename,
            size=len(content),
        )

    # ===================== 第7步：获取下载路径 =====================
    def get_download_path(self, path: str) -> Path:
        return self._resolve_existing_file(path)

    # ===================== 第8步：路径安全校验 =====================
    def _resolve_path(self, path: str) -> Path:
        clean_path = path.strip() or "."
        if Path(clean_path).is_absolute():
            raise SandboxException(message="absolute path is not allowed")

        target = (self.workspace / clean_path).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise SandboxException(message="path escapes workspace")
        return target

    def _resolve_existing_file(self, path: str) -> Path:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxException(message="file not found", code=404, status_code=404)
        if not target.is_file():
            raise SandboxException(message="path is not a file")
        return target

    def _to_entry(self, path: Path) -> FileEntryResponse:
        stat = path.stat()
        return FileEntryResponse(
            name=path.name,
            path=self._to_relative_path(path),
            type="directory" if path.is_dir() else "file",
            size=0 if path.is_dir() else stat.st_size,
            modified_at=stat.st_mtime,
        )

    def _to_relative_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.workspace)
        return "." if str(relative) == "." else relative.as_posix()
```

##### 16.3.6.4.1 这段代码在流程中的位置
​        `SandboxFileService` 是 Sandbox 文件 API 的核心业务层。
​        路由只负责接收 HTTP 请求，真正的路径检查、读写文件、大小限制和返回模型都放在这里。

##### 16.3.6.4.2 输入和输出
​        输入来自 HTTP 接口：

```Plain
path=notes/hello.txt
content=hello sandbox
```

​        输出是 Pydantic 响应模型，例如：

```Plain
FileWriteResponse(path="notes/hello.txt", size=13)
```

##### 16.3.6.4.3 调用链路
​        写文件的调用链路是：

```Plain
POST /api/files/write
  |
  v
files.py 路由函数
  |
  v
SandboxFileService.write_file()
  |
  v
_resolve_path()
  |
  v
/workspace/notes/hello.txt
```

##### 16.3.6.4.4 关键代码逐段解释
​        `__init__()` 中先把 `workspace_dir` 转成真实路径：

```Python
self.workspace = Path(settings.workspace_dir).resolve()
```

​        这里必须使用 `resolve()`。因为后续要判断用户路径是否逃出 workspace，比较的必须是真实路径。
​        `_resolve_path()` 是本阶段最重要的安全函数：

```Python
target = (self.workspace / clean_path).resolve()
if target != self.workspace and self.workspace not in target.parents:
    raise SandboxException(message="path escapes workspace")
```

​        如果用户传入 `../secret.txt`，拼接后看起来还在 workspace 下面，但 `resolve()` 会把 `..` 折叠掉。折叠后的真实路径如果不在 workspace 内，就直接拒绝。
​        读取文件时使用：

```Python
preview = raw_content[: self.settings.max_file_read_bytes]
content = preview.decode("utf-8", errors="replace")
```

​        这样即使文件很大，也只返回允许的前半部分。`errors="replace"` 可以避免非 UTF-8 字节导致接口直接崩掉。
​        写入文件时先把内容编码成字节，再比较大小：

```Python
encoded = content.encode("utf-8")
```

​        不要用 `len(content)` 判断大小。中文字符在 UTF-8 中可能占多个字节，文件大小应该按字节计算。

##### 16.3.6.4.5 为什么这样设计
​        文件 API 的核心不是“能读写文件”，而是“只能读写允许的文件”。
​        Agent 后续会自动调用工具。工具参数可能来自模型输出，模型输出不能直接信任。所以文件路径必须在服务端做安全校验。
​        本阶段把安全校验放在 `SandboxFileService`，而不是放在每个路由函数里。这样未来 ShellTool、BrowserTool 如果也需要处理文件路径，可以复用同样的设计思路。

##### 16.3.6.4.6 小白最容易困惑的点
​        `Path(filename).name` 不是为了好看，而是为了去掉上传文件名里的路径。
​        如果浏览器或客户端上传的文件名是 `../../a.txt`，`Path(...).name` 会取出 `a.txt`。真正保存前仍然会经过 `_resolve_path()`，形成双重保护。

#### 16.3.6.5 创建 Sandbox 文件路由
​        创建 `sandbox/app/api/routes/files.py`：

```Python
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.files import (
    FileDeleteResponse,
    FileListResponse,
    FileReadResponse,
    FileReplaceRequest,
    FileReplaceResponse,
    FileUploadResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.services.file_service import SandboxFileService

router = APIRouter(prefix="/files", tags=["files"])

def build_file_service() -> SandboxFileService:
    # 文件服务只依赖配置，后续如果接入权限或审计，可以从这里统一扩展。
    return SandboxFileService(settings=settings)

@router.get("", response_model=ApiResponse[FileListResponse])
async def list_files(
    path: str = Query(default="."),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileListResponse]:
    # 列表接口只允许浏览 workspace 里的相对路径。
    return ApiResponse(data=service.list_files(path))

@router.get("/read", response_model=ApiResponse[FileReadResponse])
async def read_file(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReadResponse]:
    return ApiResponse(data=service.read_file(path))

@router.post("/write", response_model=ApiResponse[FileWriteResponse])
async def write_file(
    payload: FileWriteRequest,
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileWriteResponse]:
    return ApiResponse(
        data=service.write_file(
            path=payload.path,
            content=payload.content,
            create_parent=payload.create_parent,
        )
    )

@router.post("/replace", response_model=ApiResponse[FileReplaceResponse])
async def replace_text(
    payload: FileReplaceRequest,
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileReplaceResponse]:
    return ApiResponse(
        data=service.replace_text(
            path=payload.path,
            old_text=payload.old_text,
            new_text=payload.new_text,
        )
    )

@router.delete("", response_model=ApiResponse[FileDeleteResponse])
async def delete_path(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileDeleteResponse]:
    return ApiResponse(data=service.delete_path(path))

@router.post("/upload", response_model=ApiResponse[FileUploadResponse])
async def upload_file(
    path: str = Query(default="."),
    upload: UploadFile = File(...),
    service: SandboxFileService = Depends(build_file_service),
) -> ApiResponse[FileUploadResponse]:
    return ApiResponse(data=await service.save_upload(path, upload))

@router.get("/download")
async def download_file(
    path: str = Query(min_length=1),
    service: SandboxFileService = Depends(build_file_service),
) -> FileResponse:
    target = service.get_download_path(path)
    return FileResponse(path=target, filename=target.name)
```

##### 16.3.6.5.1 这段代码在流程中的位置
​        这是 Sandbox 文件模块的 HTTP 入口。
​        它把请求参数转换成 `SandboxFileService` 的方法调用，再把结果包成统一响应。

##### 16.3.6.5.2 接口输入和返回
​        写入文件：

```Bash
curl -X POST http://localhost:8100/api/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","content":"hello sandbox"}'
```

​        读取文件：

```Bash
curl "http://localhost:8100/api/files/read?path=notes/hello.txt"
```

​        上传文件：

```Bash
curl -F "upload=@README.md" "http://localhost:8100/api/files/upload?path=uploads"
```

##### 16.3.6.5.3 为什么这样设计
​        下载接口没有使用 `ApiResponse`，而是直接返回 `FileResponse`。
​        原因是下载文件本身就是二进制响应。如果把文件内容塞进 JSON，浏览器就不能自然地把它当作附件下载。
​        其余接口都返回 `ApiResponse`，保持和主 API 一致的错误处理风格。

##### 16.3.6.5.4 常见误区
​        `GET /files` 和 `DELETE /files` 使用同一个路径，但 HTTP 方法不同，所以它们不会冲突。
​        读取接口用 `/files/read`，下载接口用 `/files/download`。读取返回文本内容，下载返回文件流。两者服务的场景不同。

#### 16.3.6.6 注册 Sandbox 文件路由
​        打开 `sandbox/app/api/router.py`，改成：

```Python
from fastapi import APIRouter

from app.api.routes import files, status, supervisor

api_router = APIRouter()
api_router.include_router(files.router)
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
```

##### 16.3.6.6.1 代码讲解
​        本章第一阶段只注册了 `status` 和 `supervisor`。
​        本阶段新增 `files.router` 后，Sandbox 应用才会真正暴露：

```Plain
/api/files
/api/files/read
/api/files/write
```

​        如果忘记注册路由，请求会返回 404。

#### 16.3.6.7 更新 Docker Compose 环境变量
​        打开 `.env.example`，在 Sandbox 配置区域加入：

```Plain
SANDBOX_MAX_FILE_READ_BYTES=65536
SANDBOX_MAX_FILE_WRITE_BYTES=524288
SANDBOX_MAX_UPLOAD_SIZE=10485760
```

​        打开 `docker-compose.yml`，在 `sandbox.environment` 中加入：

```YAML
      MAX_FILE_READ_BYTES: ${SANDBOX_MAX_FILE_READ_BYTES:-65536}
      MAX_FILE_WRITE_BYTES: ${SANDBOX_MAX_FILE_WRITE_BYTES:-524288}
      MAX_UPLOAD_SIZE: ${SANDBOX_MAX_UPLOAD_SIZE:-10485760}
```

##### 16.3.6.7.1 代码讲解
​        `.env.example` 面向使用者。
​        `docker-compose.yml` 面向容器运行时。
​        这里变量名看起来有一层转换：

```Plain
SANDBOX_MAX_FILE_READ_BYTES -> MAX_FILE_READ_BYTES
```

​        左边是项目根目录 `.env` 中的名字，带 `SANDBOX_` 前缀，避免和主 API 的文件配置混淆。
​        右边是 Sandbox 容器内读取的名字，对应 `Settings.max_file_read_bytes`。

#### 16.3.6.8 在主 API 中增加 Sandbox 配置
​        打开 `api/app/core/config.py`，在文件配置后加入：

```Python
    sandbox_api_base_url: str = "http://localhost:8100/api"
    sandbox_api_timeout_seconds: float = 10.0
```

​        同时在 `.env.example` 的 API 配置区域加入：

```Plain
SANDBOX_API_BASE_URL=http://sandbox:8100/api
SANDBOX_API_TIMEOUT_SECONDS=10
```

​        在 `docker-compose.yml` 的 `api.environment` 中加入：

```YAML
      SANDBOX_API_BASE_URL: ${SANDBOX_API_BASE_URL:-http://sandbox:8100/api}
      SANDBOX_API_TIMEOUT_SECONDS: ${SANDBOX_API_TIMEOUT_SECONDS:-10}
```

##### 16.3.6.8.1 字段含义
​        `sandbox_api_base_url` 是主 API 访问 Sandbox API 的基础地址。直接在本机运行时，它可以是 `http://localhost:8100/api`；放进 Docker Compose 后，它必须变成 `http://sandbox:8100/api`，因为容器里的 `localhost` 指向的是当前容器自己，不是另一个服务。
​        `sandbox_api_timeout_seconds` 则控制主 API 等待 Sandbox 响应的最长时间。文件读写通常不应该无限等待，如果 Sandbox 不可用、网络不通或接口卡住，主 API 应该尽快把错误暴露出来，让 Agent 事件流和前端都能看到真实失败原因。

##### 16.3.6.8.2 代码讲解
​        本地直接运行主 API 时，默认地址是：

```Plain
http://localhost:8100/api
```

​        Docker Compose 中运行主 API 时，地址是：

```Plain
http://sandbox:8100/api
```

​        因为容器里不能用 `localhost` 访问另一个容器。`sandbox` 是 Docker Compose 服务名。

#### 16.3.6.9 实现主 API 的 Sandbox 文件客户端
​        创建 `api/app/infrastructure/sandbox/__init__.py`：

```Python
"""Sandbox API clients used by the main API service."""
```

​        创建 `api/app/infrastructure/sandbox/file_client.py`：

```Python
from typing import Any

import httpx

from app.core.exceptions import AppException

class SandboxFileClient:
    """主 API 访问 Sandbox 文件接口的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        # base_url 指向 Sandbox 服务地址，例如 http://sandbox:8100/api。
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：封装文件列表 =====================
    def list_files(self, path: str = ".") -> dict[str, Any]:
        return self._request("GET", "/files", params={"path": path})

    # ===================== 第2步：封装文件读取 =====================
    def read_file(self, path: str) -> dict[str, Any]:
        return self._request("GET", "/files/read", params={"path": path})

    # ===================== 第3步：封装文件写入 =====================
    def write_file(
        self,
        path: str,
        content: str,
        create_parent: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/write",
            json={
                "path": path,
                "content": content,
                "create_parent": create_parent,
            },
        )

    # ===================== 第4步：封装文本替换 =====================
    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/files/replace",
            json={
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
            },
        )

    # ===================== 第5步：封装文件删除 =====================
    def delete_path(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", "/files", params={"path": path})

    # ===================== 第6步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox returned invalid data",
                code=502,
                status_code=502,
            )
        return data
```

##### 16.3.6.9.1 这段代码在流程中的位置
​        `SandboxFileClient` 位于主 API 的基础设施层。
​        它不处理业务决策，只负责把主 API 的工具调用转换成 Sandbox HTTP 请求。

##### 16.3.6.9.2 调用链路
​        读取文件时链路是：

```Plain
FileTool
  |
  v
SandboxFileClient.read_file()
  |
  v
GET http://sandbox:8100/api/files/read?path=...
  |
  v
SandboxFileService.read_file()
```

##### 16.3.6.9.3 关键代码逐段解释
​        `base_url.rstrip("/")` 是为了避免拼接路径时出现双斜杠：

```Plain
http://sandbox:8100/api//files
```

​        `_request()` 统一处理所有 Sandbox 响应。这样每个文件方法不用重复写异常处理。
​        如果 Sandbox 不可用，`httpx.HTTPError` 会被转换成主 API 的 `AppException`，前端会拿到统一错误响应。
​        如果 Sandbox 返回非 JSON，说明请求可能打到了错误服务，或者 Nginx 返回了 HTML 错误页。这种情况也统一转成 502。

##### 16.3.6.9.4 为什么这样设计
​        FileTool 不直接依赖 `httpx`。
​        FileTool 依赖的是 `SandboxFileClient`。这样工具代码只关心“读文件、写文件”，不关心 HTTP 方法、路径、超时和响应格式。

#### 16.3.6.10 实现 Sandbox FileTool
​        创建 `api/app/infrastructure/agent_tools/sandbox_file.py`：

```Python
from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.infrastructure.sandbox.file_client import SandboxFileClient

def build_sandbox_file_client() -> SandboxFileClient:
    """根据主 API 配置创建 Sandbox 文件客户端。"""

    return SandboxFileClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )

def register_sandbox_file_tools(
    registry: ToolRegistry,
    client: SandboxFileClient | None = None,
) -> None:
    """把 Sandbox 文件能力注册成 Agent 可调用工具。"""

    file_client = client or build_sandbox_file_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_list",
                description="列出 Sandbox 工作目录中的文件和子目录。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要浏览的相对路径，默认是 workspace 根目录。",
                        required=False,
                    )
                ],
            ),
            handler=lambda path=".": _format_file_list(file_client.list_files(path or ".")),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_read",
                description="读取 Sandbox 工作目录中的文本文件。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要读取的文件相对路径。",
                    )
                ],
            ),
            handler=lambda path: _format_file_content(file_client.read_file(path)),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_write",
                description="向 Sandbox 工作目录写入文本文件。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要写入的文件相对路径。",
                    ),
                    ToolParameter(
                        name="content",
                        type="string",
                        description="要写入文件的文本内容。",
                    ),
                ],
            ),
            handler=lambda path, content: _format_write_result(
                file_client.write_file(path=path, content=content)
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_replace",
                description="替换 Sandbox 文本文件中的指定内容。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要修改的文件相对路径。",
                    ),
                    ToolParameter(
                        name="old_text",
                        type="string",
                        description="需要被替换的原文本。",
                    ),
                    ToolParameter(
                        name="new_text",
                        type="string",
                        description="替换后的新文本。",
                    ),
                ],
            ),
            handler=lambda path, old_text, new_text: _format_replace_result(
                file_client.replace_text(
                    path=path,
                    old_text=old_text,
                    new_text=new_text,
                )
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="file_delete",
                description="删除 Sandbox 工作目录中的文件或目录。",
                parameters=[
                    ToolParameter(
                        name="path",
                        type="string",
                        description="要删除的文件或目录相对路径。",
                    )
                ],
            ),
            handler=lambda path: _format_delete_result(file_client.delete_path(path)),
        )
    )

def _format_file_list(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return f"{data.get('current_path', '.')} 目录为空。"

    lines = [f"当前目录：{data.get('current_path', '.')}"]
    for item in items:
        marker = "目录" if item.get("type") == "directory" else "文件"
        lines.append(
            f"- [{marker}] {item.get('path')} ({item.get('size', 0)} bytes)"
        )
    return "\n".join(lines)

def _format_file_content(data: dict) -> str:
    suffix = "\n\n内容已截断。" if data.get("truncated") else ""
    return f"文件：{data.get('path')}\n大小：{data.get('size')} bytes\n\n{data.get('content', '')}{suffix}"

def _format_write_result(data: dict) -> str:
    return f"文件已写入：{data.get('path')}，大小 {data.get('size')} bytes。"

def _format_replace_result(data: dict) -> str:
    return (
        f"文件已替换：{data.get('path')}，"
        f"替换次数 {data.get('replacements')}。\n\n{data.get('content', '')}"
    )

def _format_delete_result(data: dict) -> str:
    if data.get("deleted"):
        return f"路径已删除：{data.get('path')}"
    return f"路径未删除：{data.get('path')}"
```

##### 16.3.6.10.1 这段代码在流程中的位置
​        这是主 API 的工具注册代码。
​        它把 Sandbox 文件 API 包装成 Agent 能理解的工具 schema。

##### 16.3.6.10.2 输入和输出
​        模型或前端看到的工具是：

```Plain
file_write(path, content)
file_read(path)
file_replace(path, old_text, new_text)
```

​        工具返回给 Agent 的是字符串，例如：

```Plain
文件已写入：notes/hello.txt，大小 13 bytes。
```

##### 16.3.6.10.3 调用链路
​        调用 `file_write` 时：

```Plain
AgentTool.call()
  |
  v
handler=lambda path, content: ...
  |
  v
SandboxFileClient.write_file()
  |
  v
Sandbox /api/files/write
```

##### 16.3.6.10.4 为什么这样设计
​        工具返回 `str`，是为了和第 12 章的工具协议保持一致。
​        当前 `AgentTool` 的 handler 类型是：

```Python
Callable[..., str]
```

​        所以本阶段把 Sandbox 返回的结构化数据格式化成文本。后续如果工具协议升级为结构化输出，可以把 `ToolCallResult.output` 扩展为 `dict` 或新增 `metadata` 字段。

##### 16.3.6.10.5 小白最容易困惑的点
​        这里没有用 `@agent_tool` 装饰器，是因为 FileTool 需要持有 `SandboxFileClient`。
​        装饰器适合简单纯函数工具，比如 `summarize_text()`。
​        FileTool 需要访问外部服务，所以用 `AgentTool(...)` 手动创建更清晰。

#### 16.3.6.11 把 FileTool 注册进工具列表
​        打开 `api/app/infrastructure/agent_tools/builtin.py`，新增 import：

```Python
from app.infrastructure.agent_tools.sandbox_file import register_sandbox_file_tools
```

​        然后在 `build_builtin_tool_registry()` 中加入：

```Python
    register_sandbox_file_tools(registry)
```

​        修改后函数如下：

```Python
def build_builtin_tool_registry() -> ToolRegistry:
    """注册并返回本章可用的内置工具。"""

    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    register_sandbox_file_tools(registry)
    return registry
```

##### 16.3.6.11.1 代码讲解
​        第 12 章创建工具注册表时，只有三个教学工具：

```Plain
summarize_text
extract_keywords
draft_plan
```

​        本阶段加入：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

​        这意味着访问：

```Plain
GET /api/agent-core/tools
```

​        应该能看到这些文件工具。

### 16.3.7 关键理解
​        本阶段最重要的是“路径安全”。
​        文件工具不是简单地把用户传入的路径交给 `open()`。
​        正确流程是：

```Plain
用户传入相对路径
  |
  v
拼到 workspace 下面
  |
  v
resolve() 归一化真实路径
  |
  v
确认真实路径仍然在 workspace 内
  |
  v
允许读写
```

​        这样可以拦住：

```Plain
../.env
/etc/passwd
notes/../../secret.txt
```

​        第二个重点是“主 API 不直接操作文件”。
​        主 API 通过 HTTP 调用 Sandbox：

```Plain
主 API -> Sandbox API -> /workspace
```

​        这个边界会让后续 DockerSandbox、多任务隔离、远程沙箱更容易实现。
​        第三个重点是“工具协议和沙箱协议分层”。
​        Sandbox API 返回结构化 JSON，FileTool 返回给 Agent 的是可读文本。两者不是一层：

```Plain
Sandbox API：给程序调用
FileTool 输出：给 Agent/模型理解
```

### 16.3.8 技术难点与亮点
​        本阶段的技术难点首先是路径安全。文件工具不是把用户传进来的字符串直接交给 `open()`，而是必须把相对路径拼到 `workspace` 下，再用 `resolve()` 折叠真实路径，最后确认这个真实路径仍然位于工作目录内部。只要这一步漏掉，`../.env`、`/etc/passwd` 或 `notes/../../secret.txt` 都可能变成越界访问。
​        第二个难点是文件内容并不总是理想文本。读取大文件时需要截断，读取非 UTF-8 字节时不能让接口崩溃，上传文件时还要引入 `python-multipart` 才能解析 `multipart/form-data`。主 API 侧还要注意 Docker Compose 网络里的服务名：容器访问 Sandbox 应该使用 `http://sandbox:8100/api`，而不是本机调试时常见的 `localhost:8100`。
​        本阶段的亮点，是文件能力从一开始就运行在独立 Sandbox 服务中，而不是和主 API 耦合在一起。Sandbox API 面向程序，返回结构化 JSON；FileTool 面向 Agent，把结构化结果整理成可读文本；工具注册表则让这些能力可以被 `/api/agent-core/tools` 发现。`truncated` 字段也为后续上下文工程和分段读取留下了清楚的信号。

### 16.3.9 面试考点
​        面试里问到这一阶段，最容易展开的是“为什么文件工具必须运行在沙箱中”。回答时不要只说“安全”，而要讲清楚主 API 的职责是会话、任务和调度，文件读写属于执行环境，应该被限制在 `workspace` 里，并由 Sandbox 统一做路径校验和大小限制。
​        路径穿越也是一个高频追问点。可以用 `../.env` 举例说明：字符串看起来只是一个相对路径，但经过 `resolve()` 后可能已经跳出了工作目录。正确做法是得到真实路径后，再检查它是否等于 `workspace` 或者位于 `workspace.parents` 关系内。上传接口需要 `python-multipart`，是因为浏览器上传文件使用 `multipart/form-data`，FastAPI 解析这种格式需要额外依赖。
​        主 API 容器不能用 `localhost:8100` 访问 Sandbox，是因为容器里的 `localhost` 指向当前主 API 容器自己。Compose 网络中应该使用服务名 `sandbox`。至于 FileTool 不直接返回原始 JSON，是因为当前工具协议给 Agent 的输出是字符串，程序接口和模型可读输出属于两个层次，不能混在一起。

### 16.3.10 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 16.3.10.1 检查 Sandbox 依赖锁文件

```Bash
cd sandbox
uv lock --check
```

​        预期看到类似：

```Plain
Resolved ... packages
```

#### 16.3.10.2 检查 Python 编译
​        检查 Sandbox：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/sandbox
uv run python -m compileall app
```

​        检查主 API：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/api
uv run python -m compileall app
```

​        预期没有 Python 语法错误。
​        本地直接运行 Sandbox 时，如果没有设置环境变量，文件会写入：

```Plain
sandbox/workspace
```

​        Docker Compose 运行时，`docker-compose.yml` 会把 `SANDBOX_WORKSPACE_DIR` 映射成容器里的：

```Plain
/workspace
```

#### 16.3.10.3 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        如果镜像已经构建过，可以执行：

```Bash
docker compose up -d sandbox api nginx
```

​        如果改了依赖或 Dockerfile，需要重新构建：

```Bash
docker compose build sandbox api
docker compose up -d sandbox api nginx
```

​        如果 Nginx 返回旧页面或 404，重启 Nginx：

```Bash
docker compose restart nginx
```

#### 16.3.10.4 验证 Sandbox 文件 API
​        写入文件：

```Bash
curl -X POST http://localhost:8088/sandbox-api/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","content":"hello sandbox"}'
```

​        预期返回：

```JSON
{"code":200,"message":"success","data":{"path":"notes/hello.txt","size":13}}
```

​        读取文件：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=notes/hello.txt"
```

​        预期能看到：

```Plain
hello sandbox
```

​        列出目录：

```Bash
curl "http://localhost:8088/sandbox-api/files?path=notes"
```

​        预期能看到：

```Plain
hello.txt
```

​        替换文本：

```Bash
curl -X POST http://localhost:8088/sandbox-api/files/replace \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/hello.txt","old_text":"sandbox","new_text":"file api"}'
```

​        再次读取：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=notes/hello.txt"
```

​        预期能看到：

```Plain
hello file api
```

#### 16.3.10.5 验证路径穿越防护
​        执行：

```Bash
curl "http://localhost:8088/sandbox-api/files/read?path=../README.md"
```

​        预期返回错误，消息类似：

```Plain
path escapes workspace
```

​        这说明 Sandbox 没有允许访问 workspace 外面的文件。

#### 16.3.10.6 验证 FileTool 已注册
​        执行：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期工具列表里能看到：

```Plain
file_list
file_read
file_write
file_replace
file_delete
```

#### 16.3.10.7 验证 FileTool 调用
​        调用 `file_read`：

```Bash
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"notes/hello.txt","tool_name":"file_read"}'
```

​        如果文件存在，预期返回的 `tool_result.output` 里能看到文件内容。
​        如果提示 Sandbox 连接失败，先确认：

```Bash
docker compose ps
curl http://localhost:8088/sandbox-api/status
```

### 16.3.11 阶段小结
​        本阶段完成了 Sandbox 文件能力的第一版。Sandbox 侧新增了文件请求和响应模型，也新增了负责路径安全、读写限制、上传保存和下载路径处理的 `SandboxFileService`。在 HTTP 层，`/api/files` 已经覆盖列表、读取、写入、替换、删除、上传和下载这些基础动作。
​        主 API 侧新增了 `SandboxFileClient`，让业务服务不直接碰沙箱文件系统，而是通过 HTTP 调用 Sandbox。FileTool 又把这些客户端方法包装成 Agent 能理解的工具，并注册进统一工具表。到这一阶段结束时，Agent 已经具备“通过沙箱读写文件”的基础能力，而且这条能力从一开始就带有路径边界、大小限制和清晰的服务分层。

### 16.3.12 代码
​        暂时无法在飞书文档外展示此内容

## 16.4 本章小结

​        完成“Sandbox 服务骨架初成”和“Sandbox 文件 API 与 FileTool 成形”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第十五章. 上下文工程](15-上下文工程.md) · [返回目录](../README.md) · [第十七章. Sandbox Shell 与 Docker 隔离 →](17-Sandbox%20Shell%20与%20Docker%20隔离.md)
