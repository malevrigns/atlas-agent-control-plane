# 第十八章. Playwright、CDP 与 BrowserTool

## 18.1 Playwright 与 CDP 奠基

### 18.1.1 本节目标
​        学完本节后，你将能够：
​        文件和 Shell 让 Agent 有了读写与执行能力，但很多真实任务还需要“看网页”。浏览器自动化不是简单打开一个页面，它背后涉及浏览器进程、调试协议、页面上下文、截图结果和后续可视化观察，因此它也必须属于 Sandbox，而不是主 API。
​        学完本节后，你应该能讲清 Playwright、Chromium 和 CDP 之间的关系，也能在 Sandbox 服务中启动 headless Chromium，并编写状态、启动、关闭、导航、页面信息和截图接口。你还要理解 `Browser`、`BrowserContext` 和 `Page` 三个对象各自负责什么。到本节结束时，我们会通过 `/sandbox-api/browser/...` 独立验证浏览器控制链路，但还不会直接把它包装成 BrowserTool，因为工具封装需要建立在稳定的 Browser API 之上。

### 18.1.2 最终效果
​        本节结束后，Sandbox 服务会新增一组浏览器基础接口：

```Plain
GET    /api/browser/status
POST   /api/browser/session
DELETE /api/browser/session
POST   /api/browser/page/navigate
GET    /api/browser/page
POST   /api/browser/page/screenshot
```

​        通过 Nginx 可以访问：

```Plain
http://localhost:8088/sandbox-api/browser/status
```

​        本节完成后的调用链路是：

```Plain
浏览器或 curl
  |
  v
Nginx /sandbox-api
  |
  v
Sandbox Browser API
  |
  v
SandboxBrowserService
  |
  v
Playwright
  |
  v
headless Chromium
```

### 18.1.3 本节要解决的问题
​        第 16 章和第 17 章已经让 Sandbox 具备文件和 Shell 能力。
​        但真实 Agent 不只需要读写文件和执行命令，还经常需要像人一样访问网页：

```Plain
打开网页
读取标题
点击按钮
输入内容
滚动页面
截图观察结果
```

​        如果直接让主 API 操作本机浏览器，会带来两个问题：
​        浏览器运行环境会失去隔离，页面访问、下载文件、截图和缓存都可能影响主 API 所在环境。更麻烦的是，后续 Docker、VNC、文件下载和页面截图需要协同工作，如果浏览器不在 Sandbox 里，这些能力会散落在不同地方，最终很难形成统一执行现场。
​        所以浏览器能力应该放进 Sandbox。
​        本节先完成最小浏览器控制链路：

```Plain
启动 Chromium -> 打开网页 -> 读取页面信息 -> 截图
```

​        本章后文再把这些接口封装成 Agent 可调用的 `BrowserTool`。

### 18.1.4 本节技术方案
​        本节使用 Playwright 控制 Chromium。
​        几个概念先理清楚：
​        `Chromium` 是真正运行网页的浏览器进程，`CDP` 是 Chromium 暴露出来的调试和控制协议。Playwright 站在更高一层，它把底层协议封装成更容易使用的 API，让我们可以用 `page.goto()`、`page.title()`、`page.screenshot()` 这样的代码控制浏览器。
​        在 Playwright 的对象模型里，`Browser` 代表一个浏览器进程，`BrowserContext` 代表一个隔离的浏览器上下文，类似独立用户环境，`Page` 则代表一个网页标签页。本节先用一个共享的 Browser Runtime 保存这几层对象，把最小浏览器控制链路跑通。
​        本节选择在 Sandbox 服务中直接使用 Playwright，原因是：
​        Sandbox 已经是项目里的隔离执行环境，文件、Shell 和浏览器都应该围绕同一个工作目录和执行上下文展开。主 API 不需要知道浏览器进程如何启动，也不需要关心截图是怎么从页面对象中生成的；它只需要在后续通过 Sandbox API 调用浏览器能力。
​        这样设计还有一个好处：第 19 章接入 VNC 时，显示服务、远程桌面和浏览器进程都可以继续在 Sandbox 里扩展，主 API 的边界不会被浏览器运行细节打破。
​        本节暂时不做这些内容：
​        本节不会实现点击、输入、滚动等完整 BrowserTool，也不会做元素提取、VNC 可视化、多浏览器会话或截图文件化。浏览器工具事件也暂时不进入 AI 对话时间线。这里先把 Playwright 控制 Chromium 的底层链路打通，后续第 27、28、29 章再逐步完成工具封装、远程桌面和工具预览。

### 18.1.5 新增和修改的文件

```Plain
.env.example
README.md
docker-compose.yml
backend/sandbox/README.md
backend/sandbox/Dockerfile
backend/sandbox/pyproject.toml
backend/sandbox/uv.lock
backend/sandbox/app/core/config.py
backend/sandbox/app/schemas/browser.py
backend/sandbox/app/services/browser_service.py
backend/sandbox/app/api/routes/browser.py
backend/sandbox/app/api/router.py
docs/course/chapters/26-playwright-cdp.md
```

### 18.1.6 开始前检查：确认 Playwright 依赖
​        进入 Sandbox 目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/backend/sandbox
```

​        安装 Playwright Python 依赖：

```Bash
uv add 'playwright>=1.48,<2.0'
```

​        安装本地 Chromium：

```Bash
uv run playwright install chromium
```

​        第一条命令会更新：

```Plain
backend/sandbox/pyproject.toml
backend/sandbox/uv.lock
```

​        第二条命令会下载浏览器二进制。Playwright 包只是 Python SDK，本地运行浏览器还需要 Chromium。
​        如果只做 Docker 验证，浏览器会在 `backend/sandbox/Dockerfile` 中安装。本地安装主要用于直接运行 `uv run uvicorn app.main:app` 时验证。

### 18.1.7 实施步骤
#### 18.1.7.1 补充 Sandbox 浏览器配置
​        打开 `backend/sandbox/app/core/config.py`，在 Shell 配置后加入：

```Python
    # ----- Browser / CDP：本章先用 Playwright 启动一个 headless Chromium -----
    browser_enabled: bool = True
    browser_headless: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720
    browser_default_timeout_ms: int = 15_000
    browser_screenshot_full_page: bool = True
