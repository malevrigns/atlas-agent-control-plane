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

    # ===================== 第5步：内部辅助方法 =====================
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
