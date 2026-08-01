# 第二十五章. DockerSandbox 契合

## 25.1 本章目标
​        学完本章后，你将能够：
​        第 23 章和第 24 章分别把文件与 Shell 能力接到了 Sandbox，但主 API 仍然是直接拿一个固定的 Sandbox 地址去调用。这个方式能跑通教学代码，却还没有形成真正的“沙箱管理”抽象。只要后续出现多任务、多容器或任务级隔离，散落在各处的 Sandbox URL 就会变成维护负担。
​        学完本章后，你应该能理解为什么主 API 需要一个 Sandbox 管理器，而不是让工具和路由到处直接拼 Sandbox 地址。本章会设计当前任务沙箱的创建、获取、健康等待和释放接口，在主 API 中封装 `DockerSandboxManager`，再通过它代理文件读取、文件写入和 Shell 命令执行。前端工作台右侧会出现“任务沙箱”状态面板，让用户在执行任务时能看到当前执行环境是否可用。

## 25.2 最终效果
​        本章结束后，主 API 会新增一组 Sandbox 管理接口：

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

​        本章完成后的调用链路是：

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

## 25.3 本章要解决的问题
​        第 23 章和第 24 章已经分别实现了 FileTool 和 ShellTool。
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

​        所以本章加入 `DockerSandboxManager`，先把“当前沙箱实例”的管理入口固定下来。

## 25.4 本章技术方案
​        本章不直接把 Docker socket 挂给主 API。
​        原因是 Docker socket 权限很高，如果过早暴露，会把课程复杂度和安全风险一下拉高。
​        本章采用过渡方案：
​        Docker Compose 仍然负责启动 `atlas-sandbox` 容器，主 API 不直接操作 Docker Engine。主 API 新增 `DockerSandboxManager`，由它代表“当前任务沙箱”这个概念，并通过健康检查判断 Sandbox 服务是否可用。文件和 Shell 的代理调用也统一经过这个管理器，前端则只通过主 API 查看当前任务沙箱状态。
​        这个设计先固定调用形状：

```Plain
create / get / wait / release / file proxy / shell proxy
```

​        等第 25 章之后需要一任务一容器时，可以把 `DockerSandboxManager` 的实现方式换成真实 Docker Engine 操作，路由和前端不用大改。
​        本章暂时不做这些内容：
​        本章不会把 `/var/run/docker.sock` 挂给主 API，也不会动态创建多个 Docker 容器。沙箱资源限制、任务和沙箱实例的一对一绑定、沙箱运行日志审计，都属于更靠后的生产化和安全加固内容。这里先把接口形状和适配层做稳定，避免过早把 Docker 权限和生命周期管理复杂度引入主 API。

## 25.5 本章删除和合并的临时 UI
​        本章不新增独立“DockerSandbox 演示页”。
​        沙箱状态是工作台的一部分，所以本章把它放进 `ChatWorkspace` 右侧：

```Plain
任务沙箱
计划面板
文件面板
上下文面板
事件记录
```

​        这样用户在执行任务时能看到当前沙箱是否可用，而不是在另一个孤立区域手动调接口。
​        同时，本章删除第 17 章留下的 Agent 核心演示前端入口。
​        第 17 章的演示面板只用于解释 Memory、工具协议和工具调用结果，不应该一直停留在真实工作台首页。后续工具调用结果会进入统一的事件时间线和工具预览面板，而不是保留一个独立演示区域。

## 25.6 新增、修改和删除的文件

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

​        其中最后四个 `agent-core` 前端文件会在本章删除。后端的 Agent Core 接口和领域代码保留，因为后续 Agent 执行链路仍然会复用工具协议能力；删除的是页面上的临时演示 UI。

## 25.7 实施步骤
### 25.7.1 补充主 API 沙箱配置
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

