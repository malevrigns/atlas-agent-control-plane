# 第二十八章. VNC 远程桌面临场

## 28.1 本章目标
​        学完本章后，你将能够：
​        第 27 章已经让浏览器截图进入事件记录，但截图只能告诉我们某一刻页面长什么样。真正做浏览器类 Agent 时，用户还会关心页面是否正在加载、点击之后有没有变化、输入框是否填上了内容。截图像一张证据照片，VNC 则更像一扇实时观察窗口。
​        学完本章后，你应该能理解为什么浏览器自动化还需要 VNC 远程桌面，也能讲清 `Xvfb`、`x11vnc`、`websockify` 和 `noVNC` 的分工。本章会在 Sandbox 容器中启动虚拟显示器、VNC 服务和 websockify，通过 Nginx 暴露 `/sandbox-vnc/`，再在前端工作台右侧嵌入浏览器远程桌面。到这里，浏览器能力就不再只是截图结果，而是具备可持续观察的界面。

## 28.2 最终效果
​        本章结束后，访问：

```Plain
http://localhost:8088
```

​        右侧工作台会新增：

```Plain
浏览器远程桌面
```

​        面板会使用前端 `@novnc/novnc` SDK 连接 Sandbox 的 websockify 服务。执行 BrowserTool 打开网页后，可以在这个区域看到 Sandbox 中浏览器的实时画面。
​        本章完成后的链路是：

```Plain
Chromium 有头浏览器
  |
  v
Xvfb 虚拟显示器
  |
  v
x11vnc
  |
  v
websockify + noVNC
  |
  v
Nginx /sandbox-vnc/
  |
  v
前端 VncPanel noVNC SDK
```

## 28.3 本章要解决的问题
​        第 26 章已经能让 Sandbox 启动 Chromium 并截图。
​        第 27 章已经能让 Agent 调用 `browser_open` 和 `browser_screenshot`，并在事件记录里展示截图。
​        但是截图是离散结果，它只能回答：

```Plain
某一刻页面长什么样？
```

​        真实 Agent 执行浏览器任务时，还需要观察：

```Plain
浏览器是否真的打开了？
页面是否正在加载？
点击后页面有没有变化？
输入框里是否已经填入内容？
```

​        所以本章加入 VNC 远程桌面，让用户可以在工作台中看到 Sandbox 里的浏览器实时画面。

## 28.4 本章技术方案
​        容器里没有真实显示器。要让有头浏览器可视化，需要补一条显示链路：

```Plain
Xvfb      创建虚拟显示器
x11vnc    把虚拟显示器画面暴露成 VNC
websockify 把 VNC TCP 协议转换成 WebSocket
@novnc/novnc SDK 在前端工作台里显示远程桌面
```

​        本章选择让 Sandbox 只提供 websockify WebSocket，再让前端通过 `@novnc/novnc` SDK 渲染远程桌面：

```Plain
/sandbox-vnc/websockify -> sandbox:6080
```

​        这样设计的原因是：
​        Docker 镜像不需要安装 Debian 的 `novnc` 包，构建会轻一些，也能减少系统依赖带来的网络失败概率。前端工作台直接使用 `@novnc/novnc` SDK 后，可以自己控制连接状态、错误提示和展示尺寸。后续做统一工具预览面板时，也可以继续复用同一个 noVNC 组件。
​        本章暂时不做这些内容：
​        本章不做 VNC 密码、多会话多桌面、录屏、完整 noVNC 工具栏，也不做生产环境 HTTPS 和鉴权。这里仍然是课程里的本地开发闭环，重点是把画面从 Sandbox 容器送到前端工作台。安全和多租户能力会在后续生产化阶段再补。

## 28.5 新增和修改的文件

```Plain
.env.example
README.md
docker-compose.yml
nginx/README.md
nginx/default.conf
sandbox/README.md
sandbox/Dockerfile
sandbox/scripts/start.sh
sandbox/app/core/config.py
sandbox/app/schemas/vnc.py
sandbox/app/services/vnc_service.py
sandbox/app/api/routes/vnc.py
sandbox/app/api/router.py
ui/app/types.ts
ui/app/lib/sandbox-api.ts
ui/app/components/vnc-panel.tsx
ui/app/components/chat-workspace.tsx
ui/app/page.tsx
docs/course/chapters/28-vnc-integration.md
```

