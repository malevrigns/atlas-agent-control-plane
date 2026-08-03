from pydantic import BaseModel


class VncStatusResponse(BaseModel):
    enabled: bool  # 是否启用 VNC/noVNC 能力。
    display: str  # Xvfb 使用的虚拟显示器编号，例如 :99。
    vnc_port: int  # x11vnc 在容器内监听的原生 VNC 端口。
    web_port: int  # websockify/noVNC 在容器内监听的 Web 端口。
    iframe_path: str  # 前端 iframe 直接打开的网关路径。
    websocket_path: str  # noVNC 连接 websockify 时使用的 WebSocket 路径。
    message: str  # 给前端展示的状态说明。