```

​        打开 `.env.example`，在 Sandbox 配置区域加入：

```Plain
SANDBOX_BROWSER_ENABLED=true
SANDBOX_BROWSER_HEADLESS=true
SANDBOX_BROWSER_VIEWPORT_WIDTH=1280
SANDBOX_BROWSER_VIEWPORT_HEIGHT=720
SANDBOX_BROWSER_DEFAULT_TIMEOUT_MS=15000
SANDBOX_BROWSER_SCREENSHOT_FULL_PAGE=true
```

​        打开 `docker-compose.yml`，在 `sandbox.environment` 中加入：

```YAML
      BROWSER_ENABLED: ${SANDBOX_BROWSER_ENABLED:-true}
      BROWSER_HEADLESS: ${SANDBOX_BROWSER_HEADLESS:-true}
      BROWSER_VIEWPORT_WIDTH: ${SANDBOX_BROWSER_VIEWPORT_WIDTH:-1280}
      BROWSER_VIEWPORT_HEIGHT: ${SANDBOX_BROWSER_VIEWPORT_HEIGHT:-720}
      BROWSER_DEFAULT_TIMEOUT_MS: ${SANDBOX_BROWSER_DEFAULT_TIMEOUT_MS:-15000}
      BROWSER_SCREENSHOT_FULL_PAGE: ${SANDBOX_BROWSER_SCREENSHOT_FULL_PAGE:-true}
```

.1.7.1.1 字段含义
​        `browser_enabled` 用来控制浏览器能力是否启用。浏览器比文件和 Shell 更消耗资源，生产环境里有时需要临时关闭它，这个开关可以让 Sandbox 保持可运行，而不是因为浏览器依赖问题影响所有能力。
​        `browser_headless` 控制是否使用无头浏览器，本节默认开启；第 19 章接入 VNC 后，会继续扩展显示和远程桌面相关配置。`browser_viewport_width` 和 `browser_viewport_height` 决定页面视口大小，后续截图尺寸和元素坐标都依赖它。`browser_default_timeout_ms` 避免网页一直加载导致请求卡住，`browser_screenshot_full_page` 则决定默认截图整页还是只截当前视口。

.1.7.1.2 为什么这样设计
​        浏览器能力比文件和 Shell 更消耗资源。
​        配置项让浏览器能力可以被关闭，也让视口尺寸、超时时间和截图方式可以调整。后续如果浏览器截图太大、网页加载太慢，优先从这些配置排查。

#### 18.1.7.2 定义 Browser API 模型
​        创建 `backend/sandbox/app/schemas/browser.py`：

```Python
from pydantic import BaseModel, Field

class BrowserStatusResponse(BaseModel):
    enabled: bool  # 是否允许 Sandbox 启动浏览器能力。
    session_started: bool  # 当前进程中是否已经启动 Playwright 浏览器会话。
    current_url: str | None  # 当前页面地址，未启动或未导航时为空。
    page_title: str | None  # 当前页面标题，前端工具预览会优先展示它。
    viewport_width: int  # 浏览器视口宽度，后续截图和元素坐标都依赖它。
    viewport_height: int  # 浏览器视口高度，后续截图和元素坐标都依赖它。

class BrowserSessionResponse(BaseModel):
    status: str  # started、closed 或 disabled。
    message: str  # 给调用方展示的状态说明。
    current_url: str | None  # 当前页面地址。
    page_title: str | None  # 当前页面标题。

class BrowserNavigateRequest(BaseModel):
    url: str = Field(min_length=1)  # 要打开的 URL，必须包含协议或由服务补齐。
    wait_until: str = "domcontentloaded"  # Playwright 等待策略，本章默认等 DOM 加载完成。

class BrowserPageResponse(BaseModel):
    url: str  # Playwright 读取到的当前页面地址。
    title: str  # Playwright 读取到的当前页面标题。

class BrowserScreenshotRequest(BaseModel):
    full_page: bool | None = None  # 是否截取完整页面；为空时使用配置默认值。

class BrowserScreenshotResponse(BaseModel):
    mime_type: str  # 截图 MIME 类型，前端用它拼接 data URL。
    base64_data: str  # PNG 截图的 base64 内容，本章先直接返回，后续可改成文件存储。
    size: int  # 截图字节数，用于判断截图是否过大。
```

.1.7.2.1 代码讲解
​        这些模型是 Sandbox Browser API 和外部调用方之间的协议。
​        `BrowserStatusResponse` 用来回答“浏览器能力是否可用、是否已经启动、当前页面是什么”。这类状态后续会进入右侧工具预览或环境状态区域。
​        `BrowserNavigateRequest` 只接收 `url` 和 `wait_until`。本节不做点击和输入，因为本节目标是打通 Playwright/CDP 控制链路。
​        `BrowserScreenshotResponse` 直接返回 `base64_data`，这样用 `curl` 就能验证截图是否产生。后续截图会更适合保存成文件，再把文件 ID 交给前端展示，避免接口响应过大。

#### 18.1.7.3 实现 BrowserService
​        创建 `backend/sandbox/app/services/browser_service.py`：

```Python
import base64
from dataclasses import dataclass

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    async_playwright,
)

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.browser import (
    BrowserPageResponse,
    BrowserScreenshotResponse,
    BrowserSessionResponse,
    BrowserStatusResponse,
)

@dataclass(slots=True)
class BrowserRuntime:
    """Sandbox 进程中的浏览器运行时对象。

    Playwright 通过 CDP 控制 Chromium。路由层不直接保存这些对象，
    统一放在 service 中，后续 BrowserTool 只需要调用 Sandbox API。
    """

    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page

