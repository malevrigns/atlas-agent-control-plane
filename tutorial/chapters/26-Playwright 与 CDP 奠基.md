# 第二十六章. Playwright 与 CDP 奠基

## 26.1 本章目标
​        学完本章后，你将能够：
​        文件和 Shell 让 Agent 有了读写与执行能力，但很多真实任务还需要“看网页”。浏览器自动化不是简单打开一个页面，它背后涉及浏览器进程、调试协议、页面上下文、截图结果和后续可视化观察，因此它也必须属于 Sandbox，而不是主 API。
​        学完本章后，你应该能讲清 Playwright、Chromium 和 CDP 之间的关系，也能在 Sandbox 服务中启动 headless Chromium，并编写状态、启动、关闭、导航、页面信息和截图接口。你还要理解 `Browser`、`BrowserContext` 和 `Page` 三个对象各自负责什么。到本章结束时，我们会通过 `/sandbox-api/browser/...` 独立验证浏览器控制链路，但还不会直接把它包装成 BrowserTool，因为工具封装需要建立在稳定的 Browser API 之上。

## 26.2 最终效果
​        本章结束后，Sandbox 服务会新增一组浏览器基础接口：

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

​        本章完成后的调用链路是：

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

## 26.3 本章要解决的问题
​        第 23 章和第 24 章已经让 Sandbox 具备文件和 Shell 能力。
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
​        本章先完成最小浏览器控制链路：

```Plain
启动 Chromium -> 打开网页 -> 读取页面信息 -> 截图
```

​        第 27 章再把这些接口封装成 Agent 可调用的 `BrowserTool`。

## 26.4 本章技术方案
​        本章使用 Playwright 控制 Chromium。
​        几个概念先理清楚：
​        `Chromium` 是真正运行网页的浏览器进程，`CDP` 是 Chromium 暴露出来的调试和控制协议。Playwright 站在更高一层，它把底层协议封装成更容易使用的 API，让我们可以用 `page.goto()`、`page.title()`、`page.screenshot()` 这样的代码控制浏览器。
​        在 Playwright 的对象模型里，`Browser` 代表一个浏览器进程，`BrowserContext` 代表一个隔离的浏览器上下文，类似独立用户环境，`Page` 则代表一个网页标签页。本章先用一个共享的 Browser Runtime 保存这几层对象，把最小浏览器控制链路跑通。
​        本章选择在 Sandbox 服务中直接使用 Playwright，原因是：
​        Sandbox 已经是项目里的隔离执行环境，文件、Shell 和浏览器都应该围绕同一个工作目录和执行上下文展开。主 API 不需要知道浏览器进程如何启动，也不需要关心截图是怎么从页面对象中生成的；它只需要在后续通过 Sandbox API 调用浏览器能力。
​        这样设计还有一个好处：第 28 章接入 VNC 时，显示服务、远程桌面和浏览器进程都可以继续在 Sandbox 里扩展，主 API 的边界不会被浏览器运行细节打破。
​        本章暂时不做这些内容：
​        本章不会实现点击、输入、滚动等完整 BrowserTool，也不会做元素提取、VNC 可视化、多浏览器会话或截图文件化。浏览器工具事件也暂时不进入 AI 对话时间线。这里先把 Playwright 控制 Chromium 的底层链路打通，后续第 27、28、29 章再逐步完成工具封装、远程桌面和工具预览。

## 26.5 新增和修改的文件

```Plain
.env.example
README.md
docker-compose.yml
sandbox/README.md
sandbox/Dockerfile
sandbox/pyproject.toml
sandbox/uv.lock
sandbox/app/core/config.py
sandbox/app/schemas/browser.py
sandbox/app/services/browser_service.py
sandbox/app/api/routes/browser.py
sandbox/app/api/router.py
docs/course/chapters/26-playwright-cdp.md
```

