# 第十七章. Sandbox Shell 与 Docker 隔离

## 17.1 合章说明

​        旧版教程把“Sandbox Shell 与 ShellTool 成形”与“DockerSandbox 契合”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 17.2 第一阶段：Sandbox Shell 与 ShellTool 成形

### 17.2.1 本阶段目标
​        学完本阶段后，你将能够：
​        第 16 章让 Agent 能通过沙箱读写文件，但读写文件只是执行能力的开始。真正做项目时，Agent 还需要运行测试、查看目录、执行脚本、安装依赖、观察命令输出，并在进程卡住时主动终止。也就是说，文件系统解决“改什么”，Shell 才开始解决“怎么跑”。
​        学完本阶段后，你应该能说明为什么 Shell 命令必须放在 Sandbox 中执行，也能理解 `asyncio.create_subprocess_shell` 如何启动子进程。更关键的是，本阶段不会把 Shell 做成“一次请求直接等完整结果”的接口，而是把命令抽象成 Shell 会话，支持启动、查询、等待、写入 stdin 和终止。主 API 侧会封装 `SandboxShellClient`，再把能力注册成 `shell_run` 和 `shell_status`。前端则不再新增孤立演示卡片，而是在既有工具结果区域里用终端样式展示 Shell 输出。

### 17.2.2 最终效果
​        本阶段结束后，Sandbox 服务会新增 Shell API：

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
​        本阶段完成后的调用链路是：

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

### 17.2.3 本阶段要解决的问题
​        第 16 章已经让 Agent 可以通过 FileTool 读写文件。
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
​        所以本阶段把 Shell 能力放进 Sandbox 服务，再由主 API 通过 ShellTool 调用。

### 17.2.4 本阶段技术方案
​        本阶段采用“Shell 会话”的设计，而不是“一次请求直接返回全部结果”。
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

​        本阶段会在 Sandbox 中新增 Shell 请求和响应模型，实现 `SandboxShellService`，并把 `/api/shell` 路由挂进沙箱应用。主 API 侧会新增 `SandboxShellClient` 和 ShellTool，前端侧则改造已有工具结果区域，让 `shell_*` 工具结果以终端样式展示。
​        本阶段暂时不做多沙箱实例路由、命令白名单、执行审计、WebSocket 实时终端，也不会把 ShellTool 接入完整 ReAct 自动执行策略。这些能力都依赖更成熟的沙箱实例管理和工具预览体系。本章第二阶段会处理 DockerSandbox 适配，第 19 章会集中整理工具预览面板。

### 17.2.5 本阶段删除和合并的临时 UI
​        本阶段不新增新的 Shell 演示卡片。
​        第 12 章留下的“Agent 记忆与工具协议”区域已经能选择工具、运行工具、展示工具结果。ShellTool 本质上也是工具，所以本阶段直接改造这个区域：
​        原来的工具选择和运行入口会保留下来，Memory 展示也会继续保留。真正变化的是工具结果渲染：当工具名以 `shell_` 开头时，结果区会使用深色终端样式，让用户一眼知道这里展示的是命令执行状态、退出码和标准输出。
​        同时，本阶段会删除第 12 章遗留的前端思维模型演示区域：

```Plain
ui/app/components/agent-thinking-panel.tsx
ui/app/hooks/use-agent-thinking.ts
ui/app/stores/agent-thinking-store.ts
ui/app/lib/agent-thinking-api.ts
```

​        这些文件曾经用来讲普通 ChatBot、CoT、ReAct 和工具调用之间的区别。进入 ShellTool 章节后，这类概念演示已经完成教学任务，继续放在首页会干扰真实工作台。
​        删除后，后端的 Agent 思维模型接口仍然保留，作为前面章节的接口成果；但前端首页不再展示这块临时演示 UI。
​        这样做的目的，是让前端从“演示卡片堆叠”开始向“统一工具预览面板”收敛。
​        第 19 章会继续把 file、shell、browser、search 等工具事件统一到真正的工具预览面板中。

### 17.2.6 新增和修改的文件

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

### 17.2.7 实施步骤
#### 17.2.7.1 补充 Shell 配置
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

##### 17.2.7.1.1 字段含义
​        `shell_output_limit` 控制每个 Shell 会话最多保留多少字节输出。Shell 命令和普通接口不同，它可能持续刷屏，如果不限制输出，沙箱进程内存会随着 stdout 和 stderr 不断增长。
​        `shell_default_timeout_seconds` 则是等待命令完成时的默认时间。调用方可以先启动命令，再等待一小段时间；如果命令没有结束，接口返回当前状态，而不是让请求无限挂起。这个配置让 ShellTool 可以兼顾短命令和长命令。

##### 17.2.7.1.2 代码讲解
​        Shell 命令和普通接口不同。普通接口通常很快返回，Shell 命令可能持续输出。
​        如果不限制输出，类似下面的命令会不断产生内容：

```Bash
yes
```

​        所以本阶段先用 `shell_output_limit` 做内存保护。超出限制时只保留最后一段输出，并用 `output_truncated=true` 告诉调用方输出被裁剪过。

#### 17.2.7.2 定义 Shell 请求和响应模型
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

##### 17.2.7.2.1 这段代码在流程中的位置
​        这些模型是 Sandbox Shell API 的协议边界。
​        前端或主 API 不直接接触 `asyncio.subprocess.Process`，只接触这些响应字段。

##### 17.2.7.2.2 字段含义
​        `id` 是 Shell 会话的核心标识。命令启动之后，后续查询、等待、写入 stdin 和终止进程都靠它找到同一个子进程。`status` 描述当前会话状态，可能是 `running`、`succeeded`、`failed` 或 `terminated`，前端和工具结果都要根据这个状态判断命令是否仍在执行。
​        `return_code` 是进程退出码，运行中时为空，命令完成后才有意义。`output` 合并保存 stdout 和 stderr，便于 Agent 直接阅读命令结果；`output_truncated` 则告诉调用方输出是否因为超过限制被裁剪。Shell 结果不能只看文本内容，还要连同状态和退出码一起解释。