#### 25.7.1.1 字段含义
​        `docker_sandbox_id` 是主 API 识别当前沙箱实例的稳定 ID。本章只有一个 Compose 沙箱，所以它可以固定为 `default`；以后如果变成一任务一沙箱，这个 ID 就可以替换成任务 ID、会话 ID 或容器 ID。
​        `docker_sandbox_name` 对应当前 Docker Compose 沙箱容器名，也就是 `atlas-sandbox`。`docker_sandbox_wait_retries` 和 `docker_sandbox_wait_interval_seconds` 共同控制健康等待逻辑：主 API 可以按固定次数和间隔轮询 Sandbox 状态，而不是只检查一次就判断失败。

#### 25.7.1.2 代码讲解
​        本章只有一个 Compose 沙箱，所以 ID 固定为 `default`。
​        后续如果变成“一任务一沙箱”，这个 ID 可以替换成任务 ID、会话 ID 或容器 ID。

### 25.7.2 定义主 API 沙箱响应模型
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

#### 25.7.2.1 这段代码在流程中的位置
​        这些模型属于主 API，不属于 Sandbox 服务。
​        它们描述的是主 API 对前端暴露的沙箱管理协议。

#### 25.7.2.2 为什么这样设计
​        主 API 不应该直接把 Sandbox 服务的所有字段原样透出。
​        本章先让主 API 控制对外协议。后续 DockerSandbox 变成多实例后，前端仍然可以继续使用：

```Plain
/api/sandboxes/current
```

​        而不用知道具体容器地址如何变化。

### 25.7.3 实现 DockerSandboxManager
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

#### 25.7.3.1 这段代码在流程中的位置
​        `DockerSandboxManager` 是主 API 对沙箱的统一入口。
​        工具、路由、前端都不需要直接拼 Sandbox 地址。它们通过 manager 获取状态或代理调用。

#### 25.7.3.2 调用链路
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

#### 25.7.3.3 为什么这样设计
​        现在的 `release_current()` 不会停止 Docker 容器。
​        这是刻意设计。当前容器由 Docker Compose 管理，如果主 API 随便停止它，课程环境会变得难排查。
​        本章先把“释放沙箱”这个接口形状做出来，后续真正一任务一容器时，再把实现方式替换成 Docker Engine 删除容器。

### 25.7.4 新增 Sandbox 管理路由
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

#### 25.7.4.1 代码讲解
​        这组路由有两类：
​        管理类接口围绕当前沙箱实例展开，包括读取当前状态、确保实例存在、等待健康检查通过，以及释放当前引用。代理类接口则把文件读取、文件写入和 Shell 运行统一放到 `/api/sandboxes/current` 下面。
​        代理类接口不是为了替代第 23、24 章的工具，而是为了给前端和后续任务系统一个统一入口。
​        第 29 章工具预览面板会更依赖这种统一入口。

### 25.7.5 注册 Sandbox 路由
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

### 25.7.6 新增前端 Sandbox API
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

#### 25.7.6.1 代码讲解
​        前端只访问主 API：

```Plain
/api/sandboxes/current
```

​        不直接访问：

```Plain
/sandbox-api/status
```

​        这样前端不会绑定 Sandbox 服务路径。后续多沙箱时，主 API 可以继续隐藏具体容器地址。

### 25.7.7 新增任务沙箱状态面板
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

#### 25.7.7.1 代码讲解
​        这个组件不直接请求接口。
​        它只接收 `state`、`refreshing` 和 `onRefresh`。请求逻辑放在页面层。
​        这样 `SandboxStatusPanel` 只是展示组件，后续如果要把沙箱状态接到 zustand store，也不用改它的 UI 结构。

### 25.7.8 把沙箱状态放进工作台
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

#### 25.7.8.1 为什么放在这里
​        沙箱状态和当前会话任务强相关。
​        如果放到首页顶部，它会像系统状态；如果放到右侧工作台，它更像“当前任务执行环境”。
​        本章选择放在 `ChatWorkspace` 右侧，为后续 Shell、Browser、VNC 面板继续收敛做准备。

### 25.7.9 删除旧演示面板
​        打开 `ui/app/page.tsx`，删除第 17 章临时演示面板相关代码。
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

