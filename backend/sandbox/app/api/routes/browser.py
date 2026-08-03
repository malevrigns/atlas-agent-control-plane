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
