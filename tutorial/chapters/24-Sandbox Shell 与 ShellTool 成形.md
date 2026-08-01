# 第二十四章. Sandbox Shell 与 ShellTool 成形

## 24.1 本章目标
​        学完本章后，你将能够：
​        第 23 章让 Agent 能通过沙箱读写文件，但读写文件只是执行能力的开始。真正做项目时，Agent 还需要运行测试、查看目录、执行脚本、安装依赖、观察命令输出，并在进程卡住时主动终止。也就是说，文件系统解决“改什么”，Shell 才开始解决“怎么跑”。
​        学完本章后，你应该能说明为什么 Shell 命令必须放在 Sandbox 中执行，也能理解 `asyncio.create_subprocess_shell` 如何启动子进程。更关键的是，本章不会把 Shell 做成“一次请求直接等完整结果”的接口，而是把命令抽象成 Shell 会话，支持启动、查询、等待、写入 stdin 和终止。主 API 侧会封装 `SandboxShellClient`，再把能力注册成 `shell_run` 和 `shell_status`。前端则不再新增孤立演示卡片，而是在既有工具结果区域里用终端样式展示 Shell 输出。

## 24.2 最终效果
​        本章结束后，Sandbox 服务会新增 Shell API：

```Plain
POST /api/shell/sessions
GET  /api/shell/sessions
GET  /api/shell/sessions/{session_id}
POST /api/shell/sessions/{session_id}/wait
POST /api/shell/sessions/{session_id}/write
POST /api/shell/sessions/{session_id}/terminate
```

​        通过 Nginx 访问时，路径是：

```Plain
POST /sandbox-api/shell/sessions
GET  /sandbox-api/shell/sessions/{session_id}
```

​        主 API 会新增两个工具：

```Plain
shell_run
shell_status
```

​        前端不新增独立 Shell 演示页，而是在已有工具结果区域里识别 `shell_*` 工具，并用终端样式展示输出。
​        本章完成后的调用链路是：

```Plain
前端工具预览
  |
  v
主 API AgentCoreService
  |
  v
ShellTool
  |
  v
SandboxShellClient
  |
  v
Sandbox Shell API
  |
  v
workspace 中的子进程
```

## 24.3 本章要解决的问题
​        第 23 章已经让 Agent 可以通过 FileTool 读写文件。
​        但文件工具只能修改文件，不能运行命令。真实任务里经常需要：

```Plain
查看当前目录
运行脚本
安装依赖
执行测试
读取命令输出
停止卡住的进程
```

​        这些动作不能在主 API 容器里执行。主 API 是业务服务，不能让模型直接影响它的运行环境。
​        所以本章把 Shell 能力放进 Sandbox 服务，再由主 API 通过 ShellTool 调用。

## 24.4 本章技术方案
​        本章采用“Shell 会话”的设计，而不是“一次请求直接返回全部结果”。
​        原因是命令可能有三种情况：
​        有些命令会很快结束，例如 `pwd` 或 `ls`；有些命令会运行一段时间，例如测试命令或依赖安装；还有一些命令可能等待输入，甚至长期运行，例如开发服务。如果所有命令都要求在同一个 HTTP 请求里等到完整结果，那么一旦命令变慢，调用方就会被挂住。
​        所以 Sandbox 需要先创建会话：

```Plain
POST /api/shell/sessions
```

​        再通过会话 ID 做后续操作：

```Plain
读取状态
等待完成
写入 stdin
终止进程
```

​        本章会在 Sandbox 中新增 Shell 请求和响应模型，实现 `SandboxShellService`，并把 `/api/shell` 路由挂进沙箱应用。主 API 侧会新增 `SandboxShellClient` 和 ShellTool，前端侧则改造已有工具结果区域，让 `shell_*` 工具结果以终端样式展示。
​        本章暂时不做多沙箱实例路由、命令白名单、执行审计、WebSocket 实时终端，也不会把 ShellTool 接入完整 ReAct 自动执行策略。这些能力都依赖更成熟的沙箱实例管理和工具预览体系。第 25 章会处理 DockerSandbox 适配，第 29 章会集中整理工具预览面板。

## 24.5 本章删除和合并的临时 UI
​        本章不新增新的 Shell 演示卡片。
​        第 17 章留下的“Agent 记忆与工具协议”区域已经能选择工具、运行工具、展示工具结果。ShellTool 本质上也是工具，所以本章直接改造这个区域：
​        原来的工具选择和运行入口会保留下来，Memory 展示也会继续保留。真正变化的是工具结果渲染：当工具名以 `shell_` 开头时，结果区会使用深色终端样式，让用户一眼知道这里展示的是命令执行状态、退出码和标准输出。
​        同时，本章会删除第 16 章遗留的前端思维模型演示区域：

