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