##### 17.2.7.2.3 为什么这样设计
​        Shell 会话比文件接口多了“状态”。
​        文件写入要么成功，要么失败。Shell 命令可能还在运行，所以必须返回 `running`。
​        后续前端展示 Shell 输出时，也不能只看有没有 `output`，还要看 `status` 和 `return_code`。

#### 17.2.7.3 实现 Sandbox Shell 服务
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

##### 17.2.7.3.1 这段代码在流程中的位置
​        `SandboxShellService` 是 Sandbox Shell API 的核心。
​        路由负责 HTTP，服务负责进程、输出、状态和安全工作目录。

##### 17.2.7.3.2 调用链路
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

##### 17.2.7.3.3 关键代码逐段解释
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
​        `_resolve_workdir()` 和第 16 章文件路径校验思路一致。Shell 的工作目录也不能逃出 workspace。

##### 17.2.7.3.4 为什么这样设计
​        Shell 命令可能运行很久，所以不能让 HTTP 请求一直挂着。
​        会话模型让调用方可以先启动，再等待、查询、写入或终止。
​        本阶段先把会话放在内存里，因为现在只有一个 Sandbox 服务实例。本章第二阶段引入 DockerSandbox 后，会继续讨论多容器、多任务时会话归属的问题。

#### 17.2.7.4 创建 Sandbox Shell 路由
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

##### 17.2.7.4.1 代码讲解
​        这里故意使用模块级 `shell_service`：

```Python
shell_service = SandboxShellService(settings=settings)
```

​        原因是 Shell 会话要跨请求保存。
​        如果每个请求都重新创建一个 `SandboxShellService`，那么启动命令后，下一次查询就找不到这个会话。
​        这也是本阶段和文件 API 最大的区别。文件 API 可以每次创建 service，因为文件状态在磁盘上；Shell API 的会话状态在内存里。

#### 17.2.7.5 注册 Shell 路由
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

#### 17.2.7.6 主 API 增加 Shell 客户端配置
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

##### 17.2.7.6.1 字段含义
​        `sandbox_shell_wait_timeout_seconds` 是主 API 调用 ShellTool 时愿意等待命令完成的时间。
​        如果命令超过这个时间还没结束，工具结果会返回 `running`，而不是一直阻塞。

#### 17.2.7.7 实现主 API 的 Sandbox Shell 客户端
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

##### 17.2.7.7.1 代码讲解
​        这个客户端和第 16 章的 `SandboxFileClient` 很像。
​        区别是 ShellClient 多了会话操作：

```Plain
execute -> wait -> get/write/terminate
```

​        主 API 不直接使用 `asyncio.create_subprocess_shell`，也不直接读写沙箱文件系统。它只通过 Sandbox API 操作 Shell 会话。

#### 17.2.7.8 实现 ShellTool
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

##### 17.2.7.8.1 这段代码在流程中的位置
​        ShellTool 位于主 API 的工具层。
​        它把 Agent 的工具调用转换成 Sandbox Shell API 调用。

##### 17.2.7.8.2 输入和输出
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

##### 17.2.7.8.3 为什么这样设计
​        本阶段仍然沿用第 12 章的工具协议：工具 handler 返回字符串。
​        Shell API 原始响应是结构化 JSON，ShellTool 会把它格式化成文本。这样现有 Memory 和工具结果展示不用大改。
​        第 19 章做统一工具预览面板时，可以进一步把 `ToolCallResult` 扩展出结构化元数据。

#### 17.2.7.9 注册 ShellTool
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

#### 17.2.7.10 改造前端工具结果展示
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

##### 17.2.7.10.1 这段代码在流程中的位置
​        这是本阶段的前端产品化收敛点。
​        没有新增 Shell 独立页面，而是让现有工具结果区支持 Shell 输出。

##### 17.2.7.10.2 组件输入和输出
​        `ToolResultOutput` 接收：

```Plain
toolName
output
```

​        如果 `toolName` 以 `shell_` 开头，就使用终端样式。
​        否则继续使用普通白底代码块。

##### 17.2.7.10.3 为什么这样设计
​        Shell 输出和普通文本摘要不一样。它通常包含命令、状态、退出码和多行终端输出。
​        终端样式能让用户更快理解“这是命令执行结果”，也为第 19 章统一工具预览面板做准备。
​        本阶段不新建大块页面，避免前端继续变成接口调试台。

### 17.2.8 关键理解
​        本阶段最重要的是 Shell 会话。
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
​        本阶段仍然只允许命令在 workspace 目录中执行。工作目录不能写绝对路径，也不能用 `../` 逃出 workspace。
​        第三个重点是前端收敛。
​        能力可以不断增加，但入口不应该无限增加。ShellTool 是工具能力，所以优先进入工具结果区域，而不是新增孤立演示面板。

### 17.2.9 技术难点与亮点
​        本阶段的技术难点在于 Shell 命令不是普通函数。进程启动后，stdout 和 stderr 需要后台持续收集，命令状态也要跨请求保存。否则启动命令的请求结束之后，下一次查询就找不到进程，也看不到后续输出。
​        命令还会出现很多不规整状态：可能超时，可能失败，可能没有输出，也可能输出过大。stdin 写入也只能发生在进程仍然运行时，进程结束后再写就应该明确报错。前端同样不能把 Shell 输出当成普通摘要文本，它需要用终端样式呈现状态、退出码和多行输出。
​        本阶段的亮点，是 Shell 能力被隔离在 Sandbox 服务中，主 API 只通过 ShellClient 操作会话，不直接执行命令。ShellTool 复用第 12 章的工具协议，前端也没有继续堆新的演示卡片，而是开始把工具展示能力收敛到同一块区域。

