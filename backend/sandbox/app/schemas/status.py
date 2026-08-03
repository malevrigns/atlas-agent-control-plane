from pydantic import BaseModel


class SandboxStatusResponse(BaseModel):
    service: str  # 确认当前访问的是 Sandbox 服务，而不是主 API。
    environment: str  # 当前运行环境，例如 development。
    status: str  # 健康状态，本章正常时固定返回 ok。
    version: str  # 沙箱服务版本，方便排查镜像是否更新。
    workspace_dir: str  # 沙箱工作目录，后续文件和 Shell 都围绕它运行。
