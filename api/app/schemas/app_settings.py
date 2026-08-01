from typing import Literal

from pydantic import BaseModel, Field


SettingsIntegrationKind = Literal[
    "llm",
    "search",
    "mcp",
    "a2a",
    "multi_agent",
    "sandbox",
]


class SettingsItemResponse(BaseModel):
    name: str  # 配置项名称，例如 provider name、MCP server name 或 Agent key。
    description: str  # 配置项说明，前端设置页直接展示。
    enabled: bool  # 当前配置项是否可用。
    metadata: dict[str, object]  # 额外信息，例如 transport、url、api_key_env。


class SettingsModuleResponse(BaseModel):
    key: str  # 模块稳定标识，例如 llm、mcp、a2a、multi_agent。
    name: str  # 展示名称。
    description: str  # 模块作用说明。
    enabled: bool  # 设置页中的运行时启用状态。
    default_item: str | None  # 当前默认项，例如默认 provider 或默认远程 Agent。
    items: list[SettingsItemResponse]  # 模块下的配置项列表。
    status: str  # ready、warning 或 disabled，用于前端展示集成健康状态。
    status_message: str  # 给用户看的状态说明，例如密钥未配置或工具已启用。
    source: str  # 配置来源，例如 .env、config/llm.yaml 或 docker-compose.yml。
    verify_command: str  # 可以复制执行的验证命令。


class SettingsIntegrationResponse(BaseModel):
    id: str  # 运行时集成记录 ID。
    kind: SettingsIntegrationKind  # 集成类型。
    name: str  # 集成名称。
    description: str  # 集成说明。
    endpoint: str | None  # 外部服务地址，某些集成可以为空。
    enabled: bool  # 当前记录是否启用。


class AppSettingsResponse(BaseModel):
    modules: list[SettingsModuleResponse]
    integrations: list[SettingsIntegrationResponse]


class SettingsModuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    default_item: str | None = Field(default=None, max_length=120)


class SettingsIntegrationCreateRequest(BaseModel):
    kind: SettingsIntegrationKind
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=8000)
    endpoint: str | None = Field(default=None, max_length=1000)


class SettingsItemUpdateRequest(BaseModel):
    enabled: bool