class SandboxBrowserService:
    """管理 Sandbox 中的 Playwright 浏览器会话。

    本章先启动一个共享 headless Chromium，用来理解 CDP 控制链路。
    第 27 章会在这个基础上封装 BrowserTool，让 Agent 通过工具调用它。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # runtime 为空表示浏览器还没启动；启动后会保存 Playwright、Browser、Context、Page。
        self._runtime: BrowserRuntime | None = None

    # ===================== 第1步：查询浏览器状态 =====================
    async def status(self) -> BrowserStatusResponse:
        page = self._runtime.page if self._runtime else None
        return BrowserStatusResponse(
            enabled=self.settings.browser_enabled,
            session_started=self._runtime is not None,
            current_url=page.url if page else None,
            page_title=await self._safe_title(page) if page else None,
            viewport_width=self.settings.browser_viewport_width,
            viewport_height=self.settings.browser_viewport_height,
        )

    # ===================== 第2步：启动和关闭浏览器会话 =====================
    async def start(self) -> BrowserSessionResponse:
        if not self.settings.browser_enabled:
            return BrowserSessionResponse(
                status="disabled",
                message="Browser capability is disabled.",
                current_url=None,
                page_title=None,
            )
        if self._runtime is not None:
            return await self._session_response("started", "Browser session already started.")

        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=self.settings.browser_headless,
                args=[
                    # Docker 容器中常用的 Chromium 启动参数；第 28 章接 VNC 时会继续调整。
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                viewport={
                    "width": self.settings.browser_viewport_width,
                    "height": self.settings.browser_viewport_height,
                }
            )
            context.set_default_timeout(self.settings.browser_default_timeout_ms)
            page = await context.new_page()
        except PlaywrightError as exc:
            raise SandboxException(message=f"failed to start browser: {exc}") from exc

        self._runtime = BrowserRuntime(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
        )
        return await self._session_response("started", "Browser session started.")

    async def close(self) -> BrowserSessionResponse:
        if self._runtime is None:
            return BrowserSessionResponse(
                status="closed",
                message="Browser session is not running.",
                current_url=None,
                page_title=None,
            )

        runtime = self._runtime
        self._runtime = None
        await runtime.context.close()
        await runtime.browser.close()
        await runtime.playwright.stop()
        return BrowserSessionResponse(
            status="closed",
            message="Browser session closed.",
            current_url=None,
            page_title=None,
        )

    # ===================== 第3步：页面导航和信息读取 =====================
    async def navigate(self, url: str, wait_until: str) -> BrowserPageResponse:
        runtime = await self._ensure_runtime()
        target_url = self._normalize_url(url)
        try:
            await runtime.page.goto(target_url, wait_until=wait_until)
        except PlaywrightError as exc:
            raise SandboxException(message=f"failed to navigate page: {exc}") from exc
        return await self.page_info()

    async def page_info(self) -> BrowserPageResponse:
        runtime = await self._ensure_runtime()
        return BrowserPageResponse(
            url=runtime.page.url,
            title=await self._safe_title(runtime.page),
        )

    # ===================== 第4步：页面截图 =====================
    async def screenshot(self, full_page: bool | None = None) -> BrowserScreenshotResponse:
        runtime = await self._ensure_runtime()
        use_full_page = (
            self.settings.browser_screenshot_full_page
            if full_page is None
            else full_page
        )
        try:
            image = await runtime.page.screenshot(full_page=use_full_page, type="png")
        except PlaywrightError as exc:
            raise SandboxException(message=f"failed to capture screenshot: {exc}") from exc

        return BrowserScreenshotResponse(
            mime_type="image/png",
            base64_data=base64.b64encode(image).decode("ascii"),
            size=len(image),
        )

    # ===================== 第5步：辅助方法 =====================
    async def _ensure_runtime(self) -> BrowserRuntime:
        # BrowserTool 调用前可以显式 start；如果忘记启动，这里自动启动一次。
        if self._runtime is None:
            await self.start()
        if self._runtime is None:
            raise SandboxException(message="browser session is not available")
        return self._runtime

    async def _session_response(self, status: str, message: str) -> BrowserSessionResponse:
        runtime = await self._ensure_runtime()
        return BrowserSessionResponse(
            status=status,
            message=message,
            current_url=runtime.page.url,
            page_title=await self._safe_title(runtime.page),
        )

    async def _safe_title(self, page: Page | None) -> str | None:
        if page is None:
            return None
        try:
            return await page.title()
        except PlaywrightError:
            return None

    def _normalize_url(self, value: str) -> str:
        clean_value = value.strip()
        if clean_value.startswith(("http://", "https://")):
            return clean_value
        return f"https://{clean_value}"
```

.1.7.3.1 这段代码在流程中的位置
​        `SandboxBrowserService` 是 Sandbox 服务里的浏览器运行时管理器。
​        调用链路是：

```Plain
Browser API Route
  |
  v
SandboxBrowserService
  |
  v
Playwright async API
  |
  v
Chromium
```

.1.7.3.2 关键代码逐段解释
​        `BrowserRuntime` 保存四个对象：
​        `playwright` 是 Playwright 运行时入口，负责启动和停止自动化框架。`browser` 是实际的 Chromium 浏览器进程，`context` 是隔离的浏览器上下文，`page` 是当前操作的标签页。把这四个对象放进 `BrowserRuntime`，是为了让一次启动后的浏览器会话可以跨多个请求继续使用。
​        `start()` 负责启动 Chromium。这里使用 `headless=True`，所以本节不会看到真实浏览器窗口。第 19 章接 VNC 时，会继续补显示、远程桌面和 WebSocket 代理。
​        `navigate()` 会自动补齐 URL 协议。输入 `example.com` 时，会变成 `https://example.com`。
​        `screenshot()` 返回 PNG 的 base64。这样接口验证最直接，但这不是最终形态。后续真实对话执行里，截图更适合保存到文件系统或对象存储，再在工具预览里展示。

.1.7.3.3 小白最容易困惑的点
​        Playwright 不是浏览器本身。
​        Playwright 是控制器，Chromium 才是浏览器。Playwright 通过 CDP 或浏览器自动化协议控制 Chromium 完成打开网页、点击、输入和截图。

#### 18.1.7.4 新增 Browser API 路由
​        创建 `backend/sandbox/app/api/routes/browser.py`：

```Python
from fastapi import APIRouter, Depends

from app.core.config import settings
from app.schemas.browser import (
    BrowserNavigateRequest,
    BrowserPageResponse,
    BrowserScreenshotRequest,
    BrowserScreenshotResponse,
    BrowserSessionResponse,
    BrowserStatusResponse,
)
from app.schemas.common import ApiResponse
from app.services.browser_service import SandboxBrowserService

router = APIRouter(prefix="/browser", tags=["browser"])

# 浏览器会话需要跨请求保存，所以和 ShellService 一样使用模块级 service。
browser_service = SandboxBrowserService(settings=settings)

def get_browser_service() -> SandboxBrowserService:
    return browser_service

@router.get("/status", response_model=ApiResponse[BrowserStatusResponse])
async def get_browser_status(
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserStatusResponse]:
    # 前端或主 API 可以先读状态，判断浏览器是否已经启动。
    return ApiResponse(data=await service.status())

@router.post("/session", response_model=ApiResponse[BrowserSessionResponse])
async def start_browser_session(
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserSessionResponse]:
    # 显式启动浏览器会话；如果已经启动，返回当前会话信息。
    return ApiResponse(data=await service.start())

@router.delete("/session", response_model=ApiResponse[BrowserSessionResponse])
async def close_browser_session(
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserSessionResponse]:
    # 关闭当前 Playwright/Chromium 会话，释放浏览器资源。
    return ApiResponse(data=await service.close())

@router.post("/page/navigate", response_model=ApiResponse[BrowserPageResponse])
async def navigate_page(
    payload: BrowserNavigateRequest,
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserPageResponse]:
    # 本章先只做导航；第 27 章会继续封装点击、输入、滚动等 BrowserTool。
    return ApiResponse(data=await service.navigate(payload.url, payload.wait_until))

@router.get("/page", response_model=ApiResponse[BrowserPageResponse])
async def get_page_info(
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserPageResponse]:
    # 读取当前页面 URL 和标题，用来验证 CDP 控制链路已经打通。
    return ApiResponse(data=await service.page_info())

@router.post("/page/screenshot", response_model=ApiResponse[BrowserScreenshotResponse])
async def capture_screenshot(
    payload: BrowserScreenshotRequest,
    service: SandboxBrowserService = Depends(get_browser_service),
) -> ApiResponse[BrowserScreenshotResponse]:
    # 返回 PNG base64；后续可以改成写入文件系统，再把文件 ID 返回给前端。
    return ApiResponse(data=await service.screenshot(payload.full_page))
```

​        打开 `backend/sandbox/app/api/router.py`，注册路由：

```Python
from fastapi import APIRouter

from app.api.routes import browser, files, shell, status, supervisor

api_router = APIRouter()
api_router.include_router(browser.router)
api_router.include_router(files.router)
api_router.include_router(shell.router)
api_router.include_router(status.router)
api_router.include_router(supervisor.router)
```

.1.7.4.1 这段代码在流程中的位置
​        Browser 路由是 Sandbox 服务对外暴露的浏览器控制入口。
​        本章后文主 API 会调用这些接口，把它们包装成 Agent 可使用的 BrowserTool。本节先不让 Agent 直接调用浏览器，是为了把浏览器运行环境和接口协议先稳定下来。

.1.7.4.2 为什么使用模块级 service
​        浏览器会话需要跨请求保存。
​        如果每次请求都创建新的 `SandboxBrowserService`，上一次打开的页面就会丢失，截图也无法截到刚导航的页面。
​        所以这里和 Shell 会话一样，使用模块级 service 保存进程内状态。

#### 18.1.7.5 更新 Sandbox Dockerfile
​        打开 `backend/sandbox/Dockerfile`，在第一次 `uv sync` 后加入：

```Dockerfile
# Playwright 需要浏览器二进制和系统依赖。
# 本章先安装 headless Chromium，第 28 章接入 VNC 时再扩展显示相关进程。
RUN uv run playwright install --with-deps chromium
```

​        完整关键片段如下：

```Dockerfile
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Playwright 需要浏览器二进制和系统依赖。
# 本章先安装 headless Chromium，第 28 章接入 VNC 时再扩展显示相关进程。
RUN uv run playwright install --with-deps chromium

COPY app ./app

RUN uv sync --frozen --no-dev
```

.1.7.5.1 为什么 Dockerfile 也要安装 Chromium
​        `uv add playwright` 只安装 Python SDK。
​        容器里运行浏览器时，还需要 Chromium 二进制和系统依赖。`playwright install --with-deps chromium` 会安装这些内容。
​        这一步构建时间会明显变长，这是正常现象。

#### 18.1.7.6 更新 Sandbox README
​        打开 `backend/sandbox/README.md`，在接口列表中加入：

```Plain
/api/browser/status
/api/browser/session
/api/browser/page/navigate
/api/browser/page
/api/browser/page/screenshot
```

​        这份 README 是给开发时快速查接口用的，不影响运行。

### 18.1.8 关键理解
​        本节最重要的是理解“浏览器能力属于 Sandbox，而不是主 API”。
​        主 API 负责 Agent 编排、会话、事件和工具调用。
​        Sandbox 负责隔离执行环境，包括：

```Plain
文件
Shell
浏览器
后续 VNC
```

​        第二个重点是理解 Playwright 和 CDP。
​        CDP 是 Chromium 暴露的控制协议，Playwright 封装了这些控制能力。代码里调用 `page.goto()` 和 `page.screenshot()`，底层其实是在控制浏览器。
​        第三个重点是理解本节边界。
​        本节只打通浏览器控制链路，不把它直接接进 AI 对话过程。本章后文会把这些能力包装为 BrowserTool，第 19 章会把浏览器动作和截图收敛进统一工具预览面板。

### 18.1.9 技术难点与亮点
​        本节的技术难点，首先是 Playwright Python 依赖和 Chromium 浏览器二进制不是一回事。安装了 Playwright SDK，并不意味着环境里已经有可启动的浏览器。Docker 容器里运行 Chromium 还需要额外系统依赖，所以 Dockerfile 中必须执行 `playwright install --with-deps chromium`。
​        第二个难点是浏览器会话需要跨请求保存。启动浏览器、导航页面、读取标题、截图，往往发生在不同请求中。如果每次请求都创建新的 service 或新的浏览器对象，就会丢失上一次打开的页面。截图直接返回 base64 虽然方便验证，但后续也要考虑响应体变大、前端展示和文件存储的问题。
​        本节的亮点，是浏览器能力正式进入 Sandbox，保持执行环境隔离。API 先稳定浏览器控制协议，本章后文再做工具封装；`BrowserRuntime` 明确保存 Playwright、Browser、Context 和 Page 四层对象；通过 `/sandbox-api/browser/...` 可以独立验证 Playwright 控制 Chromium 的链路。

### 18.1.10 面试考点
​        面试里问到这一阶段，可以先讲 Playwright 和 Chromium 的关系。Chromium 是浏览器，Playwright 是自动化控制框架；CDP 则是浏览器暴露出来的调试与控制协议。Playwright 封装底层协议，让开发者用更稳定的 API 完成导航、截图和页面操作。
​        浏览器自动化应该放在 Sandbox 中，是因为它会启动外部进程，产生缓存、下载文件、截图和远程桌面状态。主 API 只应该编排任务，不应该直接承载这些执行细节。`Browser`、`BrowserContext` 和 `Page` 分别对应浏览器进程、隔离上下文和标签页；浏览器会话需要跨请求保存，是因为启动、导航和截图常常不是同一个请求完成。
​        Docker 中运行 Chromium 需要额外系统依赖，这一点也很容易被问到。Playwright SDK 只是控制代码，浏览器二进制和字体、图形、沙箱等依赖需要在镜像里安装，否则运行时会出现浏览器可执行文件不存在或系统库缺失的问题。

### 18.1.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 18.1.11.1 编译 Sandbox 代码

```Bash
cd backend/sandbox
uv run python -m compileall app
```

#### 18.1.11.2 本地运行 Sandbox 服务
​        如果本地已经执行过：

```Bash
uv run playwright install chromium
```

​        可以启动 Sandbox：

```Bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8100
```

​        打开另一个终端验证：

```Bash
curl http://localhost:8100/api/browser/status
```

​        预期返回：

```Plain
enabled: true
session_started: false
```

​        启动浏览器：

```Bash
curl -X POST http://localhost:8100/api/browser/session
```

​        打开网页：

```Bash
curl -X POST http://localhost:8100/api/browser/page/navigate \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

​        预期能看到：

```Plain
Example Domain
```

​        截图：

```Bash
curl -X POST http://localhost:8100/api/browser/page/screenshot \
  -H "Content-Type: application/json" \
  -d '{"full_page":true}'
```

​        预期返回中包含：

```Plain
mime_type: image/png
base64_data
size
```

​        关闭浏览器：

```Bash
curl -X DELETE http://localhost:8100/api/browser/session
```

#### 18.1.11.3 Docker Compose 验证
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        重新构建 Sandbox 镜像：

```Bash
docker compose build sandbox
```

​        这一步会安装 Chromium 和系统依赖，耗时会比前几章更长。
​        启动服务：

```Bash
docker compose up -d sandbox nginx
```

​        验证状态：

```Bash
curl http://localhost:8088/sandbox-api/browser/status
```

​        启动浏览器并导航：

```Bash
curl -X POST http://localhost:8088/sandbox-api/browser/session
curl -X POST http://localhost:8088/sandbox-api/browser/page/navigate \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

​        截图：

```Bash
curl -X POST http://localhost:8088/sandbox-api/browser/page/screenshot \
  -H "Content-Type: application/json" \
  -d '{"full_page":true}'
```

​        如果接口正常，说明：

```Plain
Nginx -> Sandbox API -> Playwright -> Chromium
```

​        这条链路已经打通。

### 18.1.12 小结
​        本节完成了浏览器自动化的基础链路。Sandbox 增加了 Playwright 依赖，Dockerfile 负责安装 Chromium 和系统依赖，配置层新增了浏览器开关、视口、超时和截图选项。接口层新增 Browser API 请求和响应模型，服务层新增 `SandboxBrowserService`，负责启动、关闭、导航、读取页面信息和截图。
​        通过 `/sandbox-api/browser/...`，我们已经能独立验证 Playwright 控制 Chromium 的过程。从这一阶段开始，Sandbox 不再只是文件和 Shell 环境，也具备了网页访问和观察能力。本章后文再把这些基础接口包装成 Agent 可以调用的 BrowserTool。

## 18.2 BrowserTool 浏览器工具成形

### 18.2.1 本节目标
​        学完本节后，你将能够：
​        前文已经证明 Sandbox 可以启动 Chromium、打开网页并截图，但那仍然只是底层 Browser API。真实 Agent 不应该让用户手动调用 `/sandbox-api/browser/page/navigate`，而应该在执行任务时，把“打开网页”和“截图观察”当作工具能力自然调用。
​        学完本节后，你应该能区分 Browser API 和 BrowserTool：前者是 Sandbox 暴露的底层浏览器控制接口，后者是主 API 注册给 Agent 的工具封装。本节会在主 API 中封装 `SandboxBrowserClient`，把浏览器状态、打开网页、截图和关闭会话注册成工具，并让 ReAct 执行步骤在识别到网页访问或截图意图时触发这些工具。前端事件记录也会开始展示工具参数、工具输出和浏览器截图，让浏览器能力进入真实 AI 对话执行过程。

### 18.2.2 最终效果
​        本节结束后，主 API 的工具注册表会新增：

```Plain
browser_status
browser_open
browser_screenshot
browser_close
```

​        执行计划时，如果步骤里出现：

```Plain
访问网页
打开网站
浏览器
截图
```

​        ReAct 执行服务会优先调用 BrowserTool。
​        前端事件记录不再只显示 `tool_called`，而是会展示：

```Plain
工具名称
调用参数
工具输出
浏览器截图预览
```

​        本节完成后的调用链路是：

```Plain
计划步骤
  |
  v
ReActAgentService
  |
  v
BrowserTool
  |
  v
SandboxBrowserClient
  |
  v
Sandbox Browser API
  |
  v
Playwright / Chromium
  |
  v
tool_called 事件
  |
  v
前端事件记录展示
```

### 18.2.3 本节要解决的问题
​        前文已经让 Sandbox 可以启动浏览器、打开网页和截图。
​        但那还只是 Sandbox API：

```Plain
curl /sandbox-api/browser/page/navigate
curl /sandbox-api/browser/page/screenshot
```

​        真实 Agent 不应该让用户手动调这些接口。Agent 应该在执行任务时，把浏览器能力当成工具：

```Plain
用户任务
  |
  v
计划步骤
  |
  v
Agent 判断需要打开网页
  |
  v
调用 browser_open
  |
  v
生成 tool_called 事件
  |
  v
前端展示工具调用结果
```

​        所以本节把 Browser API 封装成 BrowserTool，并让工具结果进入前端事件记录。

### 18.2.4 本节技术方案
​        本节继续沿用已有工具协议：

```Plain
ToolDefinition
ToolParameter
AgentTool
ToolRegistry
ToolCallResult
```

​        新增一层 `SandboxBrowserClient`：

```Plain
BrowserTool
  |
  v
SandboxBrowserClient
  |
  v
Sandbox Browser API
```

​        这样 BrowserTool 不需要导入 Playwright，也不需要知道浏览器运行在哪个容器。
​        前端不新增孤立演示页面，而是在现有事件记录中增强 `tool_called` 展示。
​        本节暂时不做这些内容：
​        本节不会做完整元素识别，也不会加入点击、输入、滚动工具。VNC 可视化、多标签页管理和统一工具预览面板的最终形态，也会继续留到后续章节。这里先把 Browser API 变成 Agent 可调用的工具，并让工具结果能进入事件记录。

### 18.2.5 新增和修改的文件

```Plain
README.md
docs/course/chapters/27-browser-tool.md
backend/api/app/infrastructure/sandbox/browser_client.py
backend/api/app/infrastructure/agent_tools/sandbox_browser.py
backend/api/app/infrastructure/agent_tools/builtin.py
backend/api/app/application/react_agent_service.py
frontend/web/app/components/event-timeline.tsx
```

### 18.2.6 实施步骤
#### 18.2.6.1 封装 SandboxBrowserClient
​        创建 `backend/api/app/infrastructure/sandbox/browser_client.py`：

```Python
from typing import Any

import httpx

from app.core.exceptions import AppException

class SandboxBrowserClient:
    """主 API 访问 Sandbox Browser API 的同步客户端。

    BrowserTool 不直接依赖 Playwright，只通过这个 client 调用 Sandbox。
    这样浏览器进程仍然被限制在隔离容器里。
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：浏览器会话状态和生命周期 =====================
    def status(self) -> dict[str, Any]:
        return self._request("GET", "/browser/status")

    def start(self) -> dict[str, Any]:
        return self._request("POST", "/browser/session")

    def close(self) -> dict[str, Any]:
        return self._request("DELETE", "/browser/session")

    # ===================== 第2步：页面操作 =====================
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/navigate",
            json={"url": url, "wait_until": wait_until},
        )

    def page_info(self) -> dict[str, Any]:
        return self._request("GET", "/browser/page")

    def screenshot(self, full_page: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/screenshot",
            json={"full_page": full_page},
        )

    # ===================== 第3步：统一处理 Sandbox 响应 =====================
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
                message=f"sandbox browser request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox browser returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox browser request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox browser returned invalid data",
                code=502,
                status_code=502,
            )
        return data