## 28.6 实施步骤
### 28.6.1 补充 VNC 配置项
​        打开 `sandbox/app/core/config.py`，在浏览器配置后加入：

```Python
    # ----- VNC / noVNC：把沙箱中的浏览器画面暴露成可嵌入的远程桌面 -----
    vnc_enabled: bool = True
    vnc_display: str = ":99"
    vnc_port: int = 5900
    vnc_web_port: int = 6080
    vnc_iframe_path: str = (
        "/sandbox-vnc/vnc.html?autoconnect=1&resize=scale&path=sandbox-vnc/websockify"
    )
```

#### 28.6.1.1 字段含义
​        `vnc_enabled` 控制是否启用远程桌面能力。`vnc_display` 是 Xvfb 创建的虚拟显示器编号，Playwright 以有头模式启动 Chromium 时，浏览器窗口就会画到这个显示器里。
​        `vnc_port` 是 x11vnc 在容器内监听的原生 VNC 端口，`vnc_web_port` 是 websockify 对外提供 WebSocket 的端口。`vnc_iframe_path` 是兼容字段，本章前端主要使用 `websocket_path` 连接 websockify。也就是说，配置层不是为了让前端硬编码端口，而是为了让 Sandbox 告诉前端应该连哪条观察通道。

#### 28.6.1.2 为什么这样设计
​        VNC 不只是前端页面，它依赖 Sandbox 容器里的多个进程。
​        这些配置让前端不需要硬编码端口和路径。后续如果多沙箱使用不同 noVNC 地址，只需要让状态接口返回不同的 `websocket_path`。

### 28.6.2 新增 VNC 状态接口
​        创建 `sandbox/app/schemas/vnc.py`：

```Python
from pydantic import BaseModel


class VncStatusResponse(BaseModel):
    enabled: bool  # 是否启用 VNC/noVNC 远程桌面。
    display: str  # Xvfb 虚拟显示器编号，例如 :99。
    vnc_port: int  # x11vnc 在容器内监听的原生 VNC 端口。
    web_port: int  # websockify/noVNC 在容器内监听的 Web 端口。
    iframe_path: str  # 兼容字段，保留给直接打开 noVNC 页面这类方案。
    websocket_path: str  # 前端 noVNC SDK 连接 websockify 时使用的 WebSocket 路径。
    message: str  # 给前端展示的状态说明。
```

​        创建 `sandbox/app/services/vnc_service.py`：

```Python
from app.core.config import Settings, settings
from app.schemas.vnc import VncStatusResponse


class VncService:
    """读取 Sandbox 的 VNC/noVNC 访问配置。

    第 28 章先把 VNC 作为沙箱内置能力暴露出来：
    Xvfb 提供虚拟显示器，x11vnc 读取显示器画面，websockify/noVNC 把画面转成浏览器可访问的 Web 页面。
    """

    def __init__(self, app_settings: Settings = settings) -> None:
        # 1. 保存配置对象。后续如果支持多沙箱，每个沙箱可以拥有不同的 VNC 地址。
        self.settings = app_settings

    def status(self) -> VncStatusResponse:
        """返回前端渲染 VNC 面板所需的最小信息。"""

        # 2. 这里不直接探测进程。进程是否真正启动，由 Docker 启动脚本和 Nginx 访问验证确认。
        #    这样状态接口不会因为临时进程抖动而阻塞工作台页面。
        websocket_path = "sandbox-vnc/websockify"
        return VncStatusResponse(
            enabled=self.settings.vnc_enabled,
            display=self.settings.vnc_display,
            vnc_port=self.settings.vnc_port,
            web_port=self.settings.vnc_web_port,
            iframe_path=self.settings.vnc_iframe_path,
            websocket_path=websocket_path,
            message=(
                "noVNC remote desktop is configured."
                if self.settings.vnc_enabled
                else "VNC remote desktop is disabled."
            ),
        )
```

​        创建 `sandbox/app/api/routes/vnc.py`：

