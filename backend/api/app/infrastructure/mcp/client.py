import json
import subprocess
from abc import ABC, abstractmethod
from itertools import count
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.mcp_config import McpServerConfig, load_mcp_config
from app.domain.mcp.entities import McpServerInfo, McpTool, McpToolResult


_json_rpc_ids = count(1)


class McpTransportClient(ABC):
    """MCP 传输层客户端基类。

    第 32 章先把传输层抽象出来。上层应用服务只关心 list_tools 和
    call_tool，不关心底层是内置 demo、stdio 还是 Streamable HTTP。
    """

    def __init__(self, server_name: str, config: McpServerConfig) -> None:
        self.server_name = server_name
        self.config = config

    @abstractmethod
    def list_tools(self) -> list[McpTool]:
        """读取当前 Server 暴露的工具列表。"""

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        """调用当前 Server 上的一个工具。"""


class DemoMcpTransportClient(McpTransportClient):
    """内置 MCP 演示传输。

    它模拟真实 MCP Server 的 tools/list 和 tools/call 响应，
    但不需要启动外部进程，适合本章稳定验证完整链路。
    """

    def list_tools(self) -> list[McpTool]:
        return [
            McpTool(
                server_name=self.server_name,
                name="mcp_echo",
                description="返回调用方传入的文本。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "需要原样返回的文本。",
                        }
                    },
                    "required": ["text"],
                },
            ),
            McpTool(
                server_name=self.server_name,
                name="mcp_add_note",
                description="模拟创建一条外部笔记。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "笔记标题。"},
                        "content": {"type": "string", "description": "笔记正文。"},
                    },
                    "required": ["title", "content"],
                },
            ),
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        tool_names = {tool.name for tool in self.list_tools()}
        if tool_name not in tool_names:
            raise AppException(
                message=f"MCP tool not found: {self.server_name}.{tool_name}",
                code=404,
                status_code=404,
            )

        if tool_name == "mcp_echo":
            text = str(arguments.get("text") or "")
            if not text:
                raise AppException(
                    message="argument is required: text",
                    code=400,
                    status_code=400,
                )
            content: list[dict[str, Any]] = [{"type": "text", "text": f"echo: {text}"}]
        else:
            title = str(arguments.get("title") or "")
            body = str(arguments.get("content") or "")
            if not title or not body:
                raise AppException(
                    message="arguments are required: title, content",
                    code=400,
                    status_code=400,
                )
            content = [{"type": "text", "text": f"note created: {title}"}]

        return McpToolResult(
            server_name=self.server_name,
            tool_name=tool_name,
            arguments=arguments,
            content=content,
        )