```Plain
ui/app/components/agent-thinking-panel.tsx
ui/app/hooks/use-agent-thinking.ts
ui/app/stores/agent-thinking-store.ts
ui/app/lib/agent-thinking-api.ts
```

​        这些文件曾经用来讲普通 ChatBot、CoT、ReAct 和工具调用之间的区别。进入 ShellTool 章节后，这类概念演示已经完成教学任务，继续放在首页会干扰真实工作台。
​        删除后，后端的 Agent 思维模型接口仍然保留，作为前面章节的接口成果；但前端首页不再展示这块临时演示 UI。
​        这样做的目的，是让前端从“演示卡片堆叠”开始向“统一工具预览面板”收敛。
​        第 29 章会继续把 file、shell、browser、search 等工具事件统一到真正的工具预览面板中。

## 24.6 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
docker-compose.yml
sandbox/README.md
docs/course/chapters/24-shell-tool.md
sandbox/app/core/config.py
sandbox/app/schemas/shell.py
sandbox/app/services/shell_service.py
sandbox/app/api/routes/shell.py
sandbox/app/api/router.py
api/app/core/config.py
api/app/infrastructure/sandbox/shell_client.py
api/app/infrastructure/agent_tools/sandbox_shell.py
api/app/infrastructure/agent_tools/builtin.py
ui/app/components/agent-core-panel.tsx
ui/app/stores/agent-core-store.ts
ui/app/types.ts
ui/app/page.tsx
```

## 24.7 实施步骤
### 24.7.1 补充 Shell 配置
​        打开 `sandbox/app/core/config.py`，在文件配置后加入：

```Python
    shell_output_limit: int = 64 * 1024
    shell_default_timeout_seconds: float = 10.0
```

​        打开 `.env.example`，在 Sandbox 配置中加入：

```Plain
SANDBOX_SHELL_OUTPUT_LIMIT=65536
SANDBOX_SHELL_DEFAULT_TIMEOUT_SECONDS=10
```

​        打开 `docker-compose.yml`，在 `sandbox.environment` 中加入：

```YAML
      SHELL_OUTPUT_LIMIT: ${SANDBOX_SHELL_OUTPUT_LIMIT:-65536}
      SHELL_DEFAULT_TIMEOUT_SECONDS: ${SANDBOX_SHELL_DEFAULT_TIMEOUT_SECONDS:-10}
```

#### 24.7.1.1 字段含义
​        `shell_output_limit` 控制每个 Shell 会话最多保留多少字节输出。Shell 命令和普通接口不同，它可能持续刷屏，如果不限制输出，沙箱进程内存会随着 stdout 和 stderr 不断增长。
​        `shell_default_timeout_seconds` 则是等待命令完成时的默认时间。调用方可以先启动命令，再等待一小段时间；如果命令没有结束，接口返回当前状态，而不是让请求无限挂起。这个配置让 ShellTool 可以兼顾短命令和长命令。

#### 24.7.1.2 代码讲解
​        Shell 命令和普通接口不同。普通接口通常很快返回，Shell 命令可能持续输出。
​        如果不限制输出，类似下面的命令会不断产生内容：

```Bash
yes
```

​        所以本章先用 `shell_output_limit` 做内存保护。超出限制时只保留最后一段输出，并用 `output_truncated=true` 告诉调用方输出被裁剪过。

### 24.7.2 定义 Shell 请求和响应模型
​        创建 `sandbox/app/schemas/shell.py`：

```Python
from pydantic import BaseModel, Field


class ShellExecuteRequest(BaseModel):
    command: str = Field(min_length=1)  # 要在沙箱中执行的命令。
    cwd: str = "."  # 相对 workspace 的工作目录，避免暴露容器真实路径。


class ShellWriteRequest(BaseModel):
    input: str  # 写入进程 stdin 的内容，通常用于交互式命令。


class ShellWaitRequest(BaseModel):
    timeout_seconds: float | None = None  # 本次等待多久；为空时使用配置默认值。


class ShellSessionResponse(BaseModel):
    id: str  # Shell 会话 ID，后续读取、等待、写入、终止都用它。
    command: str  # 启动会话时执行的原始命令。
    cwd: str  # 命令所在的相对工作目录。
    status: str  # running、succeeded、failed、terminated 中的一种。
    return_code: int | None  # 进程退出码；运行中时为 null。
    output: str  # 已收集的 stdout 和 stderr。
    output_truncated: bool  # 输出是否因为超过限制被裁剪。


class ShellSessionListResponse(BaseModel):
    items: list[ShellSessionResponse]  # 当前沙箱内仍然记录的 Shell 会话。


