from typing import Any

from pydantic import BaseModel, Field


# ===================== 第1步：MCP 角色和能力说明 =====================
class McpRoleResponse(BaseModel):
    name: str  # Host、Client 或 Server。
    responsibility: str  # 这个角色在 MCP 架构中负责什么。
    example: str  # 在 AtlasAgent 项目中可以类比到哪里。


class McpCapabilityResponse(BaseModel):
    name: str  # tools、resources 或 prompts。
    description: str  # 这类能力解决什么问题。
    system_mapping: str  # 和当前项目已有模块的对应关系。


class McpConceptsResponse(BaseModel):
    roles: list[McpRoleResponse]
    capabilities: list[McpCapabilityResponse]
    transports: list[str]  # 第 31 章只解释名称，第 32 章再实现真实连接。
    protocol: str  # MCP 数据层使用的协议说明。


# ===================== 第2步：MCP 工具发现响应 =====================
class McpToolDemoResponse(BaseModel):
    name: str  # 模拟 MCP Server 暴露的工具名。
    description: str  # 工具用途说明。
    input_schema: dict[str, Any]  # MCP tools/list 中常见的 JSON Schema。


class McpToolListResponse(BaseModel):
    items: list[McpToolDemoResponse]


# ===================== 第3步：MCP 工具调用请求和响应 =====================
class McpToolCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpCallStepResponse(BaseModel):
    index: int  # 调用流程中的第几步。
    action: str  # 例如 tools/list、tools/call。
    detail: str  # 对这一步发生了什么的解释。


class McpToolCallResponse(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, str]]  # MCP 工具结果通常用 content 数组承载。
    steps: list[McpCallStepResponse]


# ===================== 第4步：第 32 章真实 MCP 配置和工具响应 =====================
class McpServerResponse(BaseModel):
    name: str  # 配置文件中的 server 名称。
    enabled: bool  # 是否启用该 Server。
    transport: str  # demo、stdio、sse 或 streamable_http。
    description: str  # 给前端和排查时看的说明。


class McpServerListResponse(BaseModel):
    items: list[McpServerResponse]


class McpDiscoveredToolResponse(BaseModel):
    server_name: str  # 工具来自哪个 MCP Server。
    name: str  # MCP 工具名。
    description: str  # MCP Server 返回的工具说明。
    input_schema: dict[str, Any]  # MCP 工具参数 JSON Schema。


class McpDiscoveredToolListResponse(BaseModel):
    items: list[McpDiscoveredToolResponse]


class McpToolInvokeRequest(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpToolInvokeResponse(BaseModel):
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, Any]]
