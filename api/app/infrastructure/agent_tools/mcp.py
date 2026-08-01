import json
from typing import Any

from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)
from app.domain.mcp.entities import McpToolResult
from app.application.mcp_service import McpService


def register_mcp_tools(
    registry: ToolRegistry,
    service: McpService | None = None,
) -> None:
    """把 MCP 工具调用入口注册成 AgentTool。

    第 32 章先注册一个通用 `mcp_call`。它通过 server_name + tool_name
    调用外部 MCP 工具。第 39 章模型工具选择增强时，可以把动态发现到的
    MCP 工具展开成更细粒度的工具 schema。
    """

    mcp_service = service or McpService()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="mcp_call",
                description="调用一个已配置 MCP Server 暴露的工具。",
                risk_level=ToolRiskLevel.high,
                required_permissions=("integration:mcp",),
                idempotent=False,
                parameters=[
                    ToolParameter(
                        name="server_name",
                        type="string",
                        description="MCP Server 名称，例如 demo。",
                    ),
                    ToolParameter(
                        name="tool_name",
                        type="string",
                        description="MCP 工具名，例如 mcp_echo。",
                    ),
                    ToolParameter(
                        name="arguments_json",
                        type="string",
                        description="工具参数 JSON 字符串。",
                        required=False,
                    ),
                ],
            ),
            handler=lambda server_name, tool_name, arguments_json="{}": _format_mcp_result(
                mcp_service.call_tool(
                    server_name=str(server_name),
                    tool_name=str(tool_name),
                    arguments=_parse_arguments(arguments_json),
                )
            ),
        )
    )


def _parse_arguments(value: object) -> dict[str, Any]:
    """把 AgentTool 字符串参数转换成 MCP 工具参数字典。"""

    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _format_mcp_result(result: McpToolResult) -> str:
    """把 MCP 工具结果格式化成前端工具预览面板可识别的 JSON。"""

    return json.dumps(
        {
            "kind": "mcp_tool_result",
            "server_name": result.server_name,
            "tool_name": result.tool_name,
            "arguments": result.arguments,
            "content": result.content,
        },
        ensure_ascii=False,
    )
