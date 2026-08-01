from pydantic import BaseModel


class SupervisorServiceResponse(BaseModel):
    name: str  # 被 Supervisor 管理的进程名，例如 sandbox-api、chrome。
    status: str  # 进程状态，本章可能是 not_configured 或 unavailable。
    description: str  # 状态说明，帮助调用方理解为什么不是 running。


class SupervisorStatusResponse(BaseModel):
    enabled: bool  # 是否启用真实 supervisorctl 状态读取。
    services: list[SupervisorServiceResponse]  # 当前沙箱关注的进程状态列表。