class ShellWriteResponse(BaseModel):
    id: str  # 被写入的 Shell 会话 ID。
    written: int  # 写入 stdin 的字节数。


class ShellTerminateResponse(BaseModel):
    id: str  # 被终止的 Shell 会话 ID。
    terminated: bool  # 成功发出终止信号时为 true。
```

#### 24.7.2.1 这段代码在流程中的位置
​        这些模型是 Sandbox Shell API 的协议边界。
​        前端或主 API 不直接接触 `asyncio.subprocess.Process`，只接触这些响应字段。

#### 24.7.2.2 字段含义
​        `id` 是 Shell 会话的核心标识。命令启动之后，后续查询、等待、写入 stdin 和终止进程都靠它找到同一个子进程。`status` 描述当前会话状态，可能是 `running`、`succeeded`、`failed` 或 `terminated`，前端和工具结果都要根据这个状态判断命令是否仍在执行。
​        `return_code` 是进程退出码，运行中时为空，命令完成后才有意义。`output` 合并保存 stdout 和 stderr，便于 Agent 直接阅读命令结果；`output_truncated` 则告诉调用方输出是否因为超过限制被裁剪。Shell 结果不能只看文本内容，还要连同状态和退出码一起解释。

#### 24.7.2.3 为什么这样设计
​        Shell 会话比文件接口多了“状态”。
​        文件写入要么成功，要么失败。Shell 命令可能还在运行，所以必须返回 `running`。
​        后续前端展示 Shell 输出时，也不能只看有没有 `output`，还要看 `status` 和 `return_code`。

### 24.7.3 实现 Sandbox Shell 服务
​        创建 `sandbox/app/services/shell_service.py`。
​        这个文件较长，建议先写完整代码，再看下面的分段讲解：

```Python
import asyncio
from asyncio.subprocess import PIPE, Process
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.shell import (
    ShellSessionListResponse,
    ShellSessionResponse,
    ShellTerminateResponse,
    ShellWriteResponse,
)


@dataclass(slots=True)
class ShellSession:
    """保存一个沙箱命令进程的运行状态。"""

    id: str
    command: str
    cwd: str
    process: Process
    status: str = "running"
    return_code: int | None = None
    output_chunks: list[str] = field(default_factory=list)
    output_truncated: bool = False