#### 25.7.9.1 为什么现在删除
​        第 17 章的演示面板是学习工具协议时的临时入口。
​        现在项目已经有真实的会话、计划、文件、Shell 和沙箱状态，页面应该逐步收敛成真实 Agent 工作台，而不是每章新增一个演示卡片。
​        后续工具调用结果会进入事件记录和统一工具预览面板，演示区不再保留。

### 25.7.10 页面加载当前沙箱状态
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

#### 25.7.10.1 代码讲解
​        页面第一次加载时，会同时检查：

```Plain
API
数据库
Sandbox
```

​        点击沙箱刷新按钮时，会调用 `/api/sandboxes/current/wait`，让主 API 等待 Sandbox 健康。
​        这比前端直接请求 `/sandbox-api/status` 更合理，因为未来主 API 才知道当前会话绑定的是哪个沙箱。

## 25.8 关键理解
​        本章最重要的是“适配层”。
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

## 25.9 技术难点与亮点
​        本章的技术难点在于把边界补完整。主 API 需要知道当前任务沙箱是否可用，但又不能把 Sandbox 的内部路径和容器细节直接暴露给前端。健康等待也不能简单地检查一次就失败，因为容器刚启动时可能还在加载服务，短时间内不可用并不代表整个环境不可用。
​        文件和 Shell 代理同样不能绕过 Sandbox 原有安全校验。主 API 代理只是统一入口，不是重新实现文件读写或命令执行。真正的路径边界、输出限制和进程管理仍然留在 Sandbox 服务里。前端层面也需要收敛：沙箱状态应该进入工作台右侧，成为当前任务执行环境的一部分，而不是再建一个孤立演示页。
​        本章的亮点，是主 API 开始拥有统一的 Sandbox 管理入口。`/api/sandboxes/current` 把状态、健康等待、文件代理和 Shell 代理串在一起，同时为后续一任务一容器保留了稳定接口形状。前端也开始从“展示接口成果”转向“展示任务运行环境”。

## 25.10 面试考点
​        面试里问到这一章，可以先从“为什么需要 Sandbox 管理器”讲起。直接调用 Sandbox URL 的问题是耦合太强，上层代码会知道太多执行环境细节；一旦后续改成多沙箱或任务级容器，所有直接调用地址的地方都要改。管理器的价值，就是把“当前任务沙箱”抽象成一个稳定入口。
​        当前阶段不直接挂 Docker socket，是因为 Docker socket 权限很高，主 API 一旦拿到它，就具备创建、停止、删除容器的能力。课程这里先用 Compose 管理固定沙箱，是为了把接口形状讲清楚，再逐步进入更复杂的生命周期管理。健康检查和健康等待的区别也很重要：健康检查是一次判断，健康等待是多次重试直到就绪或超时。
​        `release_current()` 不直接停止 Compose 容器，是为了保护共享开发环境。Compose 沙箱还要被后续章节继续使用，主 API 此时只释放引用，不应该主动停止容器。前端通过主 API 查询沙箱状态，也是为了让未来多沙箱场景仍然由主 API 决定当前会话应该看哪一个沙箱。

## 25.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 25.11.1 编译和类型检查

```Bash
cd api
uv run python -m compileall app
cd ../ui
pnpm typecheck
```

### 25.11.2 检查 Compose 配置

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose config
```

​        预期能看到：

```Plain
DOCKER_SANDBOX_NAME
DOCKER_SANDBOX_WAIT_RETRIES
```

### 25.11.3 启动服务
​        如果本章修改了 API 代码，需要先重新构建 API 镜像：

```Bash
docker compose build api
```

​        如果本章修改了前端代码，需要重新构建 UI 镜像：

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

​        此时页面右侧应该能看到“任务沙箱”面板，并且不再看到第 17 章的 Agent 核心演示面板。

### 25.11.4 验证当前沙箱状态

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

### 25.11.5 验证文件代理

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

### 25.11.6 验证 Shell 代理

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

### 25.11.7 验证前端
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

## 25.12 常见问题

### 25.12.1 `/api/sandboxes/current` 返回 `unavailable` 怎么办？
​        `unavailable` 表示主 API 没有通过 Sandbox 健康检查。先执行 `docker compose ps`，确认 `atlas-sandbox` 是否处于 running 或 healthy 状态，再请求 `curl http://localhost:8088/sandbox-api/status`，判断 Nginx 到 Sandbox 的路径是否正常。
​        如果 `/sandbox-api/status` 也失败，问题大概率在 Sandbox 容器、Nginx 转发或容器网络。如果 `/sandbox-api/status` 正常，而 `/api/sandboxes/current` 失败，就继续检查主 API 访问 Sandbox 的内部地址。