### 17.2.10 面试考点
​        面试里问到这一阶段，首先要讲清楚为什么 Shell 命令不能在主 API 容器里执行。主 API 是业务服务，负责会话、任务和调度；Shell 命令会启动外部进程、读写工作目录、产生 stdout 和 stderr，甚至可能长期运行。把这类副作用放进主 API，会让业务服务承担执行环境风险。
​        `asyncio.create_subprocess_shell` 和同步命令执行的区别，也可以围绕“不会把请求线程一直阻塞在命令执行上”来解释。它让 Sandbox 可以启动进程后返回会话，再用后台任务收集输出和退出码。Shell 会话 ID 的价值就在这里：调用方可以用同一个 ID 查询、等待、写入或终止同一个进程。
​        Shell 工作目录也必须做路径穿越防护。命令虽然是要执行的，但它的 `cwd` 仍然应该限制在 `workspace` 内，不能用绝对路径或 `../` 跳出去。否则文件 API 做了边界，Shell API 却打开了旁路。

### 17.2.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 17.2.11.1 编译检查
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

#### 17.2.11.2 启动服务
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

#### 17.2.11.3 验证 Sandbox Shell API
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

#### 17.2.11.4 验证 ShellTool 注册
​        执行：

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期能看到：

```Plain
shell_run
shell_status
```

#### 17.2.11.5 验证 ShellTool 调用
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

#### 17.2.11.6 验证前端展示
​        访问：

```Plain
http://localhost:8088
```

​        在“Agent 记忆与工具协议”区域：
​        选择 `shell_run`，输入 `pwd && ls -la`，然后点击运行。工具结果区域应该显示深色终端样式，其中包含命令、状态、退出码和输出内容。
​        这一步确认 Shell 能力已经进入前端工具预览，而不是只停留在接口验证。

### 17.2.12 阶段小结
​        本阶段完成了 Sandbox Shell 能力。Sandbox 侧新增了 Shell 请求和响应模型，也新增了负责进程启动、会话记录、后台输出收集、等待、stdin 写入和终止的 `SandboxShellService`。路由层围绕会话 ID 暴露启动、查询、等待、写入和终止接口。
​        主 API 侧新增了 `SandboxShellClient`，并把 `shell_run` 和 `shell_status` 注册进工具表。前端则在原有工具结果区域里识别 `shell_*` 工具，并用终端样式展示命令输出。从这一阶段开始，Agent 不只会读写文件，还能在 Sandbox 中执行命令，同时仍然保持主 API 和执行环境之间的边界。

## 17.3 第二阶段：DockerSandbox 契合

### 17.3.1 本阶段目标
​        学完本阶段后，你将能够：
​        第 16 章和本章第一阶段分别把文件与 Shell 能力接到了 Sandbox，但主 API 仍然是直接拿一个固定的 Sandbox 地址去调用。这个方式能跑通教学代码，却还没有形成真正的“沙箱管理”抽象。只要后续出现多任务、多容器或任务级隔离，散落在各处的 Sandbox URL 就会变成维护负担。
​        学完本阶段后，你应该能理解为什么主 API 需要一个 Sandbox 管理器，而不是让工具和路由到处直接拼 Sandbox 地址。本阶段会设计当前任务沙箱的创建、获取、健康等待和释放接口，在主 API 中封装 `DockerSandboxManager`，再通过它代理文件读取、文件写入和 Shell 命令执行。前端工作台右侧会出现“任务沙箱”状态面板，让用户在执行任务时能看到当前执行环境是否可用。

### 17.3.2 最终效果
​        本阶段结束后，主 API 会新增一组 Sandbox 管理接口：

```Plain
GET    /api/sandboxes/current
POST   /api/sandboxes/current/ensure
POST   /api/sandboxes/current/wait
DELETE /api/sandboxes/current
GET    /api/sandboxes/current/files/read
POST   /api/sandboxes/current/files/write
POST   /api/sandboxes/current/shell/run
```

​        前端工作台右侧会新增“任务沙箱”状态面板，用于展示：

```Plain
实例 ID
容器名称
沙箱状态
健康检查说明
```

​        本阶段完成后的调用链路是：

```Plain
前端工作台
  |
  v
主 API /api/sandboxes/current
  |
  v
DockerSandboxManager
  |
  +-- SandboxFileClient
  |
  +-- SandboxShellClient
  |
  v
atlas-sandbox
```

### 17.3.3 本阶段要解决的问题
​        第 16 章和本章第一阶段已经分别实现了 FileTool 和 ShellTool。
​        但现在主 API 的工具代码直接使用：

```Plain
SANDBOX_API_BASE_URL=http://sandbox:8100/api
```

​        这能跑通功能，但还不是一个完整的沙箱管理模型。
​        后续真实任务会遇到这些问题：

```Plain
当前任务使用哪个沙箱？
沙箱是否已经启动？
沙箱是否健康？
如果前端要查看沙箱状态，访问哪个接口？
如果后续一任务一容器，主 API 应该在哪里改？
```

​        所以本阶段加入 `DockerSandboxManager`，先把“当前沙箱实例”的管理入口固定下来。

### 17.3.4 本阶段技术方案
​        本阶段不直接把 Docker socket 挂给主 API。
​        原因是 Docker socket 权限很高，如果过早暴露，会把课程复杂度和安全风险一下拉高。
​        本阶段采用过渡方案：
​        Docker Compose 仍然负责启动 `atlas-sandbox` 容器，主 API 不直接操作 Docker Engine。主 API 新增 `DockerSandboxManager`，由它代表“当前任务沙箱”这个概念，并通过健康检查判断 Sandbox 服务是否可用。文件和 Shell 的代理调用也统一经过这个管理器，前端则只通过主 API 查看当前任务沙箱状态。
​        这个设计先固定调用形状：

```Plain
create / get / wait / release / file proxy / shell proxy
```

​        等本阶段之后需要一任务一容器时，可以把 `DockerSandboxManager` 的实现方式换成真实 Docker Engine 操作，路由和前端不用大改。
​        本阶段暂时不做这些内容：
​        本阶段不会把 `/var/run/docker.sock` 挂给主 API，也不会动态创建多个 Docker 容器。沙箱资源限制、任务和沙箱实例的一对一绑定、沙箱运行日志审计，都属于更靠后的生产化和安全加固内容。这里先把接口形状和适配层做稳定，避免过早把 Docker 权限和生命周期管理复杂度引入主 API。

