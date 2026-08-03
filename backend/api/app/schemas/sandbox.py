from pydantic import BaseModel, Field


class SandboxInstanceResponse(BaseModel):
    id: str  # 主 API 识别当前沙箱实例的稳定 ID。
    name: str  # Docker Compose 中的沙箱容器名。
    base_url: str  # 主 API 访问 Sandbox 服务的 API 地址。
    status: str  # ready、unavailable、released 等状态。
    message: str  # 给前端展示的状态说明。


class SandboxWaitRequest(BaseModel):
    retries: int | None = Field(default=None, ge=1)  # 覆盖默认重试次数，用于前端手动刷新。
    interval_seconds: float | None = Field(default=None, gt=0)  # 覆盖默认重试间隔。


class SandboxFileReadResponse(BaseModel):
    path: str  # 相对 workspace 的文件路径。
    content: str  # 文件文本内容，后续可进入工具预览或上下文工程。
    size: int  # 文件真实字节数。
    truncated: bool  # true 表示内容被 Sandbox 读取上限裁剪。


class SandboxFileWriteRequest(BaseModel):
    path: str = Field(min_length=1)  # 要写入的相对路径。
    content: str  # 写入的文本内容。
    create_parent: bool = True  # 父目录不存在时是否自动创建。


class SandboxFileWriteResponse(BaseModel):
    path: str  # 写入成功的相对路径。
    size: int  # 写入后的文件字节数。


class SandboxShellRunRequest(BaseModel):
    command: str = Field(min_length=1)  # 要在当前沙箱中执行的命令。
    cwd: str = "."  # 相对 workspace 的命令工作目录。
    timeout_seconds: float | None = None  # 本次等待命令完成的最大时间。


class SandboxShellRunResponse(BaseModel):
    id: str  # Shell 会话 ID，可用于后续查询。
    command: str  # 实际执行的命令。
    cwd: str  # 实际执行命令的相对目录。
    status: str  # running、succeeded、failed 或 terminated。
    return_code: int | None  # 进程退出码；命令未结束时为空。
    output: str  # 命令输出，前端工具预览面板会展示它。
    output_truncated: bool  # true 表示输出被 Sandbox 裁剪。