```Python
from fastapi import APIRouter, Depends

from app.schemas.common import ApiResponse
from app.schemas.vnc import VncStatusResponse
from app.services.vnc_service import VncService

router = APIRouter(prefix="/vnc", tags=["vnc"])


def build_vnc_service() -> VncService:
    # 第 28 章先直接创建 service；后续多沙箱时可以在这里按会话 ID 选择不同实例。
    return VncService()


@router.get("/status", response_model=ApiResponse[VncStatusResponse])
async def get_vnc_status(
    service: VncService = Depends(build_vnc_service),
) -> ApiResponse[VncStatusResponse]:
    # 前端工作台通过这个接口拿 websockify 路径，不需要硬编码 VNC 细节。
    return ApiResponse(data=service.status())
```

​        打开 `sandbox/app/api/router.py` 注册路由：

```Python
from app.api.routes import browser, files, shell, status, supervisor, vnc

api_router.include_router(vnc.router)
```

#### 28.6.2.1 这段代码在流程中的位置
​        VNC 状态接口不是用来控制浏览器的。
​        它只负责告诉前端：

```Plain
websockify 路径是什么
前端应该连接哪个 WebSocket
当前是否启用 VNC
```

​        真正的浏览器打开网页仍然由第 27 章的 BrowserTool 完成。VNC 只是让用户观察这个浏览器。

### 28.6.3 编写 Sandbox 启动脚本
​        创建 `sandbox/scripts/start.sh`：

```Bash
#!/usr/bin/env bash
set -eu

# ===================== 第1步：准备 VNC 相关默认配置 =====================
# DISPLAY 指向 Xvfb 创建的虚拟显示器。Playwright 使用 headless=false 时会把 Chromium 画面画到这里。
export DISPLAY="${DISPLAY:-${VNC_DISPLAY:-:99}}"
VNC_PORT="${VNC_PORT:-5900}"
VNC_WEB_PORT="${VNC_WEB_PORT:-6080}"

# ===================== 第2步：启动虚拟桌面和 noVNC 链路 =====================
if [[ "${VNC_ENABLED:-true}" == "true" ]]; then
  # Xvfb 提供一个没有真实显示器的 X11 桌面，浏览器窗口会运行在这个桌面里。
  Xvfb "${DISPLAY}" -screen 0 "${BROWSER_VIEWPORT_WIDTH:-1280}x${BROWSER_VIEWPORT_HEIGHT:-720}x24" &
  sleep 1

  # fluxbox 提供最轻量的窗口管理能力，让有头 Chromium 能正常创建窗口。
  fluxbox >/tmp/fluxbox.log 2>&1 &

  # x11vnc 把 Xvfb 桌面暴露成 VNC 端口。这里不设置密码，只用于本地课程环境。
  x11vnc -display "${DISPLAY}" -rfbport "${VNC_PORT}" -forever -shared -nopw >/tmp/x11vnc.log 2>&1 &

  # websockify 把 VNC TCP 连接转换成浏览器可用的 WebSocket。
  # 这里使用 apt 安装到系统里的 websockify 命令，不走 Python 依赖，避免额外拉取 numpy。
  websockify "${VNC_WEB_PORT}" "127.0.0.1:${VNC_PORT}" >/tmp/websockify.log 2>&1 &
fi

# ===================== 第3步：启动 Sandbox FastAPI 服务 =====================
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8100
```

#### 28.6.3.1 这段代码的业务流程
​        Sandbox 容器启动后，会按顺序启动：

```Plain
Xvfb -> fluxbox -> x11vnc -> websockify/noVNC -> FastAPI
```

​        `FastAPI` 仍然监听 `8100`，文件、Shell、浏览器 API 不变。
​        新增的是 `6080` 端口，websockify 会在这里提供 WebSocket 连接。

#### 28.6.3.2 常见误区
​        `x11vnc` 不是浏览器。
​        `x11vnc` 只是把虚拟显示器画面转成 VNC 协议。真正访问网页的仍然是 Playwright 启动的 Chromium。
​        `websockify` 也不是浏览器。
​        它只是把 VNC 协议转成浏览器能连接的 WebSocket。