```

.2.6.1.1 这段代码在流程中的位置
​        `SandboxBrowserClient` 是主 API 到 Sandbox Browser API 的适配层。
​        它的作用类似第 16 章的 `SandboxFileClient` 和第 17 章的 `SandboxShellClient`。
​        BrowserTool 不直接请求 `httpx`，而是通过 client 调用：

```Plain
browser_open
  |
  v
SandboxBrowserClient.navigate()
  |
  v
POST /sandbox-api/browser/page/navigate
```

.2.6.1.2 为什么这样设计
​        这样可以把错误处理集中在一个地方。
​        如果 Sandbox 返回非 JSON、HTTP 500、业务 code 不是 200，client 会统一转成 `AppException`。上层工具不用重复写这些判断。

#### 18.2.6.2 注册 BrowserTool
​        创建 `backend/api/app/infrastructure/agent_tools/sandbox_browser.py`：

```Python
import json

from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.infrastructure.sandbox.browser_client import SandboxBrowserClient

def build_sandbox_browser_client() -> SandboxBrowserClient:
    """根据主 API 配置创建 Sandbox Browser 客户端。"""

    return SandboxBrowserClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )

def register_sandbox_browser_tools(
    registry: ToolRegistry,
    client: SandboxBrowserClient | None = None,
) -> None:
    """把 Sandbox 浏览器能力注册成 Agent 可调用工具。

    这些工具不直接控制本机浏览器，而是转发到 Sandbox Browser API。
    """

    browser_client = client or build_sandbox_browser_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_status",
                description="查看 Sandbox 浏览器会话状态、当前页面和视口信息。",
                parameters=[],
            ),
            handler=lambda: _format_status(browser_client.status()),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_open",
                description="在 Sandbox 浏览器中打开一个网页，并返回页面地址和标题。",
                parameters=[
                    ToolParameter(
                        name="url",
                        type="string",
                        description="要打开的网页地址，例如 https://example.com。",
                    )
                ],
            ),
            handler=lambda url: _format_page(browser_client.navigate(url=url)),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_screenshot",
                description="截取当前浏览器页面，返回图片信息和 base64 数据。",
                parameters=[
                    ToolParameter(
                        name="full_page",
                        type="boolean",
                        description="是否截取完整页面，默认 true。",
                        required=False,
                    )
                ],
            ),
            handler=lambda full_page=True: _format_screenshot(
                browser_client.screenshot(full_page=_to_bool(full_page))
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_close",
                description="关闭 Sandbox 浏览器会话，释放浏览器资源。",
                parameters=[],
            ),
            handler=lambda: _format_session(browser_client.close()),
        )
    )

