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