### 28.6.4 更新 Sandbox Dockerfile
​        打开 `sandbox/Dockerfile`，先把基础镜像固定到 bookworm：

```Dockerfile
FROM python:3.12-slim-bookworm
```

​        再配置 apt 镜像源并安装 VNC 相关系统包：

```Dockerfile
ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ENV APT_OPTS="-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 -o Acquire::ForceIPv4=true"

RUN sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g; s|http://deb.debian.org/debian|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get ${APT_OPTS} update \
    && apt-get ${APT_OPTS} install -y --no-install-recommends \
        bash \
        fluxbox \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*
```

​        加入启动脚本并暴露端口：

```Dockerfile
COPY scripts ./scripts
RUN chmod +x ./scripts/start.sh

EXPOSE 8100
EXPOSE 5900
EXPOSE 6080

CMD ["./scripts/start.sh"]
```

#### 28.6.4.1 为什么 Dockerfile 要这样改
​        第 26 章只需要 headless Chromium，所以容器只要能运行 Playwright。
​        第 28 章需要安装一组系统级桌面组件。这里把镜像固定为 `python:3.12-slim-bookworm`，是为了避免 `python:3.12-slim` 随 Debian 版本变化而带来不同的包解析结果。
​        默认 apt 源在国内网络下可能比较慢，所以这里通过 `APT_MIRROR` 和 `APT_SECURITY_MIRROR` 默认切到阿里云 Debian 源。`APT_OPTS` 中的重试、超时和 `Acquire::ForceIPv4=true` 用来提升网络不稳定时的成功率。安装 VNC 相关包时下载内容较多，网络慢时这一步会明显耗时。
​        第 28 章需要看到浏览器窗口，所以要补齐：
​        `xvfb` 提供虚拟显示器，让容器里即使没有真实屏幕也能运行有头浏览器。`fluxbox` 提供轻量窗口管理能力，让 Chromium 能正常创建窗口。`x11vnc` 读取这个虚拟显示器画面，并把它暴露成 VNC 服务。
​        `websockify` 通过 apt 安装成系统命令，不加入 `sandbox/pyproject.toml`。这样 `uv sync` 不会因为 Python 包版 `websockify` 额外下载 `numpy`。noVNC 不放进容器，而是作为前端依赖运行在工作台中。

### 28.6.5 更新 Compose 和 Nginx
​        打开 `docker-compose.yml`，把 Sandbox 浏览器改成有头模式，并加入 VNC 配置：

```YAML
      BROWSER_HEADLESS: ${SANDBOX_BROWSER_HEADLESS:-false}
      VNC_ENABLED: ${SANDBOX_VNC_ENABLED:-true}
      VNC_DISPLAY: ${SANDBOX_VNC_DISPLAY:-:99}
      VNC_PORT: ${SANDBOX_VNC_PORT:-5900}
      VNC_WEB_PORT: ${SANDBOX_VNC_WEB_PORT:-6080}
      VNC_IFRAME_PATH: ${SANDBOX_VNC_IFRAME_PATH:-/sandbox-vnc/vnc.html?autoconnect=1&resize=scale&path=sandbox-vnc/websockify}
      DISPLAY: ${SANDBOX_VNC_DISPLAY:-:99}
```

​        同时让 Sandbox 在 Docker 网络内开放：

```YAML
    expose:
      - "8100"
      - "5900"
      - "6080"
```

​        打开 `nginx/default.conf`，新增：

```Nginx
    location /sandbox-vnc/ {
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_pass http://sandbox:6080/;
    }
```

#### 28.6.5.1 为什么 Nginx 要加 WebSocket 头
​        远程桌面画面通过 WebSocket 传输。
​        如果没有：

```Nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

​        前端 noVNC SDK 可能无法连接远程桌面。

### 28.6.6 安装前端 noVNC SDK
​        进入 `ui` 目录：

```Bash
cd ui
pnpm add @novnc/novnc
```

​        这个依赖让前端可以直接连接 websockify，并把 VNC 画面渲染到一个普通 `div` 中。
​        继续创建类型声明文件 `ui/app/types/novnc.d.ts`：

```TypeScript
declare module "@novnc/novnc/lib/rfb" {
  export default class RFB extends EventTarget {
    scaleViewport: boolean;
    resizeSession: boolean;
    viewOnly: boolean;