## 26.6 开始前检查：确认 Playwright 依赖
​        进入 Sandbox 目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/sandbox
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
sandbox/pyproject.toml
sandbox/uv.lock
```

​        第二条命令会下载浏览器二进制。Playwright 包只是 Python SDK，本地运行浏览器还需要 Chromium。
​        如果只做 Docker 验证，浏览器会在 `sandbox/Dockerfile` 中安装。本地安装主要用于直接运行 `uv run uvicorn app.main:app` 时验证。

## 26.7 实施步骤
### 26.7.1 补充 Sandbox 浏览器配置
​        打开 `sandbox/app/core/config.py`，在 Shell 配置后加入：

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

#### 26.7.1.1 字段含义
​        `browser_enabled` 用来控制浏览器能力是否启用。浏览器比文件和 Shell 更消耗资源，生产环境里有时需要临时关闭它，这个开关可以让 Sandbox 保持可运行，而不是因为浏览器依赖问题影响所有能力。
​        `browser_headless` 控制是否使用无头浏览器，本章默认开启；第 28 章接入 VNC 后，会继续扩展显示和远程桌面相关配置。`browser_viewport_width` 和 `browser_viewport_height` 决定页面视口大小，后续截图尺寸和元素坐标都依赖它。`browser_default_timeout_ms` 避免网页一直加载导致请求卡住，`browser_screenshot_full_page` 则决定默认截图整页还是只截当前视口。

#### 26.7.1.2 为什么这样设计
​        浏览器能力比文件和 Shell 更消耗资源。
​        配置项让浏览器能力可以被关闭，也让视口尺寸、超时时间和截图方式可以调整。后续如果浏览器截图太大、网页加载太慢，优先从这些配置排查。

### 26.7.2 定义 Browser API 模型
​        创建 `sandbox/app/schemas/browser.py`：

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

#### 26.7.2.1 代码讲解
​        这些模型是 Sandbox Browser API 和外部调用方之间的协议。
​        `BrowserStatusResponse` 用来回答“浏览器能力是否可用、是否已经启动、当前页面是什么”。这类状态后续会进入右侧工具预览或环境状态区域。
​        `BrowserNavigateRequest` 只接收 `url` 和 `wait_until`。本章不做点击和输入，因为本章目标是打通 Playwright/CDP 控制链路。
​        `BrowserScreenshotResponse` 直接返回 `base64_data`，这样用 `curl` 就能验证截图是否产生。后续截图会更适合保存成文件，再把文件 ID 交给前端展示，避免接口响应过大。

### 26.7.3 实现 BrowserService
​        创建 `sandbox/app/services/browser_service.py`：

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

#### 26.7.3.1 这段代码在流程中的位置
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

#### 26.7.3.2 关键代码逐段解释
​        `BrowserRuntime` 保存四个对象：
​        `playwright` 是 Playwright 运行时入口，负责启动和停止自动化框架。`browser` 是实际的 Chromium 浏览器进程，`context` 是隔离的浏览器上下文，`page` 是当前操作的标签页。把这四个对象放进 `BrowserRuntime`，是为了让一次启动后的浏览器会话可以跨多个请求继续使用。
​        `start()` 负责启动 Chromium。这里使用 `headless=True`，所以本章不会看到真实浏览器窗口。第 28 章接 VNC 时，会继续补显示、远程桌面和 WebSocket 代理。
​        `navigate()` 会自动补齐 URL 协议。输入 `example.com` 时，会变成 `https://example.com`。
​        `screenshot()` 返回 PNG 的 base64。这样接口验证最直接，但这不是最终形态。后续真实对话执行里，截图更适合保存到文件系统或对象存储，再在工具预览里展示。

#### 26.7.3.3 小白最容易困惑的点
​        Playwright 不是浏览器本身。
​        Playwright 是控制器，Chromium 才是浏览器。Playwright 通过 CDP 或浏览器自动化协议控制 Chromium 完成打开网页、点击、输入和截图。