### 17.3.5 本阶段删除和合并的临时 UI
​        本阶段不新增独立“DockerSandbox 演示页”。
​        沙箱状态是工作台的一部分，所以本阶段把它放进 `ChatWorkspace` 右侧：

```Plain
任务沙箱
计划面板
文件面板
上下文面板
事件记录
```

​        这样用户在执行任务时能看到当前沙箱是否可用，而不是在另一个孤立区域手动调接口。
​        同时，本阶段删除第 12 章留下的 Agent 核心演示前端入口。
​        第 12 章的演示面板只用于解释 Memory、工具协议和工具调用结果，不应该一直停留在真实工作台首页。后续工具调用结果会进入统一的事件时间线和工具预览面板，而不是保留一个独立演示区域。

### 17.3.6 新增、修改和删除的文件

```Plain
.env.example
README.md
api/README.md
docker-compose.yml
docs/course/chapters/25-docker-sandbox.md
api/app/core/config.py
api/app/schemas/sandbox.py
api/app/infrastructure/sandbox/manager.py
api/app/api/routes/sandboxes.py
api/app/api/router.py
ui/app/types.ts
ui/app/lib/sandbox-api.ts
ui/app/components/sandbox-status-panel.tsx
ui/app/components/chat-workspace.tsx
ui/app/page.tsx
ui/app/components/agent-core-panel.tsx
ui/app/hooks/use-agent-core.ts
ui/app/stores/agent-core-store.ts
ui/app/lib/agent-core-api.ts
```

​        其中最后四个 `agent-core` 前端文件会在本阶段删除。后端的 Agent Core 接口和领域代码保留，因为后续 Agent 执行链路仍然会复用工具协议能力；删除的是页面上的临时演示 UI。

### 17.3.7 实施步骤
#### 17.3.7.1 补充主 API 沙箱配置
​        打开 `api/app/core/config.py`，在 Sandbox 配置后加入：

```Python
    docker_sandbox_id: str = "default"
    docker_sandbox_name: str = "atlas-sandbox"
    docker_sandbox_wait_retries: int = 10
    docker_sandbox_wait_interval_seconds: float = 1.0
```

​        打开 `.env.example`，加入：

```Plain
DOCKER_SANDBOX_ID=default
DOCKER_SANDBOX_NAME=atlas-sandbox
DOCKER_SANDBOX_WAIT_RETRIES=10
DOCKER_SANDBOX_WAIT_INTERVAL_SECONDS=1
```

​        打开 `docker-compose.yml`，在 `api.environment` 中加入：

```YAML
      DOCKER_SANDBOX_ID: ${DOCKER_SANDBOX_ID:-default}
      DOCKER_SANDBOX_NAME: ${DOCKER_SANDBOX_NAME:-atlas-sandbox}
      DOCKER_SANDBOX_WAIT_RETRIES: ${DOCKER_SANDBOX_WAIT_RETRIES:-10}
      DOCKER_SANDBOX_WAIT_INTERVAL_SECONDS: ${DOCKER_SANDBOX_WAIT_INTERVAL_SECONDS:-1}
```

##### 17.3.7.1.1 字段含义
​        `docker_sandbox_id` 是主 API 识别当前沙箱实例的稳定 ID。本阶段只有一个 Compose 沙箱，所以它可以固定为 `default`；以后如果变成一任务一沙箱，这个 ID 就可以替换成任务 ID、会话 ID 或容器 ID。
​        `docker_sandbox_name` 对应当前 Docker Compose 沙箱容器名，也就是 `atlas-sandbox`。`docker_sandbox_wait_retries` 和 `docker_sandbox_wait_interval_seconds` 共同控制健康等待逻辑：主 API 可以按固定次数和间隔轮询 Sandbox 状态，而不是只检查一次就判断失败。

##### 17.3.7.1.2 代码讲解
​        本阶段只有一个 Compose 沙箱，所以 ID 固定为 `default`。
​        后续如果变成“一任务一沙箱”，这个 ID 可以替换成任务 ID、会话 ID 或容器 ID。

#### 17.3.7.2 定义主 API 沙箱响应模型
​        创建 `api/app/schemas/sandbox.py`：

```Python
from pydantic import BaseModel, Field

class SandboxInstanceResponse(BaseModel):
    id: str  # 主 API 识别当前沙箱实例的稳定 ID。
    name: str  # Docker Compose 中的沙箱容器名。
    base_url: str  # 主 API 访问 Sandbox 服务的 API 地址。
    status: str  # ready、unavailable、released 等状态。
    message: str  # 给前端展示的状态说明。

class SandboxWaitRequest(BaseModel):
    retries: int | None = Field(default=None, ge=1)
    interval_seconds: float | None = Field(default=None, gt=0)

class SandboxFileReadResponse(BaseModel):
    path: str
    content: str
    size: int
    truncated: bool

class SandboxFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str
    create_parent: bool = True

class SandboxFileWriteResponse(BaseModel):
    path: str
    size: int

class SandboxShellRunRequest(BaseModel):
    command: str = Field(min_length=1)
    cwd: str = "."
    timeout_seconds: float | None = None

class SandboxShellRunResponse(BaseModel):
    id: str
    command: str
    cwd: str
    status: str
    return_code: int | None
    output: str
    output_truncated: bool
```

##### 17.3.7.2.1 这段代码在流程中的位置
​        这些模型属于主 API，不属于 Sandbox 服务。
​        它们描述的是主 API 对前端暴露的沙箱管理协议。

##### 17.3.7.2.2 为什么这样设计
​        主 API 不应该直接把 Sandbox 服务的所有字段原样透出。
​        本阶段先让主 API 控制对外协议。后续 DockerSandbox 变成多实例后，前端仍然可以继续使用：

```Plain
/api/sandboxes/current
```

​        而不用知道具体容器地址如何变化。