def _format_status(data: dict) -> str:
    return "\n".join(
        [
            f"浏览器启用：{data.get('enabled')}",
            f"会话已启动：{data.get('session_started')}",
            f"当前地址：{data.get('current_url') or '-'}",
            f"页面标题：{data.get('page_title') or '-'}",
            f"视口：{data.get('viewport_width')}x{data.get('viewport_height')}",
        ]
    )

def _format_page(data: dict) -> str:
    return "\n".join(
        [
            f"页面已打开：{data.get('url')}",
            f"页面标题：{data.get('title') or '-'}",
        ]
    )

def _format_screenshot(data: dict) -> str:
    # 截图结果使用 JSON，前端事件面板可以解析后直接显示图片。
    return json.dumps(
        {
            "kind": "browser_screenshot",
            "mime_type": data.get("mime_type"),
            "base64_data": data.get("base64_data"),
            "size": data.get("size"),
        },
        ensure_ascii=False,
    )

def _format_session(data: dict) -> str:
    return f"{data.get('message')} status={data.get('status')}"

def _to_bool(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"false", "0", "no"}
    return bool(value)
```

​        打开 `backend/api/app/infrastructure/agent_tools/builtin.py`，注册 BrowserTool：

```Python
from app.infrastructure.agent_tools.sandbox_browser import register_sandbox_browser_tools
```

​        在 `build_builtin_tool_registry()` 里加入：

```Python
register_sandbox_browser_tools(registry)
```

.2.6.2.1 这段代码在流程中的位置
​        这一步把浏览器能力加入工具注册表。
​        注册后，`GET /api/agent-core/tools` 会看到 `browser_open`、`browser_screenshot` 等工具，ReAct 执行服务也可以通过 `self.registry.get("browser_open")` 找到工具。

.2.6.2.2 为什么截图结果用 JSON 字符串
​        当前工具协议的 `ToolCallResult.output` 是字符串。
​        为了让前端能识别截图，本节把截图结果格式化成 JSON 字符串：

```JSON
{
  "kind": "browser_screenshot",
  "mime_type": "image/png",
  "base64_data": "...",
  "size": 12345
}
```

​        这不是最终工具事件协议，但足够支撑本节的前端图片预览。第 19 章会把工具预览面板统一重构。

#### 18.2.6.3 让 ReAct 步骤触发 BrowserTool
​        打开 `backend/api/app/application/react_agent_service.py`，新增 import：

```Python
from urllib.parse import urlparse
```

​        在 `_execute_step()` 中，把计划、步骤和序号一起传给工具选择方法：

```Python
tool_result = self._call_tool_for_step(plan=plan, step=step, index=index)
```

​        在 `_call_tool_for_step()` 中，把浏览器判断放在其他教学工具之前：

```Python
def _call_tool_for_step(self, plan: dict, step: dict, index: int) -> dict:
    """根据计划目标和步骤内容选择并调用一个内置工具。

    这里同时读取 plan.goal 和 step 文本，是为了避免计划步骤被概括后
    丢失用户原始任务里的“访问网页、截图”等关键信息。
    """

    goal = str(plan.get("goal", ""))
    title = str(step.get("title", ""))
    description = str(step.get("description", ""))
    expected_output = str(step.get("expected_output", ""))
    step_text = f"{title} {description} {expected_output}".strip()
    text = f"{goal} {step_text}".strip()

    if self._needs_browser_screenshot(text):
        # 同一个任务里同时出现“访问”和“截图”时，先打开页面，再截图。
        # 这样即使规划步骤比较抽象，也能稳定产生 browser_open 和 browser_screenshot。
        if index == 1 or self._needs_browser_open(step_text):
            tool = self.registry.get("browser_open")
            arguments = {"url": self._extract_url(text)}
        else:
            tool = self.registry.get("browser_screenshot")
            arguments = {"full_page": True}
    elif self._needs_browser_open(text):
        tool = self.registry.get("browser_open")
        arguments = {"url": self._extract_url(text)}
    elif "拆" in title or "步骤" in title or "计划" in title:
        tool = self.registry.get("draft_plan")
        arguments = {"task": text}