class StreamableHttpMcpTransportClient(McpTransportClient):
    """最小 Streamable HTTP MCP 客户端。

    真实 MCP Server 可能还有初始化、会话和通知等细节。本章先实现
    `tools/list` 和 `tools/call` 两个最关键请求，让项目具备扩展点。
    """

    def list_tools(self) -> list[McpTool]:
        result = self._send_json_rpc("tools/list", {})
        tools = result.get("tools", [])
        return [
            McpTool(
                server_name=self.server_name,
                name=str(tool.get("name") or ""),
                description=str(tool.get("description") or ""),
                input_schema=dict(tool.get("inputSchema") or {}),
            )
            for tool in tools
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        result = self._send_json_rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return McpToolResult(
            server_name=self.server_name,
            tool_name=tool_name,
            arguments=arguments,
            content=list(result.get("content") or []),
        )

    def _send_json_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_body = {
            "jsonrpc": "2.0",
            "id": next(_json_rpc_ids),
            "method": method,
            "params": params,
        }
        try:
            response = httpx.post(
                str(self.config.url),
                json=request_body,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"MCP HTTP request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        payload = response.json()
        if payload.get("error"):
            raise AppException(
                message=f"MCP JSON-RPC error: {payload['error']}",
                code=502,
                status_code=502,
            )
        result = payload.get("result")
        return result if isinstance(result, dict) else {}


class StdioMcpTransportClient(McpTransportClient):
    """最小 stdio MCP 客户端。

    每次调用都会启动一次命令，写入一条 JSON-RPC 请求，并读取一行响应。
    这种方式适合课程理解协议，不适合长连接生产场景；生产连接管理会在后续加强。
    """

    def list_tools(self) -> list[McpTool]:
        result = self._send_json_rpc("tools/list", {})
        return [
            McpTool(
                server_name=self.server_name,
                name=str(tool.get("name") or ""),
                description=str(tool.get("description") or ""),
                input_schema=dict(tool.get("inputSchema") or {}),
            )
            for tool in result.get("tools", [])
        ]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        result = self._send_json_rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return McpToolResult(
            server_name=self.server_name,
            tool_name=tool_name,
            arguments=arguments,
            content=list(result.get("content") or []),
        )

    def _send_json_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.config.command:
            raise AppException(
                message=f"MCP stdio command is missing: {self.server_name}",
                code=500,
                status_code=500,
            )

        request_body = {
            "jsonrpc": "2.0",
            "id": next(_json_rpc_ids),
            "method": method,
            "params": params,
        }
        command = [self.config.command, *self.config.args]
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(request_body, ensure_ascii=False) + "\n",
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=self.config.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AppException(
                message=f"MCP stdio request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        if completed.returncode != 0:
            raise AppException(
                message=f"MCP stdio server exited: {completed.stderr.strip()}",
                code=502,
                status_code=502,
            )

        first_line = completed.stdout.splitlines()[0] if completed.stdout else "{}"
        payload = json.loads(first_line)
        if payload.get("error"):
            raise AppException(
                message=f"MCP JSON-RPC error: {payload['error']}",
                code=502,
                status_code=502,
            )
        result = payload.get("result")
        return result if isinstance(result, dict) else {}


class SseMcpTransportClient(StreamableHttpMcpTransportClient):
    """SSE MCP 配置占位。

    早期 MCP SSE 传输需要先建立事件流，再通过服务端返回的消息端点发送
    JSON-RPC 请求。第 32 章先识别该配置并返回清晰错误，避免假装支持完整生命周期。
    """

    def _send_json_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise AppException(
            message="MCP SSE transport requires long-lived session management; use streamable_http or demo in this chapter.",
            code=501,
            status_code=501,
        )


class McpClientManager:
    """MCP Client 管理器。

    它读取 MCP 配置，按 server_name 创建对应传输客户端，
    并向应用服务提供统一的 list_tools / call_tool 方法。
    """

    def __init__(self) -> None:
        self.config = load_mcp_config()

    def list_servers(self) -> list[McpServerInfo]:
        return [
            McpServerInfo(
                name=name,
                enabled=server.enabled,
                transport=server.transport,
                description=server.description,
            )
            for name, server in self.config.servers.items()
        ]

    def list_tools(self, server_name: str | None = None) -> list[McpTool]:
        server_names = (
            [server_name]
            if server_name
            else [
                name
                for name, server in self.config.servers.items()
                if server.enabled
            ]
        )
        tools: list[McpTool] = []
        for name in server_names:
            server = self._get_enabled_server(name)
            tools.extend(self._build_transport(name, server).list_tools())
        return tools

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpToolResult:
        server = self._get_enabled_server(server_name)
        return self._build_transport(server_name, server).call_tool(tool_name, arguments)

    def _get_enabled_server(self, server_name: str) -> McpServerConfig:
        server = self.config.servers.get(server_name)
        if server is None:
            raise AppException(
                message=f"MCP server not found: {server_name}",
                code=404,
                status_code=404,
            )
        if not server.enabled:
            raise AppException(
                message=f"MCP server is disabled: {server_name}",
                code=400,
                status_code=400,
            )
        return server

    def _build_transport(
        self,
        server_name: str,
        server: McpServerConfig,
    ) -> McpTransportClient:
        if server.transport == "demo":
            return DemoMcpTransportClient(server_name, server)
        if server.transport == "stdio":
            return StdioMcpTransportClient(server_name, server)
        if server.transport == "streamable_http":
            return StreamableHttpMcpTransportClient(server_name, server)
        if server.transport == "sse":
            return SseMcpTransportClient(server_name, server)
        raise AppException(
            message=f"unsupported MCP transport: {server.transport}",
            code=500,
            status_code=500,
        )


def build_mcp_client_manager() -> McpClientManager:
    return McpClientManager()
