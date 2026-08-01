from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.core.exceptions import AppException


McpTransport = Literal["demo", "stdio", "sse", "streamable_http"]


# ===================== 第1步：定义单个 MCP Server 配置 =====================
class McpServerConfig(BaseModel):
    enabled: bool = True
    transport: McpTransport
    description: str = ""
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "McpServerConfig":
        """根据 transport 校验必需字段。

        stdio 需要 command，HTTP/SSE 需要 url。demo 是内置演示 Server，
        不需要额外连接信息。
        """

        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio MCP server requires command")
        if self.transport in {"sse", "streamable_http"} and not self.url:
            raise ValueError(f"{self.transport} MCP server requires url")
        return self


# ===================== 第2步：定义 MCP 总配置 =====================
class McpDefaults(BaseModel):
    enabled: bool = True
    default_server: str = "demo"


class McpConfig(BaseModel):
    mcp: McpDefaults
    servers: dict[str, McpServerConfig]


# ===================== 第3步：读取并校验 MCP 配置文件 =====================
@lru_cache
def load_mcp_config() -> McpConfig:
    """读取 MCP YAML 配置。

    第 32 章开始，MCP Server 不再写死在代码里，而是通过配置声明。
    这样后续新增外部 Server 时，只需要改配置和重启 API。
    """

    path = Path(settings.mcp_config_path)
    if not path.is_file():
        path = Path("config/mcp.yaml")
    if not path.is_file():
        raise AppException(
            message=f"MCP config file not found: {settings.mcp_config_path}",
            code=500,
            status_code=500,
        )

    raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = McpConfig.model_validate(raw_config)
    if config.mcp.default_server not in config.servers:
        raise AppException(
            message="default MCP server is not defined",
            code=500,
            status_code=500,
        )
    return config