```

​        继续新增三个辅助方法：

```Python
def _needs_browser_open(self, text: str) -> bool:
    """判断当前步骤是否需要打开网页。"""

    keywords = ["网页", "网站", "浏览器", "访问", "打开", "页面"]
    return any(keyword in text for keyword in keywords)

def _needs_browser_screenshot(self, text: str) -> bool:
    """判断当前步骤是否需要对页面截图。"""

    keywords = ["截图", "截屏", "页面截图", "观察页面"]
    return any(keyword in text for keyword in keywords)

def _extract_url(self, text: str) -> str:
    """从计划步骤中提取 URL，没有 URL 时使用稳定示例站点。

    本章先用简单规则，后续会由 LLM 结构化输出工具参数。
    """

    for token in text.split():
        clean_token = token.strip("，。,.!?！？、()（）")
        parsed = urlparse(clean_token)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return clean_token
    return "https://example.com"
```

.2.6.3.1 这段代码在流程中的位置
​        第 13 章的 ReAct 执行服务本来会根据步骤内容选择教学工具。
​        本节把浏览器判断放在最前面。这样只要计划目标或步骤内容包含“网页、网站、浏览器、访问、截图”等关键词，就会触发 BrowserTool。
​        执行计划时，每个步骤结束后都会提交一次事件。这样前端轮询事件列表时，可以逐步看到：

```Plain
step_started -> tool_called -> step_completed
```

​        如果某个浏览器工具超时或失败，错误事件会带上当前 `step_id`，前端就能把对应步骤从 `running` 改成 `failed`，而不是一直停在运行中。

.2.6.3.2 为什么本节用简单规则
​        现在还没有完整的 LLM 工具参数生成。
​        所以本节先用关键词和 URL 提取规则，让浏览器工具进入真实执行链路。后续 LLM 结构化输出成熟后，会由模型明确生成：

```JSON
{"tool_name":"browser_open","arguments":{"url":"https://example.com"}}
```

#### 18.2.6.4 增强前端事件记录
​        打开 `frontend/web/app/components/event-timeline.tsx`，在事件时间后加入：

```TypeScript
<EventPayload event={event} />
```

​        然后新增 `EventPayload`：

```TypeScript
function EventPayload({ event }: { event: SessionEventItem }) {
  if (event.type !== "tool_called") {
    return null;
  }

  const toolName = getString(event.payload.tool_name);
  const output = getString(event.payload.output);
  const screenshot = parseScreenshot(output);

  return (
    <div className="mt-2 grid gap-2 text-xs text-slate-600">
      <div>
        <span className="font-medium text-slate-700">工具：</span>
        {toolName || "-"}
      </div>
      <pre className="max-h-24 overflow-auto rounded-md bg-white p-2 text-[11px] leading-5 text-slate-600">
        {JSON.stringify(event.payload.arguments ?? {}, null, 2)}
      </pre>
      {screenshot ? (
        <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
          <img
            alt="浏览器截图"
            className="max-h-48 w-full object-contain"
            src={`data:${screenshot.mime_type};base64,${screenshot.base64_data}`}
          />
          <div className="border-t border-slate-200 px-2 py-1 text-[11px] text-slate-500">
            {screenshot.mime_type} · {screenshot.size} bytes
          </div>
        </div>
      ) : (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-md bg-white p-2 text-[11px] leading-5 text-slate-600">
          {output || "<no output>"}
        </pre>
      )}
    </div>
  );
}
```

​        再新增截图解析工具：

```TypeScript
type ScreenshotPayload = {
  kind: "browser_screenshot";
  mime_type: string;
  base64_data: string;
  size: number;
};