#### 17.3.7.3 实现 DockerSandboxManager
​        创建 `api/app/infrastructure/sandbox/manager.py`：

```Python
from dataclasses import dataclass
from time import sleep

import httpx

from app.core.config import Settings
from app.infrastructure.sandbox.file_client import SandboxFileClient
from app.infrastructure.sandbox.shell_client import SandboxShellClient

@dataclass(slots=True)
class SandboxInstance:
    """主 API 视角下的当前 DockerSandbox 实例。"""

    id: str
    name: str
    base_url: str
    status: str
    message: str

class DockerSandboxManager:
    """管理当前 Compose 沙箱容器，并提供健康检查。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.file_client = SandboxFileClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        )
        self.shell_client = SandboxShellClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        )

    # ===================== 第1步：获取或创建当前沙箱实例 =====================
    def ensure_current(self) -> SandboxInstance:
        if self._is_healthy():
            return self._build_instance("ready", "Sandbox 服务已经可用。")
        return self._build_instance("unavailable", "Sandbox 服务暂时不可用。")

    def get_current(self) -> SandboxInstance:
        return self.ensure_current()

    # ===================== 第2步：等待沙箱健康 =====================
    def wait_until_ready(
        self,
        retries: int | None = None,
        interval_seconds: float | None = None,
    ) -> SandboxInstance:
        max_retries = retries or self.settings.docker_sandbox_wait_retries
        interval = interval_seconds or self.settings.docker_sandbox_wait_interval_seconds

        for _ in range(max_retries):
            if self._is_healthy():
                return self._build_instance("ready", "Sandbox 服务已经通过健康检查。")
            sleep(interval)

        return self._build_instance("unavailable", "等待 Sandbox 健康检查超时。")

    # ===================== 第3步：释放当前沙箱引用 =====================
    def release_current(self) -> SandboxInstance:
        return self._build_instance(
            "released",
            "当前阶段沙箱由 Docker Compose 管理，主 API 只释放引用，不停止容器。",
        )

    # ===================== 第4步：代理文件和 Shell 能力 =====================
    def read_file(self, path: str) -> dict:
        return self.file_client.read_file(path)

    def write_file(self, path: str, content: str, create_parent: bool) -> dict:
        return self.file_client.write_file(path, content, create_parent)

    def run_shell(
        self,
        command: str,
        cwd: str,
        timeout_seconds: float | None,
    ) -> dict:
        started = self.shell_client.execute(command=command, cwd=cwd)
        return self.shell_client.wait(
            session_id=str(started["id"]),
            timeout_seconds=timeout_seconds or self.settings.sandbox_shell_wait_timeout_seconds,
        )

    # ===================== 第5步：健康检查辅助方法 =====================
    def _is_healthy(self) -> bool:
        try:
            with httpx.Client(timeout=self.settings.sandbox_api_timeout_seconds) as client:
                response = client.get(f"{self.settings.sandbox_api_base_url}/status")
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False

        return response.status_code == 200 and payload.get("code") == 200

    def _build_instance(self, status: str, message: str) -> SandboxInstance:
        return SandboxInstance(
            id=self.settings.docker_sandbox_id,
            name=self.settings.docker_sandbox_name,
            base_url=self.settings.sandbox_api_base_url,
            status=status,
            message=message,
        )
```

##### 17.3.7.3.1 这段代码在流程中的位置
​        `DockerSandboxManager` 是主 API 对沙箱的统一入口。
​        工具、路由、前端都不需要直接拼 Sandbox 地址。它们通过 manager 获取状态或代理调用。

##### 17.3.7.3.2 调用链路
​        前端刷新任务沙箱状态：

```Plain
SandboxStatusPanel
  |
  v
GET /api/sandboxes/current
  |
  v
DockerSandboxManager.get_current()
  |
  v
GET http://sandbox:8100/api/status
```

​        运行 Shell：

```Plain
POST /api/sandboxes/current/shell/run
  |
  v
DockerSandboxManager.run_shell()
  |
  v
SandboxShellClient.execute()
  |
  v
SandboxShellClient.wait()
```

##### 17.3.7.3.3 为什么这样设计
​        现在的 `release_current()` 不会停止 Docker 容器。
​        这是刻意设计。当前容器由 Docker Compose 管理，如果主 API 随便停止它，课程环境会变得难排查。
​        本阶段先把“释放沙箱”这个接口形状做出来，后续真正一任务一容器时，再把实现方式替换成 Docker Engine 删除容器。

#### 17.3.7.4 新增 Sandbox 管理路由
​        创建 `api/app/api/routes/sandboxes.py`：