    constructor(target: HTMLElement, url: string);
    disconnect(): void;
  }
}
```

#### 28.6.6.1 为什么要加类型声明
​        `@novnc/novnc` 的运行时代码可以直接使用，但深路径 `@novnc/novnc/lib/rfb` 在 TypeScript 下可能缺少完整类型声明。
​        这里补一个最小声明，只描述本章用到的构造函数、三个配置字段和 `disconnect()` 方法。

### 28.6.7 前端新增 VNC 状态类型和 API
​        打开 `ui/app/types.ts`，新增：

```TypeScript
export type VncStatusData = {
  enabled: boolean; // 是否启用 VNC/noVNC 远程桌面。
  display: string; // Xvfb 虚拟显示器编号，例如 :99。
  vnc_port: number; // 容器内 x11vnc 端口，主要用于排查。
  web_port: number; // 容器内 noVNC/websockify 端口，Nginx 会代理它。
  iframe_path: string; // 兼容字段，本章前端主要使用 websocket_path。
  websocket_path: string; // 前端 noVNC SDK 连接 websockify 使用的 WebSocket 路径。
  message: string; // 状态说明，显示在 VNC 面板中。
};
```

​        打开 `ui/app/lib/sandbox-api.ts`，新增：

```TypeScript
export function fetchVncStatus(): Promise<VncStatusData> {
  return requestApi<VncStatusData>("/sandbox-api/vnc/status");
}
```

#### 28.6.7.1 为什么前端直接请求 `/sandbox-api/vnc/status`
​        这个接口是 Sandbox 自己的状态接口。
​        浏览器访问的是 Nginx 网关路径，不会暴露 Docker 网络里的服务地址。
​        后续如果要让主 API 统一代理所有 Sandbox 状态，也可以把这个请求切到 `/api/sandboxes/current/vnc`，前端组件不需要大改。

### 28.6.8 新增 VNC 面板组件
​        创建 `ui/app/components/vnc-panel.tsx`。
​        这个文件在本章使用完整代码：

```TypeScript
"use client";

import RFB from "@novnc/novnc/lib/rfb";
import { Monitor, RefreshCcw, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { LoadState, VncStatusData } from "../types";

type VncPanelProps = {
  onRefresh: () => void; // 重新读取 /sandbox-api/vnc/status。
  state: LoadState<VncStatusData>; // 来自 Sandbox API，包含 websockify 连接路径。
};


// ===================== 第1步：展示 Sandbox 浏览器远程桌面 =====================
export function VncPanel({ onRefresh, state }: VncPanelProps) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">
            浏览器远程桌面
          </h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">
            查看 Sandbox 中有头浏览器的实时画面
          </p>
        </div>
        <button
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          onClick={onRefresh}
          title="刷新 VNC 状态"
          type="button"
        >
          <RefreshCcw size={16} />
        </button>
      </div>

      {state.type === "loading" ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          正在读取远程桌面状态...
        </div>
      ) : null}

      {state.type === "error" ? (
        <div className="mt-4 flex gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          <XCircle className="mt-0.5 shrink-0" size={16} />
          <span>{state.message}</span>
        </div>
      ) : null}

      {state.type === "ready" ? <VncReadyView data={state.data} /> : null}
    </div>
  );
}


