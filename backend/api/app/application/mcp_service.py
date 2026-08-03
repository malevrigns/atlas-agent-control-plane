from typing import Any

from app.domain.mcp.entities import McpServerInfo, McpTool, McpToolResult
from app.infrastructure.mcp.client import McpClientManager, build_mcp_client_manager


class McpService:
    """真实 MCP 工具接入的应用服务。

    第 31 章只做概念演示；第 32 章开始，这个服务负责读取 MCP 配置、
    发现 MCP 工具，并把工具调用结果返回给 API 路由和 AgentTool。
    """

    def __init__(self, manager: McpClientManager | None = None) -> None:
        # 1. manager 负责传输层细节，service 负责应用层语义。
        self.manager = manager or build_mcp_client_manager()

    # ===================== 第1步：读取 MCP Server 配置状态 =====================
    def list_servers(self) -> list[McpServerInfo]:
        """返回所有配置过的 MCP Server。"""

        return self.manager.list_servers()

    # ===================== 第2步：发现 MCP 工具 =====================
    def list_tools(self, server_name: str | None = None) -> list[McpTool]:
        """读取某个 Server 或全部 Server 暴露的工具。"""

        return self.manager.list_tools(server_name=server_name)

    # ===================== 第3步：调用 MCP 工具 =====================
    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolResult:
        """调用指定 MCP Server 上的指定工具。"""

        return self.manager.call_tool(
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
        )