function parseScreenshot(value: string): ScreenshotPayload | null {
  try {
    const payload = JSON.parse(value) as Partial<ScreenshotPayload>;
    if (
      payload.kind === "browser_screenshot" &&
      typeof payload.mime_type === "string" &&
      typeof payload.base64_data === "string" &&
      typeof payload.size === "number"
    ) {
      return payload as ScreenshotPayload;
    }
  } catch {
    return null;
  }
  return null;
}

function getString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
```

.2.6.4.1 这段代码在流程中的位置
​        第 7 章的事件记录只能显示事件类型。
​        本节开始展示工具调用详情：

```Plain
tool_called
  |
  +-- tool_name
  +-- arguments
  +-- output
  +-- browser screenshot
```

​        这让浏览器工具不再只是接口验证，而是进入了对话执行过程。

.2.6.4.2 为什么这里还不是最终工具预览面板
​        本节先在事件记录里展示工具详情，是为了尽早让浏览器工具结果可见。
​        第 19 章会集中重构工具预览面板，把 File、Shell、Browser、Search 等工具输出统一展示。

### 18.2.7 关键理解
​        本节最重要的是理解 Browser API 和 BrowserTool 的区别。

```Plain
Browser API：Sandbox 提供的底层浏览器控制接口
BrowserTool：Agent 可以调用的工具封装
```

​        前文解决的是“浏览器能不能被控制”。
​        本节解决的是“Agent 能不能把浏览器当工具调用，并让前端看到结果”。
​        第二个重点是理解本节的前端收敛方向。
​        本节没有新增独立浏览器演示页，而是增强事件记录。因为浏览器动作应该属于当前任务执行过程，而不是孤立按钮。

### 18.2.8 技术难点与亮点
​        本节的技术难点在于分层。BrowserTool 不能直接导入 Playwright，也不能在主 API 里启动浏览器进程；它必须通过 `SandboxBrowserClient` 调用 Sandbox Browser API，继续保持浏览器运行环境隔离。
​        截图结果也比普通文本工具复杂。它本质上是二进制图片，本节暂时把它编码成 JSON 字符串放进 `ToolCallResult.output`，前端再尝试解析这个字符串并生成 `data:image/png;base64,...` 预览。这个方案不是最终协议，但能让截图尽早进入事件记录。
​        ReAct 侧同样有过渡性设计。当前还没有完整的 LLM 结构化工具参数生成，所以本节先用关键词和 URL 提取规则触发浏览器工具。项目亮点在于浏览器能力已经进入 Agent 工具体系，`tool_called` 事件开始展示真实工具参数和结果，前端也不再新增孤立演示 UI，而是把能力合并进工作台事件记录。

### 18.2.9 面试考点
​        面试里问到这一阶段，可以先说明 Browser API 和 BrowserTool 的层次差异。Browser API 属于 Sandbox，是底层浏览器控制能力；BrowserTool 属于主 API 的工具体系，是 Agent 能调用的封装。主 API 不应该直接启动 Playwright，因为浏览器进程、页面状态和截图都属于执行环境，应该留在 Sandbox。
​        工具调用结果进入事件流，是为了让用户能看到 Agent 执行过程中到底调用了什么工具、传了什么参数、拿到了什么结果。截图这种二进制结果可以先编码成 base64，再由前端拼成 data URL 展示。后续更成熟的做法，是把截图保存成文件对象，再在工具预览面板中引用。
​        本节使用规则选择工具，是因为当前还没有完整 LLM 结构化工具调用。等后续工具参数生成稳定后，模型应该直接给出 `tool_name` 和 `arguments`，而不是依赖关键词判断。

### 18.2.10 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

#### 18.2.10.1 编译和类型检查

```Bash
cd backend/api
uv run python -m compileall app