function VncReadyView({ data }: { data: VncStatusData }) {
  if (!data.enabled) {
    return (
      <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
        VNC 未启用：{data.message}
      </div>
    );
  }

  return (
    <div className="mt-4 grid gap-3">
      <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
        <Monitor size={16} />
        <span>{data.message}</span>
      </div>
      <div className="overflow-hidden rounded-md border border-slate-200 bg-slate-950">
        <div className="h-full w-full" ref={screenRef} />
      </div>
      <dl className="grid gap-2 text-xs text-slate-600">
        <div className="flex justify-between gap-3">
          <dt>显示器</dt>
          <dd className="font-medium text-slate-900">{data.display}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Web 端口</dt>
          <dd className="font-medium text-slate-900">{data.web_port}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>WebSocket</dt>
          <dd className="truncate font-medium text-slate-900">
            {data.websocket_path}
          </dd>
        </div>
      </dl>
    </div>
  );
}
```

#### 28.6.8.1 这段代码在流程中的位置
​        `VncPanel` 是右侧工作台的可视化入口。
​        它不负责启动浏览器，也不负责执行任务。
​        它只负责：
​        它读取 VNC 状态，拼出 WebSocket 地址，创建 noVNC 的 `RFB` 实例，然后把远程桌面画面渲染到工作台里。组件还会展示连接路径和端口信息，方便排查 Nginx、websockify 或 Sandbox 启动脚本的问题。

### 28.6.9 把 VNC 面板接入工作台
​        打开 `ui/app/components/chat-workspace.tsx`，导入：

```TypeScript
import { VncPanel } from "./vnc-panel";
```

​        在 props 中新增：

```TypeScript
onRefreshVnc: () => void;
vnc: LoadState<VncStatusData>;
```

​        在右侧 `aside` 中，把 VNC 面板放在沙箱状态下面：

```TypeScript
<SandboxStatusPanel
  onRefresh={onRefreshSandbox}
  refreshing={sandboxRefreshing}
  state={sandbox}
/>
<VncPanel onRefresh={onRefreshVnc} state={vnc} />
```

​        打开 `ui/app/page.tsx`，新增状态和加载逻辑：

```TypeScript
const [vncStatus, setVncStatus] = useState<LoadState<VncStatusData>>({
  type: "loading",
});
```

​        在 `loadStatus()` 中和其他基础状态一起加载：

```TypeScript
const [apiData, databaseData, sandboxData, vncData] = await Promise.all([
  requestApi<ApiStatusData>("/api/status"),
  requestApi<DatabaseStatusData>("/api/status/database"),
  fetchCurrentSandbox(),
  fetchVncStatus(),
]);
```

​        新增刷新方法：

```TypeScript
async function refreshVnc() {
  setVncStatus({ type: "loading" });
  try {
    const vnc = await fetchVncStatus();
    setVncStatus({ type: "ready", data: vnc });
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    setVncStatus({ type: "error", message });
  }
}
```

#### 28.6.9.1 为什么 VNC 面板放在沙箱状态下面
​        VNC 是 Sandbox 的可视化能力。
​        先看到“任务沙箱可用”，再看到“浏览器远程桌面”，用户更容易理解两者关系：

```Plain
Sandbox 是执行环境
VNC 是观察这个执行环境的窗口
```

## 28.7 关键理解
​        本章最重要的是理解截图和 VNC 的区别。

```Plain
截图：一次工具调用产生的一张图片
VNC：持续观察沙箱桌面的远程窗口
```

​        截图适合记录工具结果。
​        VNC 适合观察执行过程。
​        第二个重点是理解 noVNC 的路径。
​        浏览器打开：

```Plain
/sandbox-vnc/vnc.html
```

​        前端 noVNC SDK 再连接：

```Plain
ws://localhost:8088/sandbox-vnc/websockify
```

​        这个 WebSocket 路径走 Nginx，再转发到 Sandbox 的 `6080` 端口。

## 28.8 技术难点与亮点
​        本章的技术难点在于显示链路。容器里没有真实显示器，所以必须用 Xvfb 创建虚拟显示器；VNC 是 TCP 协议，浏览器不能直接连接，所以还需要 websockify 把 VNC 转成 WebSocket；前端 noVNC SDK 的 WebSocket 连接又必须经过 Nginx 代理到 Sandbox 的 6080 端口。
​        Playwright 也要从 headless 模式切到有头模式，并且 `DISPLAY` 必须指向 Xvfb 创建的显示器。否则 Chromium 虽然能被启动，却不会出现在远程桌面画面里。本章的亮点，是浏览器能力从“截图结果”升级成“可观察的远程桌面”，而且 VNC 面板直接进入真实工作台，没有再新增孤立演示页。

## 28.9 面试考点
​        面试里问到这一章，可以把显示链路按顺序讲清楚。Xvfb 负责在无显示器容器里创建虚拟显示器，x11vnc 负责把这个显示器画面转成 VNC 服务，websockify 负责把 VNC TCP 连接转成浏览器可以使用的 WebSocket，`@novnc/novnc` 则在前端把 WebSocket 数据渲染成远程桌面。
​        容器里运行有头浏览器需要 `DISPLAY`，是因为 Chromium 必须知道窗口画到哪个 X11 显示器上。noVNC 需要 WebSocket，是因为浏览器不能直接连 VNC TCP 协议。Nginx 代理 WebSocket 时必须保留 `Upgrade` 和 `Connection` 头，否则连接无法升级。截图适合记录某一刻的工具结果，VNC 适合持续观察执行过程。

## 28.10 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 28.10.1 编译 Sandbox 代码

```Bash
cd sandbox
uv run python -m compileall app
```

### 28.10.2 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

### 28.10.3 重新构建 Sandbox 和 UI
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build --no-cache --progress=plain sandbox
docker compose build ui
```