```Python
from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.infrastructure.sandbox.manager import DockerSandboxManager, SandboxInstance
from app.schemas.common import ApiResponse
from app.schemas.sandbox import (
    SandboxFileReadResponse,
    SandboxFileWriteRequest,
    SandboxFileWriteResponse,
    SandboxInstanceResponse,
    SandboxShellRunRequest,
    SandboxShellRunResponse,
    SandboxWaitRequest,
)

router = APIRouter(prefix="/sandboxes", tags=["sandboxes"])

def build_sandbox_manager() -> DockerSandboxManager:
    return DockerSandboxManager(settings=settings)

def to_instance_response(instance: SandboxInstance) -> SandboxInstanceResponse:
    return SandboxInstanceResponse(
        id=instance.id,
        name=instance.name,
        base_url=instance.base_url,
        status=instance.status,
        message=instance.message,
    )

@router.get("/current", response_model=ApiResponse[SandboxInstanceResponse])
async def get_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    return ApiResponse(data=to_instance_response(manager.get_current()))

@router.post("/current/ensure", response_model=ApiResponse[SandboxInstanceResponse])
async def ensure_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    return ApiResponse(data=to_instance_response(manager.ensure_current()))

@router.post("/current/wait", response_model=ApiResponse[SandboxInstanceResponse])
async def wait_current_sandbox(
    payload: SandboxWaitRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    return ApiResponse(
        data=to_instance_response(
            manager.wait_until_ready(
                retries=payload.retries,
                interval_seconds=payload.interval_seconds,
            )
        )
    )

@router.delete("/current", response_model=ApiResponse[SandboxInstanceResponse])
async def release_current_sandbox(
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxInstanceResponse]:
    return ApiResponse(data=to_instance_response(manager.release_current()))

@router.get("/current/files/read", response_model=ApiResponse[SandboxFileReadResponse])
async def read_sandbox_file(
    path: str = Query(min_length=1),
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxFileReadResponse]:
    return ApiResponse(data=SandboxFileReadResponse(**manager.read_file(path)))

@router.post(
    "/current/files/write",
    response_model=ApiResponse[SandboxFileWriteResponse],
)
async def write_sandbox_file(
    payload: SandboxFileWriteRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxFileWriteResponse]:
    return ApiResponse(
        data=SandboxFileWriteResponse(
            **manager.write_file(
                path=payload.path,
                content=payload.content,
                create_parent=payload.create_parent,
            )
        )
    )

@router.post(
    "/current/shell/run",
    response_model=ApiResponse[SandboxShellRunResponse],
)
async def run_sandbox_shell(
    payload: SandboxShellRunRequest,
    manager: DockerSandboxManager = Depends(build_sandbox_manager),
) -> ApiResponse[SandboxShellRunResponse]:
    return ApiResponse(
        data=SandboxShellRunResponse(
            **manager.run_shell(
                command=payload.command,
                cwd=payload.cwd,
                timeout_seconds=payload.timeout_seconds,
            )
        )
    )
```

##### 17.3.7.4.1 代码讲解
​        这组路由有两类：
​        管理类接口围绕当前沙箱实例展开，包括读取当前状态、确保实例存在、等待健康检查通过，以及释放当前引用。代理类接口则把文件读取、文件写入和 Shell 运行统一放到 `/api/sandboxes/current` 下面。
​        代理类接口不是为了替代第 23、24 章的工具，而是为了给前端和后续任务系统一个统一入口。
​        第 19 章工具预览面板会更依赖这种统一入口。

#### 17.3.7.5 注册 Sandbox 路由
​        打开 `api/app/api/router.py`，新增 `sandboxes`：

```Python
from app.api.routes import (
    agent_core,
    agent_thinking,
    config,
    files,
    llm,
    sandboxes,
    sessions,
    status,
)
```

​        并注册：

```Python
api_router.include_router(sandboxes.router)
```

#### 17.3.7.6 新增前端 Sandbox API
​        创建 `ui/app/lib/sandbox-api.ts`：

```TypeScript
import { requestApi } from "./api";
import type { SandboxInstanceData } from "../types";

// ===================== 第1步：读取当前任务沙箱状态 =====================
export function fetchCurrentSandbox(): Promise<SandboxInstanceData> {
  return requestApi<SandboxInstanceData>("/api/sandboxes/current");
}

// ===================== 第2步：等待沙箱通过健康检查 =====================
export function waitCurrentSandbox(): Promise<SandboxInstanceData> {
  return requestApi<SandboxInstanceData>("/api/sandboxes/current/wait", {
    method: "POST",
    body: JSON.stringify({
      retries: 3,
      interval_seconds: 1,
    }),
  });
}
```

​        同时在 `ui/app/types.ts` 中加入：

```TypeScript
export type SandboxInstanceData = {
  id: string;
  name: string;
  base_url: string;
  status: string;
  message: string;
};
```

##### 17.3.7.6.1 代码讲解
​        前端只访问主 API：

```Plain
/api/sandboxes/current
```

​        不直接访问：

```Plain
/sandbox-api/status
```

​        这样前端不会绑定 Sandbox 服务路径。后续多沙箱时，主 API 可以继续隐藏具体容器地址。

#### 17.3.7.7 新增任务沙箱状态面板
​        创建 `ui/app/components/sandbox-status-panel.tsx`：

```TypeScript
import { Box, CheckCircle2, Loader2, RefreshCcw, XCircle } from "lucide-react";

import type { LoadState, SandboxInstanceData } from "../types";

type SandboxStatusPanelProps = {
  onRefresh: () => void;
  refreshing: boolean;
  state: LoadState<SandboxInstanceData>;
};

// ===================== 第1步：展示当前任务沙箱状态 =====================
export function SandboxStatusPanel({
  onRefresh,
  refreshing,
  state,
}: SandboxStatusPanelProps) {
  const view = buildSandboxView(state);
  const Icon = view.icon;

  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">任务沙箱</h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            当前会话使用的 Sandbox 运行状态
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
          disabled={refreshing}
          onClick={onRefresh}
          title="刷新沙箱状态"
          type="button"
        >
          {refreshing ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <RefreshCcw size={16} />
          )}
        </button>
      </div>

      <div className="mt-4 flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
        <Icon className={view.iconClassName} size={18} aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-900">{view.title}</p>
          <p className="mt-1 truncate text-xs text-slate-500">{view.message}</p>
        </div>
      </div>

      {state.type === "ready" ? (
        <dl className="mt-4 grid gap-2 text-xs text-slate-600">
          <div className="flex justify-between gap-3">
            <dt>实例</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.id}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>容器</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.name}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>状态</dt>
            <dd className="truncate font-medium text-slate-900">{state.data.status}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function buildSandboxView(state: LoadState<SandboxInstanceData>) {
  if (state.type === "loading") {
    return {
      icon: Loader2,
      iconClassName: "animate-spin text-slate-500",
      message: "正在检查 Sandbox 健康状态",
      title: "检测中",
    };
  }
  if (state.type === "error") {
    return {
      icon: XCircle,
      iconClassName: "text-rose-600",
      message: state.message,
      title: "沙箱异常",
    };
  }
  if (state.data.status === "ready") {
    return {
      icon: CheckCircle2,
      iconClassName: "text-emerald-600",
      message: state.data.message,
      title: "沙箱可用",
    };
  }
  return {
    icon: Box,
    iconClassName: "text-amber-600",
    message: state.data.message,
    title: "沙箱未就绪",
  };
}
```

