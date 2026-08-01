from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.core.exceptions import AppException


A2aTransport = Literal["demo", "http"]


# ===================== 第1步：定义远程 Agent 能力配置 =====================
class A2aCapabilityConfig(BaseModel):
    """远程 Agent 在 Agent Card 中声明的一项能力。"""

    name: str
    description: str = ""
    input_modes: list[str] = Field(default_factory=lambda: ["text"])
    output_modes: list[str] = Field(default_factory=lambda: ["text"])


# ===================== 第2步：定义单个远程 Agent 配置 =====================
class A2aAgentConfig(BaseModel):
    """一个可被 Host Agent 调用的远程 Agent 配置。"""

    enabled: bool = True
    transport: A2aTransport
    name: str
    description: str = ""
    url: str
    version: str = "0.1.0"
    timeout_seconds: float = Field(default=10.0, gt=0)
    capabilities: list[A2aCapabilityConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "A2aAgentConfig":
        """根据 transport 校验必需字段。

        demo 使用内置实现，url 只作为展示字段。http 需要真实远程地址，
        第 35 章先约定远程 Agent 暴露 /agent-card 和 /message/send 两个接口。
        """

        if self.transport == "http" and not self.url.startswith(("http://", "https://")):
            raise ValueError("http A2A agent requires http or https url")
        return self


# ===================== 第3步：定义 A2A 总配置 =====================
class A2aDefaults(BaseModel):
    enabled: bool = True
    default_agent: str = "demo_researcher"


class A2aConfig(BaseModel):
    a2a: A2aDefaults
    agents: dict[str, A2aAgentConfig]


# ===================== 第4步：读取并校验 A2A 配置文件 =====================
@lru_cache
def load_a2a_config() -> A2aConfig:
    """读取 A2A YAML 配置。

    这样新增远程 Agent 时，只需要修改配置文件并重启 API。
    工具注册、路由和前端面板都可以从同一份配置中读取能力。
    """

    path = Path(settings.a2a_config_path)
    if not path.is_file():
        path = Path("config/a2a.yaml")
    if not path.is_file():
        raise AppException(
            message=f"A2A config file not found: {settings.a2a_config_path}",
            code=500,
            status_code=500,
        )

    raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = A2aConfig.model_validate(raw_config)
    if config.a2a.default_agent not in config.agents:
        raise AppException(
            message="default A2A agent is not defined",
            code=500,
            status_code=500,
        )
    return config