​        这一章会安装 `xvfb`、`x11vnc`、`fluxbox` 和系统命令 `websockify`。构建时间会比普通 API 改动更长，但比 Debian `novnc` 包方案轻很多。
​        这里对 Sandbox 使用 `--no-cache --progress=plain`，是因为本章改了 Dockerfile 的系统依赖安装步骤。`--no-cache` 可以避免继续复用旧镜像层，`--progress=plain` 可以在网络失败时显示更完整的 apt 下载日志。
​        如果构建在 `apt-get install` 阶段报 `exit code: 100`，通常是系统包下载失败或镜像源网络波动。确认 Dockerfile 中没有安装 Debian 的 `novnc` 包后，可以稍后重试，或者按常见问题里的命令切换镜像源。
​        如果之前已经启动过旧的 `sandbox` 容器，建议启动时加上 `--force-recreate`。否则 Docker 可能继续使用旧容器，导致新路由没有生效。

### 28.10.4 启动服务

```Bash
docker compose up -d --force-recreate sandbox api ui nginx
```

​        检查 VNC 状态：

```Bash
curl http://localhost:8088/sandbox-api/vnc/status
```

​        如果返回 `404 Not Found`，说明当前运行中的 Sandbox 还是旧镜像，容器里没有第 28 章新增的 `app/api/routes/vnc.py`。重新执行：

```Bash
docker compose build --no-cache sandbox
docker compose rm -sf sandbox
docker compose up -d --force-recreate sandbox nginx
```

​        然后再次请求 VNC 状态接口。
​        如果仍然是 404，可以进入容器确认文件是否存在：

```Bash
docker compose exec sandbox ls app/api/routes
docker compose exec sandbox sed -n '1,80p' app/api/router.py
```

​        正常情况下应该能看到 `vnc.py`，并且 `router.py` 里有 `include_router(vnc.router)`。
​        预期能看到：

```Plain
enabled: true
websocket_path: sandbox-vnc/websockify
```

​        这个接口正常，说明 Sandbox 已经把 websockify 连接信息暴露给前端。

### 28.10.5 在工作台验证
​        访问：

```Plain
http://localhost:8088
```

​        右侧应该能看到：

```Plain
浏览器远程桌面
```

​        创建会话，发送任务：

```Plain
请访问 https://www.python.org 并截图观察页面
```

​        生成计划并执行后，右侧远程桌面应该能看到 Sandbox 浏览器画面。

## 28.11 常见问题

### 28.11.1 `apt-get install` 阶段报 `exit code: 100` 怎么办？
​        这通常是 Debian 系统包下载失败或镜像源网络波动。第 28 章已经在 Dockerfile 里固定 `python:3.12-slim-bookworm`，默认切到阿里云 Debian 源，并加入 apt 重试、超时和强制 IPv4 参数。
​        确认 Dockerfile 已更新后，先用详细日志看具体卡在哪个包：`docker compose build --no-cache --progress=plain sandbox`。如果你所在网络访问阿里云也慢，可以临时指定其他镜像源：`docker compose build --no-cache --progress=plain --build-arg APT_MIRROR=http://mirrors.ustc.edu.cn/debian --build-arg APT_SECURITY_MIRROR=http://mirrors.ustc.edu.cn/debian-security sandbox`。