##### 17.3.7.7.1 代码讲解
​        这个组件不直接请求接口。
​        它只接收 `state`、`refreshing` 和 `onRefresh`。请求逻辑放在页面层。
​        这样 `SandboxStatusPanel` 只是展示组件，后续如果要把沙箱状态接到 zustand store，也不用改它的 UI 结构。

#### 17.3.7.8 把沙箱状态放进工作台
​        打开 `ui/app/components/chat-workspace.tsx`，引入组件：

```TypeScript
import { SandboxStatusPanel } from "./sandbox-status-panel";
```

​        给 props 增加：

```TypeScript
onRefreshSandbox: () => void;
sandbox: LoadState<SandboxInstanceData>;
sandboxRefreshing: boolean;
```

​        然后把组件放到右侧面板顶部：

```TypeScript
<SandboxStatusPanel
  onRefresh={onRefreshSandbox}
  refreshing={sandboxRefreshing}
  state={sandbox}
/>
```

##### 17.3.7.8.1 为什么放在这里
​        沙箱状态和当前会话任务强相关。
​        如果放到首页顶部，它会像系统状态；如果放到右侧工作台，它更像“当前任务执行环境”。
​        本阶段选择放在 `ChatWorkspace` 右侧，为后续 Shell、Browser、VNC 面板继续收敛做准备。

#### 17.3.7.9 删除旧演示面板
​        打开 `ui/app/page.tsx`，删除第 12 章临时演示面板相关代码。
​        先删除这两个 import：

```TypeScript
import { AgentCorePanel } from "./components/agent-core-panel";
import { useAgentCore } from "./hooks/use-agent-core";
```

​        再删除组件中的状态 hook：

```TypeScript
const agentCore = useAgentCore();
```

​        最后删除页面底部的 `AgentCorePanel`：

```TypeScript
<AgentCorePanel
  demo={agentCore.demo}
  onRun={agentCore.runDemo}
  onTaskChange={agentCore.setTask}
  onToolChange={agentCore.setSelectedToolName}
  running={agentCore.running}
  selectedToolName={agentCore.selectedToolName}
  task={agentCore.task}
  tools={agentCore.tools}
/>
```

​        同时删除这些已经没有页面入口的前端演示文件：

```text
ui/app/components/agent-core-panel.tsx
ui/app/hooks/use-agent-core.ts
ui/app/stores/agent-core-store.ts
ui/app/lib/agent-core-api.ts
```

##### 17.3.7.9.1 为什么现在删除
​        第 12 章的演示面板是学习工具协议时的临时入口。
​        现在项目已经有真实的会话、计划、文件、Shell 和沙箱状态，页面应该逐步收敛成真实 Agent 工作台，而不是每章新增一个演示卡片。
​        后续工具调用结果会进入事件记录和统一工具预览面板，演示区不再保留。

#### 17.3.7.10 页面加载当前沙箱状态
​        打开 `ui/app/page.tsx`，引入 API：

```TypeScript
import { fetchCurrentSandbox, waitCurrentSandbox } from "./lib/sandbox-api";
```

​        新增状态：

```TypeScript
const [sandboxStatus, setSandboxStatus] = useState<
  LoadState<SandboxInstanceData>
>({ type: "loading" });
const [sandboxRefreshing, setSandboxRefreshing] = useState(false);
```

​        在 `loadStatus()` 中同时加载：

```TypeScript
const [apiData, databaseData, sandboxData] = await Promise.all([
  requestApi<ApiStatusData>("/api/status"),
  requestApi<DatabaseStatusData>("/api/status/database"),
  fetchCurrentSandbox(),
]);
```

​        新增刷新函数：

```TypeScript
async function refreshSandbox() {
  setSandboxRefreshing(true);
  try {
    const sandbox = await waitCurrentSandbox();
    setSandboxStatus({ type: "ready", data: sandbox });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    setSandboxStatus({ type: "error", message });
  } finally {
    setSandboxRefreshing(false);
  }
}
```

​        最后把状态传给 `ChatWorkspace`：

```TypeScript
onRefreshSandbox={refreshSandbox}
sandbox={sandboxStatus}
sandboxRefreshing={sandboxRefreshing}
```

##### 17.3.7.10.1 代码讲解
​        页面第一次加载时，会同时检查：

```Plain
API
数据库
Sandbox
```

​        点击沙箱刷新按钮时，会调用 `/api/sandboxes/current/wait`，让主 API 等待 Sandbox 健康。
​        这比前端直接请求 `/sandbox-api/status` 更合理，因为未来主 API 才知道当前会话绑定的是哪个沙箱。

### 17.3.8 关键理解
​        本阶段最重要的是“适配层”。
​        如果所有地方都直接写：

```Plain
http://sandbox:8100/api
```

​        后续改成多沙箱时，会到处改代码。
​        有了 `DockerSandboxManager` 后，上层只依赖：

```Plain
/api/sandboxes/current
```

​        底层实现可以从 Compose 沙箱换成真实 Docker 容器。
​        第二个重点是“当前阶段不停止容器”。
​        `DELETE /api/sandboxes/current` 只释放主 API 对当前沙箱的引用，不停止 `atlas-sandbox`。
​        这是为了保护开发环境。真正删除容器会在后续更完整的 DockerSandbox 生命周期中处理。

### 17.3.9 技术难点与亮点
​        本阶段的技术难点在于把边界补完整。主 API 需要知道当前任务沙箱是否可用，但又不能把 Sandbox 的内部路径和容器细节直接暴露给前端。健康等待也不能简单地检查一次就失败，因为容器刚启动时可能还在加载服务，短时间内不可用并不代表整个环境不可用。
​        文件和 Shell 代理同样不能绕过 Sandbox 原有安全校验。主 API 代理只是统一入口，不是重新实现文件读写或命令执行。真正的路径边界、输出限制和进程管理仍然留在 Sandbox 服务里。前端层面也需要收敛：沙箱状态应该进入工作台右侧，成为当前任务执行环境的一部分，而不是再建一个孤立演示页。
​        本阶段的亮点，是主 API 开始拥有统一的 Sandbox 管理入口。`/api/sandboxes/current` 把状态、健康等待、文件代理和 Shell 代理串在一起，同时为后续一任务一容器保留了稳定接口形状。前端也开始从“展示接口成果”转向“展示任务运行环境”。

