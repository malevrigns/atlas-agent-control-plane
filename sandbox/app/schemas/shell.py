from pydantic import BaseModel, Field


class ShellExecuteRequest(BaseModel):
    command: str = Field(min_length=1)  # 要在沙箱中执行的命令。
    cwd: str = "."  # 相对 workspace 的工作目录，避免暴露容器真实路径。


class ShellWriteRequest(BaseModel):
    input: str  # 写入进程 stdin 的内容，通常用于交互式命令。


class ShellWaitRequest(BaseModel):
    timeout_seconds: float | None = None  # 本次等待多久；为空时使用配置默认值。


class ShellSessionResponse(BaseModel):
    id: str  # Shell 会话 ID，后续读取、等待、写入、终止都用它。
    command: str  # 启动会话时执行的原始命令。
    cwd: str  # 命令所在的相对工作目录。
    status: str  # running、succeeded、failed、terminated 中的一种。
    return_code: int | None  # 进程退出码；运行中时为 null。
    output: str  # 已收集的 stdout 和 stderr。
    output_truncated: bool  # 输出是否因为超过限制被裁剪。


class ShellSessionListResponse(BaseModel):
    items: list[ShellSessionResponse]  # 当前沙箱内仍然记录的 Shell 会话。


class ShellWriteResponse(BaseModel):
    id: str  # 被写入的 Shell 会话 ID。
    written: int  # 写入 stdin 的字节数。


class ShellTerminateResponse(BaseModel):
    id: str  # 被终止的 Shell 会话 ID。
    terminated: bool  # 成功发出终止信号时为 true。