cd ../../frontend/web
pnpm typecheck
```

#### 18.2.10.2 启动服务
​        如果前文已经构建过 Sandbox 镜像，可以直接启动：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose up -d sandbox api ui nginx
```

​        如果还没有构建过包含 Chromium 的 Sandbox 镜像，先执行：

```Bash
docker compose build sandbox
```

​        再启动：

```Bash
docker compose up -d sandbox api ui nginx
```

#### 18.2.10.3 验证 Browser API

```Bash
curl http://localhost:8088/sandbox-api/browser/status
curl -X POST http://localhost:8088/sandbox-api/browser/session
curl -X POST http://localhost:8088/sandbox-api/browser/page/navigate \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

​        预期导航接口返回页面标题：

```Plain
Example Domain
```

#### 18.2.10.4 验证工具列表

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期能看到：

```Plain
browser_status
browser_open
browser_screenshot
browser_close
```

#### 18.2.10.5 验证前端事件展示
​        访问：

```Plain
http://localhost:8088
```

​        创建一个会话，发送任务。第一次验证建议使用稳定、页面很轻的 `example.com`：

```Plain
请访问 https://example.com 并截图观察页面
```

​        `example.com` 不是假地址，它是 IANA 保留的真实示例域名，页面很轻，适合先确认 BrowserTool 链路是否打通。
​        基础链路正常后，再用真实网站验证浏览器工具：

```Plain
请访问 https://www.python.org 并截图观察页面
```

​        如果这一步也正常，再测试 `https://baidu.com` 这类资源更多、网络波动更明显的网站。
​        然后按顺序操作：

```Plain
1. 点击右侧计划区域的生成按钮
2. 等事件记录出现 plan_created
3. 点击执行按钮
4. 等执行任务状态变成 succeeded
```

​        预期事件记录中能看到：

```Plain
step_started
tool_called
工具：browser_open
调用参数：{"url":"https://example.com"}
工具输出：页面已打开

tool_called
工具：browser_screenshot
调用参数：{"full_page":true}
浏览器截图预览

step_completed
task_done
```

​        如果页面里只看到 `message_created`，说明当前还只是“消息已保存”，计划还没有生成或还没有执行。先确认是否已经看到 `plan_created`，再点击执行按钮。
​        如果步骤长时间停在 `running`，通常是浏览器工具还没有返回。优先用 `https://example.com` 验证基础链路，再用 `https://www.python.org` 验证真实网站；如果只在 `https://baidu.com` 上卡住，说明更可能是容器网络、目标站点加载速度或浏览器导航超时问题。

### 18.2.11 小结
​        本节完成了 BrowserTool 的第一版。主 API 新增了 `SandboxBrowserClient`，并注册了 `browser_status`、`browser_open`、`browser_screenshot` 和 `browser_close` 这些浏览器工具。ReAct 执行服务也开始根据计划目标和步骤内容，触发浏览器打开网页或截图。
​        前端事件记录现在可以展示工具名称、调用参数、普通文本输出和浏览器截图。从这一阶段开始，浏览器能力不再只是 Sandbox API，而是进入了 Agent 工具体系，也开始真正出现在用户可观察的执行流里。

## 18.3 本章小结

​        完成“Playwright 与 CDP 奠基”和“BrowserTool 浏览器工具成形”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第十七章. Sandbox Shell 与 Docker 隔离](17-Sandbox%20Shell%20与%20Docker%20隔离.md) · [返回目录](../README.md) · [第十九章. VNC 远程桌面与工具预览 →](19-VNC%20远程桌面与工具预览.md)