### 17.3.10 面试考点
​        面试里问到这一阶段，可以先从“为什么需要 Sandbox 管理器”讲起。直接调用 Sandbox URL 的问题是耦合太强，上层代码会知道太多执行环境细节；一旦后续改成多沙箱或任务级容器，所有直接调用地址的地方都要改。管理器的价值，就是把“当前任务沙箱”抽象成一个稳定入口。
​        当前阶段不直接挂 Docker socket，是因为 Docker socket 权限很高，主 API 一旦拿到它，就具备创建、停止、删除容器的能力。课程这里先用 Compose 管理固定沙箱，是为了把接口形状讲清楚，再逐步进入更复杂的生命周期管理。健康检查和健康等待的区别也很重要：健康检查是一次判断，健康等待是多次重试直到就绪或超时。
​        `release_current()` 不直接停止 Compose 容器，是为了保护共享开发环境。Compose 沙箱还要被后续章节继续使用，主 API 此时只释放引用，不应该主动停止容器。前端通过主 API 查询沙箱状态，也是为了让未来多沙箱场景仍然由主 API 决定当前会话应该看哪一个沙箱。

### 17.3.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 17.3.11.1 编译和类型检查

```Bash
cd api
uv run python -m compileall app
cd ../ui
pnpm typecheck
```

#### 17.3.11.2 检查 Compose 配置

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose config
```

​        预期能看到：

```Plain
DOCKER_SANDBOX_NAME
DOCKER_SANDBOX_WAIT_RETRIES
```

#### 17.3.11.3 启动服务
​        如果本阶段修改了 API 代码，需要先重新构建 API 镜像：

```Bash
docker compose build api
```

​        如果本阶段修改了前端代码，需要重新构建 UI 镜像：

```Bash
docker compose build ui
```

​        构建完成后启动服务：

```Bash
docker compose up -d sandbox api ui nginx
```

​        启动后先确认服务状态：

```Bash
docker compose ps
```

​        预期至少看到：

```Plain
atlas-api      Up ... (healthy)
atlas-nginx    Up ...
atlas-sandbox  Up ... (healthy)
```

​        这里要特别注意：`nginx` 启动成功不代表 `api` 已经完成启动。Nginx 只是网关，它会把请求转发给 API；如果 API 刚重建完还在启动，马上访问网关可能会看到 `502 Bad Gateway`。
​        如果刚重建过 `api` 或 `sandbox`，建议等 `docker compose ps` 里 `atlas-api` 和 `atlas-sandbox` 都变成 `healthy` 后，再重启一次 Nginx：

```Bash
docker compose restart nginx
```

​        这一步不重新构建镜像，只是让 Nginx 在上游服务稳定后重新建立连接。
​        如果页面还是旧样子，例如没有看到“任务沙箱”面板，说明 `ui` 容器没有重新创建到最新镜像。执行：

```Bash
docker compose up -d --force-recreate ui nginx
```

​        重新访问：

```Plain
http://localhost:8088
```

​        此时页面右侧应该能看到“任务沙箱”面板，并且不再看到第 12 章的 Agent 核心演示面板。

#### 17.3.11.4 验证当前沙箱状态

```Bash
curl http://localhost:8088/api/sandboxes/current
```

​        预期返回：

```Plain
status: ready
name: atlas-sandbox
```

​        等待沙箱健康：

```Bash
curl -X POST http://localhost:8088/api/sandboxes/current/wait \
  -H "Content-Type: application/json" \
  -d '{"retries":3,"interval_seconds":1}'
```

#### 17.3.11.5 验证文件代理

```Bash
curl -X POST http://localhost:8088/api/sandboxes/current/files/write \
  -H "Content-Type: application/json" \
  -d '{"path":"notes/from-manager.txt","content":"hello manager"}'
```

​        读取：

```Bash
curl "http://localhost:8088/api/sandboxes/current/files/read?path=notes/from-manager.txt"
```

​        预期能看到：

```Plain
hello manager
```

#### 17.3.11.6 验证 Shell 代理

```Bash
curl -X POST http://localhost:8088/api/sandboxes/current/shell/run \
  -H "Content-Type: application/json" \
  -d '{"command":"pwd && ls -la"}'
```

​        预期返回：

```Plain
status: succeeded
return_code: 0
```

#### 17.3.11.7 验证前端
​        访问：

```Plain
http://localhost:8088
```

​        右侧工作台应该出现“任务沙箱”面板。
​        点击刷新按钮后，面板应该显示：

```Plain
沙箱可用
default
atlas-sandbox
ready
```

### 17.3.12 阶段小结
​        本阶段完成了 DockerSandbox 适配的第一版。主 API 新增了 Sandbox 响应模型和 `DockerSandboxManager`，把当前沙箱的获取、确保、健康等待和释放统一到一个管理入口里。文件读取、文件写入和 Shell 运行也开始通过 `/api/sandboxes/current` 代理出去。
​        前端新增了“任务沙箱”状态面板，并把它放进工作台右侧，而不是继续新增演示区域。从这一阶段开始，文件、Shell 和后续浏览器能力都有了统一的“当前沙箱”入口。虽然底层仍然是 Docker Compose 管理的固定容器，但上层调用形状已经为后续任务级沙箱容器预留好了位置。

## 17.4 本章小结

​        完成“Sandbox Shell 与 ShellTool 成形”和“DockerSandbox 契合”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第十六章. Sandbox 服务与文件工具](16-Sandbox%20服务与文件工具.md) · [返回目录](../README.md) · [第十八章. Playwright、CDP 与 BrowserTool →](18-Playwright、CDP%20与%20BrowserTool.md)