class SandboxShellService:
    """管理沙箱里的 Shell 进程会话。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace = Path(settings.workspace_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ShellSession] = {}

    # ===================== 第1步：启动命令 =====================
    async def execute(self, command: str, cwd: str = ".") -> ShellSessionResponse:
        workdir = self._resolve_workdir(cwd)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workdir,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        session = ShellSession(
            id=str(uuid4()),
            command=command,
            cwd=self._to_relative_path(workdir),
            process=process,
        )
        self._sessions[session.id] = session

        asyncio.create_task(self._collect_stream(session, process.stdout, "stdout"))
        asyncio.create_task(self._collect_stream(session, process.stderr, "stderr"))
        asyncio.create_task(self._watch_process(session))

        return self._to_response(session)

    # ===================== 第2步：查询会话 =====================
    def get(self, session_id: str) -> ShellSessionResponse:
        return self._to_response(self._get_session(session_id))

    def list_sessions(self) -> ShellSessionListResponse:
        return ShellSessionListResponse(
            items=[self._to_response(session) for session in self._sessions.values()]
        )

    # ===================== 第3步：等待进程完成 =====================
    async def wait(
        self,
        session_id: str,
        timeout_seconds: float | None = None,
    ) -> ShellSessionResponse:
        session = self._get_session(session_id)
        timeout = timeout_seconds or self.settings.shell_default_timeout_seconds
        try:
            await asyncio.wait_for(session.process.wait(), timeout=timeout)
        except TimeoutError:
            return self._to_response(session)
        return self._to_response(session)

    # ===================== 第4步：写入标准输入 =====================
    async def write(self, session_id: str, value: str) -> ShellWriteResponse:
        session = self._get_session(session_id)
        if session.status != "running" or session.process.stdin is None:
            raise SandboxException(message="shell session is not writable")

        encoded = value.encode("utf-8")
        session.process.stdin.write(encoded)
        await session.process.stdin.drain()
        return ShellWriteResponse(id=session.id, written=len(encoded))

    # ===================== 第5步：终止进程 =====================
    async def terminate(self, session_id: str) -> ShellTerminateResponse:
        session = self._get_session(session_id)
        if session.status == "running":
            session.process.terminate()
            session.status = "terminated"
            try:
                await asyncio.wait_for(session.process.wait(), timeout=2)
            except TimeoutError:
                session.process.kill()
                await session.process.wait()
        return ShellTerminateResponse(id=session.id, terminated=True)

    # ===================== 第6步：后台收集输出和状态 =====================
    async def _collect_stream(
        self,
        session: ShellSession,
        stream: asyncio.StreamReader | None,
        name: str,
    ) -> None:
        if stream is None:
            return

        while True:
            chunk = await stream.readline()
            if not chunk:
                break
            prefix = "" if name == "stdout" else "[stderr] "
            self._append_output(session, prefix + chunk.decode("utf-8", errors="replace"))

    async def _watch_process(self, session: ShellSession) -> None:
        return_code = await session.process.wait()
        session.return_code = return_code
        if session.status == "terminated":
            return
        session.status = "succeeded" if return_code == 0 else "failed"

    def _append_output(self, session: ShellSession, text: str) -> None:
        session.output_chunks.append(text)
        output = "".join(session.output_chunks)
        if len(output.encode("utf-8")) <= self.settings.shell_output_limit:
            return

        session.output_truncated = True
        truncated = output.encode("utf-8")[-self.settings.shell_output_limit :]
        session.output_chunks = [truncated.decode("utf-8", errors="replace")]

    # ===================== 第7步：路径和会话辅助方法 =====================
    def _resolve_workdir(self, cwd: str) -> Path:
        clean_cwd = cwd.strip() or "."
        if Path(clean_cwd).is_absolute():
            raise SandboxException(message="absolute cwd is not allowed")

        target = (self.workspace / clean_cwd).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise SandboxException(message="cwd escapes workspace")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _get_session(self, session_id: str) -> ShellSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SandboxException(
                message="shell session not found",
                code=404,
                status_code=404,
            )
        return session

    def _to_relative_path(self, path: Path) -> str:
        relative = path.resolve().relative_to(self.workspace)
        return "." if str(relative) == "." else relative.as_posix()

    def _to_response(self, session: ShellSession) -> ShellSessionResponse:
        return ShellSessionResponse(
            id=session.id,
            command=session.command,
            cwd=session.cwd,
            status=session.status,
            return_code=session.return_code,
            output="".join(session.output_chunks),
            output_truncated=session.output_truncated,
        )
```

#### 24.7.3.1 这段代码在流程中的位置
​        `SandboxShellService` 是 Sandbox Shell API 的核心。
​        路由负责 HTTP，服务负责进程、输出、状态和安全工作目录。

#### 24.7.3.2 调用链路
​        执行命令的链路是：

```Plain
POST /api/shell/sessions
  |
  v
SandboxShellService.execute()
  |
  v
asyncio.create_subprocess_shell()
  |
  v
后台任务收集 stdout / stderr
```

#### 24.7.3.3 关键代码逐段解释
​        `ShellSession` 保存会话状态。它不是数据库模型，只是当前 Sandbox 进程内的内存状态。
​        `execute()` 启动命令后不会一直阻塞等待，而是创建三个后台任务：

```Python
asyncio.create_task(self._collect_stream(...stdout...))
asyncio.create_task(self._collect_stream(...stderr...))
asyncio.create_task(self._watch_process(session))
```

​        这样接口可以先返回会话 ID，前端或主 API 后续再查询状态。
​        `wait()` 使用 `asyncio.wait_for()`。如果命令在超时时间内完成，就返回最终状态；如果没完成，就返回当前状态。
​        `write()` 只允许写入正在运行的进程。如果进程已经结束，再写 stdin 就会报错。
​        `terminate()` 先尝试温和终止。如果进程没有在 2 秒内退出，再用 `kill()` 强制结束。
​        `_resolve_workdir()` 和第 23 章文件路径校验思路一致。Shell 的工作目录也不能逃出 workspace。

#### 24.7.3.4 为什么这样设计
​        Shell 命令可能运行很久，所以不能让 HTTP 请求一直挂着。
​        会话模型让调用方可以先启动，再等待、查询、写入或终止。
​        本章先把会话放在内存里，因为现在只有一个 Sandbox 服务实例。第 25 章引入 DockerSandbox 后，会继续讨论多容器、多任务时会话归属的问题。

### 24.7.4 创建 Sandbox Shell 路由
​        创建 `sandbox/app/api/routes/shell.py`：

```Python
from fastapi import APIRouter, Depends

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.shell import (
    ShellExecuteRequest,
    ShellSessionListResponse,
    ShellSessionResponse,
    ShellTerminateResponse,
    ShellWaitRequest,
    ShellWriteRequest,
    ShellWriteResponse,
)
from app.services.shell_service import SandboxShellService

router = APIRouter(prefix="/shell", tags=["shell"])

# Shell 会话必须跨请求保存，所以这里使用模块级 service。
shell_service = SandboxShellService(settings=settings)


def get_shell_service() -> SandboxShellService:
    return shell_service


@router.post("/sessions", response_model=ApiResponse[ShellSessionResponse])
async def execute_command(
    payload: ShellExecuteRequest,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(data=await service.execute(payload.command, payload.cwd))


@router.get("/sessions", response_model=ApiResponse[ShellSessionListResponse])
async def list_sessions(
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionListResponse]:
    return ApiResponse(data=service.list_sessions())


@router.get("/sessions/{session_id}", response_model=ApiResponse[ShellSessionResponse])
async def get_session(
    session_id: str,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(data=service.get(session_id))


@router.post(
    "/sessions/{session_id}/wait",
    response_model=ApiResponse[ShellSessionResponse],
)
async def wait_session(
    session_id: str,
    payload: ShellWaitRequest,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellSessionResponse]:
    return ApiResponse(data=await service.wait(session_id, payload.timeout_seconds))


@router.post(
    "/sessions/{session_id}/write",
    response_model=ApiResponse[ShellWriteResponse],
)
async def write_session(
    session_id: str,
    payload: ShellWriteRequest,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellWriteResponse]:
    return ApiResponse(data=await service.write(session_id, payload.input))


@router.post(
    "/sessions/{session_id}/terminate",
    response_model=ApiResponse[ShellTerminateResponse],
)
async def terminate_session(
    session_id: str,
    service: SandboxShellService = Depends(get_shell_service),
) -> ApiResponse[ShellTerminateResponse]:
    return ApiResponse(data=await service.terminate(session_id))
```

#### 24.7.4.1 代码讲解
​        这里故意使用模块级 `shell_service`：

```Python
shell_service = SandboxShellService(settings=settings)
```

​        原因是 Shell 会话要跨请求保存。
​        如果每个请求都重新创建一个 `SandboxShellService`，那么启动命令后，下一次查询就找不到这个会话。
​        这也是本章和文件 API 最大的区别。文件 API 可以每次创建 service，因为文件状态在磁盘上；Shell API 的会话状态在内存里。

### 24.7.5 注册 Shell 路由
​        打开 `sandbox/app/api/router.py`，改成：

```Python
from fastapi import APIRouter

from app.api.routes import files, shell, status, supervisor

api_router = APIRouter()
api_router.include_router(files.router)
api_router.include_router(shell.router)
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
```

​        如果忘记注册，`/api/shell/sessions` 会返回 404。

### 24.7.6 主 API 增加 Shell 客户端配置
​        打开 `api/app/core/config.py`，在 Sandbox 配置后加入：

```Python
    sandbox_shell_wait_timeout_seconds: float = 10.0
```

​        打开 `.env.example`，加入：

```Plain
SANDBOX_SHELL_WAIT_TIMEOUT_SECONDS=10
```

​        打开 `docker-compose.yml`，在 `api.environment` 中加入：

```YAML
      SANDBOX_SHELL_WAIT_TIMEOUT_SECONDS: ${SANDBOX_SHELL_WAIT_TIMEOUT_SECONDS:-10}
```

#### 24.7.6.1 字段含义
​        `sandbox_shell_wait_timeout_seconds` 是主 API 调用 ShellTool 时愿意等待命令完成的时间。
​        如果命令超过这个时间还没结束，工具结果会返回 `running`，而不是一直阻塞。

### 24.7.7 实现主 API 的 Sandbox Shell 客户端
​        创建 `api/app/infrastructure/sandbox/shell_client.py`：

```Python
from typing import Any

import httpx

from app.core.exceptions import AppException


class SandboxShellClient:
    """主 API 访问 Sandbox Shell 接口的同步客户端。"""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        # base_url 指向 Sandbox 服务地址，例如 http://sandbox:8100/api。
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：启动 Shell 会话 =====================
    def execute(self, command: str, cwd: str = ".") -> dict[str, Any]:
        return self._request(
            "POST",
            "/shell/sessions",
            json={"command": command, "cwd": cwd},
        )

    # ===================== 第2步：等待 Shell 会话完成 =====================
    def wait(
        self,
        session_id: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/shell/sessions/{session_id}/wait",
            json={"timeout_seconds": timeout_seconds},
        )

    # ===================== 第3步：查询和控制 Shell 会话 =====================
    def get(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/shell/sessions/{session_id}")

    def write(self, session_id: str, value: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/shell/sessions/{session_id}/write",
            json={"input": value},
        )

    def terminate(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/shell/sessions/{session_id}/terminate")

    # ===================== 第4步：统一处理 Sandbox 响应 =====================
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
                message=f"sandbox shell request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox shell returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox shell request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox shell returned invalid data",
                code=502,
                status_code=502,
            )
        return data
```

#### 24.7.7.1 代码讲解
​        这个客户端和第 23 章的 `SandboxFileClient` 很像。
​        区别是 ShellClient 多了会话操作：

```Plain
execute -> wait -> get/write/terminate
```

​        主 API 不直接使用 `asyncio.create_subprocess_shell`，也不直接读写沙箱文件系统。它只通过 Sandbox API 操作 Shell 会话。

### 24.7.8 实现 ShellTool
​        创建 `api/app/infrastructure/agent_tools/sandbox_shell.py`：

```Python
from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.infrastructure.sandbox.shell_client import SandboxShellClient


def build_sandbox_shell_client() -> SandboxShellClient:
    """根据主 API 配置创建 Sandbox Shell 客户端。"""

    return SandboxShellClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )


def register_sandbox_shell_tools(
    registry: ToolRegistry,
    client: SandboxShellClient | None = None,
) -> None:
    """把 Sandbox Shell 能力注册成 Agent 可调用工具。"""

    shell_client = client or build_sandbox_shell_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="shell_run",
                description="在 Sandbox 工作目录中执行一条 Shell 命令，并等待输出。",
                parameters=[
                    ToolParameter(
                        name="command",
                        type="string",
                        description="要执行的 Shell 命令。",
                    )
                ],
            ),
            handler=lambda command: _format_shell_result(
                _run_and_wait(shell_client, command)
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="shell_status",
                description="查询一个 Sandbox Shell 会话的当前状态和输出。",
                parameters=[
                    ToolParameter(
                        name="session_id",
                        type="string",
                        description="Shell 会话 ID。",
                    )
                ],
            ),
            handler=lambda session_id: _format_shell_result(shell_client.get(session_id)),
        )
    )


def _run_and_wait(client: SandboxShellClient, command: str) -> dict:
    started = client.execute(command=command, cwd=".")
    return client.wait(
        session_id=str(started["id"]),
        timeout_seconds=settings.sandbox_shell_wait_timeout_seconds,
    )


def _format_shell_result(data: dict) -> str:
    output = str(data.get("output") or "").strip()
    if not output:
        output = "<no output>"

    suffix = "\n\n输出已截断。" if data.get("output_truncated") else ""
    return "\n".join(
        [
            f"会话：{data.get('id')}",
            f"命令：{data.get('command')}",
            f"目录：{data.get('cwd')}",
            f"状态：{data.get('status')}",
            f"退出码：{data.get('return_code')}",
            "",
            output + suffix,
        ]
    )
```

#### 24.7.8.1 这段代码在流程中的位置
​        ShellTool 位于主 API 的工具层。
​        它把 Agent 的工具调用转换成 Sandbox Shell API 调用。

#### 24.7.8.2 输入和输出
​        `shell_run` 的输入是：

```JSON
{
  "command": "pwd && ls -la"
}
```

​        输出是适合前端和 Agent 阅读的文本：

```Plain
会话：...
命令：pwd && ls -la
目录：.
状态：succeeded
退出码：0

...
```

#### 24.7.8.3 为什么这样设计
​        本章仍然沿用第 17 章的工具协议：工具 handler 返回字符串。
​        Shell API 原始响应是结构化 JSON，ShellTool 会把它格式化成文本。这样现有 Memory 和工具结果展示不用大改。
​        第 29 章做统一工具预览面板时，可以进一步把 `ToolCallResult` 扩展出结构化元数据。

### 24.7.9 注册 ShellTool
​        打开 `api/app/infrastructure/agent_tools/builtin.py`，新增 import：

```Python
from app.infrastructure.agent_tools.sandbox_shell import register_sandbox_shell_tools
```

​        在 `build_builtin_tool_registry()` 中加入：

```Python
    register_sandbox_shell_tools(registry)
```

​        完整函数变成：

```Python
def build_builtin_tool_registry() -> ToolRegistry:
    """注册并返回本章可用的内置工具。"""

    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    register_sandbox_file_tools(registry)
    register_sandbox_shell_tools(registry)
    return registry
```

### 24.7.10 改造前端工具结果展示
​        打开 `ui/app/components/agent-core-panel.tsx`。
​        先在图标 import 中加入 `Terminal`：

```TypeScript
import {
  Bot,
  Braces,
  Hammer,
  Loader2,
  MessageCircle,
  Terminal,
} from "lucide-react";
```

​        然后把原来的工具结果 `<pre>` 替换成：

```TypeScript
<ToolResultOutput
  output={state.data.tool_result.output}
  toolName={state.data.tool_result.tool_name}
/>
```

​        在 `DemoResult` 后新增：

```TypeScript
// ===================== 第5步：按工具类型展示不同结果形态 =====================
function ToolResultOutput({
  output,
  toolName,
}: {
  output: string;
  toolName: string;
}) {
  if (toolName.startsWith("shell_")) {
    return (
      <div className="mt-3 rounded-md border border-slate-800 bg-slate-950">
        <div className="flex h-9 items-center gap-2 border-b border-slate-800 px-3 text-xs font-medium text-slate-300">
          <Terminal size={14} aria-hidden="true" />
          Sandbox Shell
        </div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-3 text-xs leading-5 text-emerald-100">
          {output}
        </pre>
      </div>
    );
  }

  return (
    <pre className="mt-3 whitespace-pre-wrap rounded-md bg-white p-3 text-xs leading-5 text-slate-700">
      {output}
    </pre>
  );
}
```

#### 24.7.10.1 这段代码在流程中的位置
​        这是本章的前端产品化收敛点。
​        没有新增 Shell 独立页面，而是让现有工具结果区支持 Shell 输出。

#### 24.7.10.2 组件输入和输出
​        `ToolResultOutput` 接收：

```Plain
toolName
output
```

​        如果 `toolName` 以 `shell_` 开头，就使用终端样式。
​        否则继续使用普通白底代码块。

#### 24.7.10.3 为什么这样设计
​        Shell 输出和普通文本摘要不一样。它通常包含命令、状态、退出码和多行终端输出。
​        终端样式能让用户更快理解“这是命令执行结果”，也为第 29 章统一工具预览面板做准备。
​        本章不新建大块页面，避免前端继续变成接口调试台。

## 24.8 关键理解
​        本章最重要的是 Shell 会话。
​        命令执行不是普通函数调用。
​        普通函数调用：

```Plain
输入 -> 执行 -> 输出
```

​        Shell 会话：

```Plain
启动进程 -> 获得 session_id -> 后台收集输出 -> 查询/等待/写入/终止
```

​        第二个重点是 Shell 的安全边界。
​        本章仍然只允许命令在 workspace 目录中执行。工作目录不能写绝对路径，也不能用 `../` 逃出 workspace。
​        第三个重点是前端收敛。
​        能力可以不断增加，但入口不应该无限增加。ShellTool 是工具能力，所以优先进入工具结果区域，而不是新增孤立演示面板。

## 24.9 技术难点与亮点
​        本章的技术难点在于 Shell 命令不是普通函数。进程启动后，stdout 和 stderr 需要后台持续收集，命令状态也要跨请求保存。否则启动命令的请求结束之后，下一次查询就找不到进程，也看不到后续输出。
​        命令还会出现很多不规整状态：可能超时，可能失败，可能没有输出，也可能输出过大。stdin 写入也只能发生在进程仍然运行时，进程结束后再写就应该明确报错。前端同样不能把 Shell 输出当成普通摘要文本，它需要用终端样式呈现状态、退出码和多行输出。
​        本章的亮点，是 Shell 能力被隔离在 Sandbox 服务中，主 API 只通过 ShellClient 操作会话，不直接执行命令。ShellTool 复用第 17 章的工具协议，前端也没有继续堆新的演示卡片，而是开始把工具展示能力收敛到同一块区域。

## 24.10 面试考点
​        面试里问到这一章，首先要讲清楚为什么 Shell 命令不能在主 API 容器里执行。主 API 是业务服务，负责会话、任务和调度；Shell 命令会启动外部进程、读写工作目录、产生 stdout 和 stderr，甚至可能长期运行。把这类副作用放进主 API，会让业务服务承担执行环境风险。
​        `asyncio.create_subprocess_shell` 和同步命令执行的区别，也可以围绕“不会把请求线程一直阻塞在命令执行上”来解释。它让 Sandbox 可以启动进程后返回会话，再用后台任务收集输出和退出码。Shell 会话 ID 的价值就在这里：调用方可以用同一个 ID 查询、等待、写入或终止同一个进程。
​        Shell 工作目录也必须做路径穿越防护。命令虽然是要执行的，但它的 `cwd` 仍然应该限制在 `workspace` 内，不能用绝对路径或 `../` 跳出去。否则文件 API 做了边界，Shell API 却打开了旁路。

## 24.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 24.11.1 编译检查
​        检查 Sandbox：

```Bash
cd sandbox
uv run python -m compileall app
```

​        检查主 API：

```Bash
cd ../api
uv run python -m compileall app
```

​        检查前端类型：

```Bash
cd ../ui
pnpm typecheck
```

### 24.11.2 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        如果镜像已经存在：

```Bash
docker compose up -d sandbox api nginx
```

​        如果修改后需要重新构建：

```Bash
docker compose build sandbox api ui
docker compose up -d sandbox api ui nginx
```

​        如果 Nginx 返回旧路由，执行：

```Bash
docker compose restart nginx
```

### 24.11.3 验证 Sandbox Shell API
​        启动命令：

```Bash
curl -X POST http://localhost:8088/sandbox-api/shell/sessions \
  -H "Content-Type: application/json" \
  -d '{"command":"pwd && ls -la"}'
```

​        预期返回里有：

```Plain
status: running
id: ...
```

​        记录返回的 `id`，等待命令完成：

```Bash
curl -X POST http://localhost:8088/sandbox-api/shell/sessions/{session_id}/wait \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds":5}'
```

​        预期返回中能看到：

```Plain
status: succeeded
return_code: 0
output: ...
```

### 24.11.4 验证 ShellTool 注册
​        执行：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期能看到：

```Plain
shell_run
shell_status
```

### 24.11.5 验证 ShellTool 调用
​        执行：

```Bash
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"pwd && ls -la","tool_name":"shell_run"}'
```

​        预期 `tool_result.output` 中能看到：

```Plain
命令：pwd && ls -la
状态：succeeded
退出码：0
```

### 24.11.6 验证前端展示
​        访问：

```Plain
http://localhost:8088
```

​        在“Agent 记忆与工具协议”区域：
​        选择 `shell_run`，输入 `pwd && ls -la`，然后点击运行。工具结果区域应该显示深色终端样式，其中包含命令、状态、退出码和输出内容。
​        这一步确认 Shell 能力已经进入前端工具预览，而不是只停留在接口验证。

## 24.12 常见问题

### 24.12.1 Shell 命令一直是 `running` 怎么办？
​        `running` 不一定是错误，它只表示进程还没有退出。像 `sleep 30`、开发服务、监听命令或等待输入的命令，都可能长期保持这个状态。可以继续调用 `/wait` 等待更长时间，也可以通过 `/terminate` 主动终止会话。
​        如果是通过 `shell_run` 调用，工具会按照 `SANDBOX_SHELL_WAIT_TIMEOUT_SECONDS` 等待一段时间。超过这个时间还没结束时，工具结果会返回当前会话状态，而不是一直阻塞。

### 24.12.2 `shell_run` 返回 Sandbox 连接失败怎么办？
​        这说明主 API 没有成功访问 Sandbox Shell API。先确认 `atlas-sandbox` 容器正在运行，再确认主 API 的 `SANDBOX_API_BASE_URL` 在 Docker Compose 中是 `http://sandbox:8100/api`。
​        如果直接在本地运行主 API，而 Sandbox 也在本机运行，才使用 `http://localhost:8100/api`。容器内外的地址不能混用，这是这类错误最常见的原因。

### 24.12.3 为什么前端没有新增 Shell 页面？
​        Shell 是工具能力，不是一个独立产品模块。第 17 章已经有工具选择、运行和结果展示区域，本章把 Shell 输出合并进去，是为了让用户在一个地方理解所有工具调用结果。
​        如果每新增一个工具就新增一个演示卡片，首页会很快变成接口调试台。后续第 29 章会继续把 file、shell、browser 和 search 等工具事件收敛到统一工具预览面板。

### 24.12.4 为什么输出会截断？
​        命令输出可能非常大，尤其是日志、测试输出或持续刷屏命令。如果 Sandbox 不限制输出，内存会随着会话输出不断增长。`SANDBOX_SHELL_OUTPUT_LIMIT` 用来控制每个会话最多保留多少字节。
​        输出被截断时，接口会返回 `output_truncated=true`。这让调用方知道当前看到的不是完整输出，后续可以调整限制或设计更细的日志读取方式。

## 24.13 本章小结
​        本章完成了 Sandbox Shell 能力。Sandbox 侧新增了 Shell 请求和响应模型，也新增了负责进程启动、会话记录、后台输出收集、等待、stdin 写入和终止的 `SandboxShellService`。路由层围绕会话 ID 暴露启动、查询、等待、写入和终止接口。
​        主 API 侧新增了 `SandboxShellClient`，并把 `shell_run` 和 `shell_status` 注册进工具表。前端则在原有工具结果区域里识别 `shell_*` 工具，并用终端样式展示命令输出。从这一章开始，Agent 不只会读写文件，还能在 Sandbox 中执行命令，同时仍然保持主 API 和执行环境之间的边界。

## 24.14 下一章预告
​        第 25 章会实现 DockerSandbox 适配，把文件和 Shell 能力从“固定 Sandbox 服务”推进到“任务级沙箱容器”。