### 25.12.2 `/sandbox-api/status` 正常，但 `/api/sandboxes/current` 不正常怎么办？
​        这通常说明浏览器到 Nginx 再到 Sandbox 的路径没问题，但 API 容器到 Sandbox 的内部路径有问题。重点检查 API 容器里的 `SANDBOX_API_BASE_URL` 是否为 `http://sandbox:8100/api`。
​        容器内不能用 `localhost:8100` 访问另一个容器。`localhost` 指向的是 API 容器自己，而 Compose 服务名 `sandbox` 才能解析到 Sandbox 容器。

### 25.12.3 `/api/sandboxes/current` 返回 `502 Bad Gateway` 怎么办？
​        `502` 是 Nginx 返回的，表示网关转发到 API 时失败。先执行 `docker compose ps`，确认 `atlas-api` 是否已经 healthy。如果 API 刚重建或刚重启，Nginx 可能在 API 还没完全启动时就转发了请求。
​        等 API healthy 后执行 `docker compose restart nginx`，再重新请求。也可以查看 `docker compose logs --tail=80 nginx`，如果看到 `connect() failed (111: Connection refused) while connecting to upstream`，通常就是请求发生在 API 尚未监听完成的瞬间。

### 25.12.4 页面没有出现“任务沙箱”面板怎么办？
​        先确认当前打开的是 `http://localhost:8088`。如果接口 `curl http://localhost:8088/api/sandboxes/current` 正常，但页面还是旧样子，说明 UI 容器没有使用最新构建产物。
​        处理方式是执行 `docker compose build ui`，然后执行 `docker compose up -d --force-recreate ui nginx`。重新访问页面后，右侧工作台应该出现“任务沙箱”面板，并且不再显示第 17 章遗留的 Agent 核心演示面板。

### 25.12.5 为什么删除当前沙箱不会停止容器？
​        当前沙箱容器由 Docker Compose 管理，它是课程环境里的共享服务。主 API 的 `release_current()` 只释放“当前沙箱引用”，不停止 `atlas-sandbox`，这样不会影响后续章节继续验证文件、Shell 和浏览器能力。
​        等后续进入一任务一容器模式时，释放沙箱才会真正对应 Docker 容器生命周期操作。现阶段先保留接口形状，不提前破坏开发环境。

### 25.12.6 为什么前端不直接请求 `/sandbox-api/status`？
​        前端应该只依赖主 API，而不是直接绑定 Sandbox 服务路径。未来不同会话可能绑定不同沙箱，只有主 API 知道当前会话应该访问哪一个实例。
​        让前端访问 `/api/sandboxes/current`，可以把沙箱选择、健康等待和实例状态都收敛在主 API 里。前端只关心当前任务环境是否可用，不关心底层容器地址。

## 25.13 本章小结
​        本章完成了 DockerSandbox 适配的第一版。主 API 新增了 Sandbox 响应模型和 `DockerSandboxManager`，把当前沙箱的获取、确保、健康等待和释放统一到一个管理入口里。文件读取、文件写入和 Shell 运行也开始通过 `/api/sandboxes/current` 代理出去。
​        前端新增了“任务沙箱”状态面板，并把它放进工作台右侧，而不是继续新增演示区域。从这一章开始，文件、Shell 和后续浏览器能力都有了统一的“当前沙箱”入口。虽然底层仍然是 Docker Compose 管理的固定容器，但上层调用形状已经为后续任务级沙箱容器预留好了位置。

## 25.14 下一章预告
​        第 26 章会进入 Playwright 与 CDP 基础，讲清楚浏览器自动化如何连接沙箱里的浏览器，为 BrowserTool 做准备。