### 26.7.4 新增 Browser API 路由
​        创建 `sandbox/app/api/routes/browser.py`：

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

​        打开 `sandbox/app/api/router.py`，注册路由：

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

#### 26.7.4.1 这段代码在流程中的位置
​        Browser 路由是 Sandbox 服务对外暴露的浏览器控制入口。
​        第 27 章主 API 会调用这些接口，把它们包装成 Agent 可使用的 BrowserTool。本章先不让 Agent 直接调用浏览器，是为了把浏览器运行环境和接口协议先稳定下来。

#### 26.7.4.2 为什么使用模块级 service
​        浏览器会话需要跨请求保存。
​        如果每次请求都创建新的 `SandboxBrowserService`，上一次打开的页面就会丢失，截图也无法截到刚导航的页面。
​        所以这里和 Shell 会话一样，使用模块级 service 保存进程内状态。

### 26.7.5 更新 Sandbox Dockerfile
​        打开 `sandbox/Dockerfile`，在第一次 `uv sync` 后加入：

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

#### 26.7.5.1 为什么 Dockerfile 也要安装 Chromium
​        `uv add playwright` 只安装 Python SDK。
​        容器里运行浏览器时，还需要 Chromium 二进制和系统依赖。`playwright install --with-deps chromium` 会安装这些内容。
​        这一步构建时间会明显变长，这是正常现象。

### 26.7.6 更新 Sandbox README
​        打开 `sandbox/README.md`，在接口列表中加入：

```Plain
/api/browser/status
/api/browser/session
/api/browser/page/navigate
/api/browser/page
/api/browser/page/screenshot
```

​        这份 README 是给开发时快速查接口用的，不影响运行。

## 26.8 关键理解
​        本章最重要的是理解“浏览器能力属于 Sandbox，而不是主 API”。
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
​        第三个重点是理解本章边界。
​        本章只打通浏览器控制链路，不把它直接接进 AI 对话过程。第 27 章会把这些能力包装为 BrowserTool，第 29 章会把浏览器动作和截图收敛进统一工具预览面板。

## 26.9 技术难点与亮点
​        本章的技术难点，首先是 Playwright Python 依赖和 Chromium 浏览器二进制不是一回事。安装了 Playwright SDK，并不意味着环境里已经有可启动的浏览器。Docker 容器里运行 Chromium 还需要额外系统依赖，所以 Dockerfile 中必须执行 `playwright install --with-deps chromium`。
​        第二个难点是浏览器会话需要跨请求保存。启动浏览器、导航页面、读取标题、截图，往往发生在不同请求中。如果每次请求都创建新的 service 或新的浏览器对象，就会丢失上一次打开的页面。截图直接返回 base64 虽然方便验证，但后续也要考虑响应体变大、前端展示和文件存储的问题。
​        本章的亮点，是浏览器能力正式进入 Sandbox，保持执行环境隔离。API 先稳定浏览器控制协议，第 27 章再做工具封装；`BrowserRuntime` 明确保存 Playwright、Browser、Context 和 Page 四层对象；通过 `/sandbox-api/browser/...` 可以独立验证 Playwright 控制 Chromium 的链路。

## 26.10 面试考点
​        面试里问到这一章，可以先讲 Playwright 和 Chromium 的关系。Chromium 是浏览器，Playwright 是自动化控制框架；CDP 则是浏览器暴露出来的调试与控制协议。Playwright 封装底层协议，让开发者用更稳定的 API 完成导航、截图和页面操作。
​        浏览器自动化应该放在 Sandbox 中，是因为它会启动外部进程，产生缓存、下载文件、截图和远程桌面状态。主 API 只应该编排任务，不应该直接承载这些执行细节。`Browser`、`BrowserContext` 和 `Page` 分别对应浏览器进程、隔离上下文和标签页；浏览器会话需要跨请求保存，是因为启动、导航和截图常常不是同一个请求完成。
​        Docker 中运行 Chromium 需要额外系统依赖，这一点也很容易被问到。Playwright SDK 只是控制代码，浏览器二进制和字体、图形、沙箱等依赖需要在镜像里安装，否则运行时会出现浏览器可执行文件不存在或系统库缺失的问题。

