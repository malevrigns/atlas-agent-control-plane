from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class McpServerInfo:
    """一个可用或可配置的 MCP Server。"""

    name: str
    enabled: bool
    transport: str
    description: str


@dataclass(slots=True)
class McpTool:
    """从 MCP Server 发现到的工具描述。"""

    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class McpToolResult:
    """一次 MCP 工具调用的统一结果。"""

    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, Any]]