### 28.11.2 `uv sync` 阶段下载 `numpy` 超时怎么办？
​        这通常说明 `sandbox/pyproject.toml` 里误加入了 Python 包版 `websockify`。本章需要的是 apt 安装的系统命令 `websockify`，不是 Python 依赖。
​        确认 `sandbox/pyproject.toml` 中没有 `websockify`，并执行 `cd sandbox && uv lock` 更新锁文件，然后重新构建 Sandbox。这样 `uv sync` 就不会因为额外 Python 依赖去下载 `numpy`。

### 28.11.3 `/sandbox-api/vnc/status` 返回 404 怎么办？
​        这通常表示当前运行的 Sandbox 容器还是旧镜像，里面没有第 28 章新增的 VNC 路由。执行 `docker compose build --no-cache sandbox`，再执行 `docker compose rm -sf sandbox` 和 `docker compose up -d --force-recreate sandbox nginx`。
​        如果仍然 404，就进入容器检查 `app/api/routes` 下是否存在 `vnc.py`，并确认 `app/api/router.py` 里已经注册 `include_router(vnc.router)`。

### 28.11.4 noVNC 页面能打开，但一直连接不上怎么办？
​        优先检查 Nginx 是否有 `/sandbox-vnc/` 代理，以及是否设置了 `Upgrade` 和 `Connection` 请求头。WebSocket 连接如果没有正确升级，前端页面能加载，但远程桌面不会真正连上。
​        接着查看 `docker compose logs --tail=80 sandbox`，确认 websockify 是否启动。如果 websockify 没启动，通常要回到 `sandbox/scripts/start.sh` 和容器启动日志排查。

### 28.11.5 远程桌面是黑屏怎么办？
​        黑屏通常说明 VNC 链路通了，但虚拟显示器里没有可见画面。先确认 Sandbox 里是否启动了 Xvfb、fluxbox 和 x11vnc。
​        可以查看 `docker compose logs sandbox`，也可以进入容器检查 `/tmp/x11vnc.log` 和 `/tmp/websockify.log`。如果这些进程正常，再确认浏览器是否以有头模式启动并画到同一个 `DISPLAY`。

### 28.11.6 执行 BrowserTool 后 VNC 里没有浏览器窗口怎么办？
​        先确认 `SANDBOX_BROWSER_HEADLESS=false`，并且 Sandbox 环境变量中有 `DISPLAY=:99`。如果 Chromium 仍然以 headless 模式运行，它可以截图，但不会出现在远程桌面里。
​        如果配置正确但仍然没有窗口，重新构建并重启 Sandbox，确保新的 Dockerfile、启动脚本和环境变量都已经进入容器。

### 28.11.7 为什么不用 iframe 打开 noVNC 自带页面？
​        Debian 的 `novnc` 包会带来较多系统依赖，容易让 Docker 构建变慢或失败。本章改用前端 `@novnc/novnc` SDK，Sandbox 只保留 websockify WebSocket 服务，构建更轻。
​        这样前端也能更好地控制面板样式、连接状态和错误提示。后续统一工具预览面板时，noVNC 组件可以继续作为工作台的一部分复用。

## 28.12 本章小结
​        本章完成了 VNC 远程桌面的最小闭环。Sandbox 容器安装了 Xvfb、x11vnc、fluxbox 和系统命令 `websockify`，启动脚本会同时拉起虚拟显示器、VNC、websockify 和 FastAPI。Nginx 增加 `/sandbox-vnc/` 代理，前端使用 `@novnc/novnc` SDK 渲染远程桌面。
​        Sandbox 还新增了 `/api/vnc/status`，让前端可以读取 websockify 连接路径，而不是硬编码端口。从这一章开始，浏览器能力不只是“截图能看”，而是可以在工作台中持续观察。后续工具预览面板会把文件、Shell、Browser、截图和 VNC 继续收敛到更完整的产品体验中。

## 28.13 下一章预告
​        第 29 章会把文件、Shell、Browser、截图和 VNC 收敛到统一工具预览面板，让右侧工作台更接近真实 Agent 产品。