## 26.11 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 26.11.1 编译 Sandbox 代码

```Bash
cd sandbox
uv run python -m compileall app
```

### 26.11.2 本地运行 Sandbox 服务
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

### 26.11.3 Docker Compose 验证
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

## 26.12 常见问题

### 26.12.1 `BrowserType.launch: Executable doesn't exist` 怎么办？
​        这个错误说明你安装了 Playwright Python 包，但还没有安装 Chromium 浏览器二进制。本地运行时，进入 `sandbox` 目录执行 `uv run playwright install chromium`。
​        如果是在 Docker 中运行，要确认 `sandbox/Dockerfile` 已经包含 `uv run playwright install --with-deps chromium`，并重新执行 `docker compose build sandbox`。镜像没有重建时，容器里仍然没有浏览器可执行文件。

### 26.12.2 Docker 构建 Sandbox 很慢怎么办？
​        本章开始下载 Chromium 和系统依赖，构建时间明显变长是正常现象。Chromium 体积较大，系统依赖也会增加镜像构建步骤。
​        如果网络不稳定，可以稍后重试，或者先在本地用 `uv run playwright install chromium` 和 `uv run uvicorn app.main:app` 验证代码链路。等网络稳定后再重新构建 Docker 镜像。

### 26.12.3 导航网页超时怎么办？
​        导航超时可能是目标网站访问慢，也可能是当前网络无法访问目标地址。先用 `https://example.com` 验证基础链路，因为它页面简单、加载稳定，适合确认 Playwright 和 Chromium 本身是否正常。
​        如果 `example.com` 正常而目标网站失败，就把问题定位到目标网站网络、证书、加载速度或反自动化策略上，而不是先怀疑 Sandbox Browser API。

### 26.12.4 为什么截图直接返回 base64？
​        本章为了方便验证，直接把 PNG 截图编码成 base64 放在接口响应里。这样只用 `curl` 就能看到截图是否生成，也能确认浏览器链路已经打通。
​        但这不是最终形态。真实工具预览里，截图更适合写入文件系统或对象存储，再返回文件 ID 或 URL 给前端展示，避免接口响应体过大。

### 26.12.5 为什么本章没有做前端页面？
​        本章是浏览器自动化基础，重点是让 Sandbox 能启动 Chromium、导航页面、读取标题和截图。前端动作、截图预览和 VNC 远程桌面都依赖这条底层链路。
​        第 27 章会把 Browser API 封装成 BrowserTool，第 28 章会处理 VNC，第 29 章会把浏览器动作和截图收敛进真实对话执行 UI。本章先不做页面，是为了让基础协议先稳定。

## 26.13 本章小结
​        本章完成了浏览器自动化的基础链路。Sandbox 增加了 Playwright 依赖，Dockerfile 负责安装 Chromium 和系统依赖，配置层新增了浏览器开关、视口、超时和截图选项。接口层新增 Browser API 请求和响应模型，服务层新增 `SandboxBrowserService`，负责启动、关闭、导航、读取页面信息和截图。
​        通过 `/sandbox-api/browser/...`，我们已经能独立验证 Playwright 控制 Chromium 的过程。从这一章开始，Sandbox 不再只是文件和 Shell 环境，也具备了网页访问和观察能力。下一章再把这些基础接口包装成 Agent 可以调用的 BrowserTool。

## 26.14 下一章预告
​        第 27 章会把本章的 Browser API 封装成 `BrowserTool`，让 Agent 可以通过工具调用浏览器打开网页、查看页面和获取截图。
