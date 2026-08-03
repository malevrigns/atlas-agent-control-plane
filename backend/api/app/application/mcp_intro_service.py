from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppException


@dataclass(slots=True)
class McpRole:
    """MCP 架构中的一个角色。

    name 是角色名称，responsibility 描述它负责什么，
    example 用本项目里的对象帮助理解这个角色会落在哪里。
    """

    name: str
    responsibility: str
    example: str


@dataclass(slots=True)
class McpCapability:
    """MCP Server 对外暴露的一类能力。"""

    name: str
    description: str
    system_mapping: str


@dataclass(slots=True)
class McpToolDemo:
    """第 31 章用来模拟 MCP tools/list 的工具描述。"""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class McpCallStep:
    """一次 MCP 工具调用流程中的可观察步骤。"""

    index: int
    action: str
    detail: str


@dataclass(slots=True)
class McpToolCallDemo:
    """一次模拟 MCP tools/call 的结果。"""

    tool_name: str
    arguments: dict[str, Any]
    content: list[dict[str, str]]
    steps: list[McpCallStep]


class McpIntroService:
    """第 31 章的 MCP 入门应用服务。

    这一章不启动真实 MCP Server，也不连接 stdio 或 Streamable HTTP。
    这里用确定性数据模拟 MCP 的工具发现和工具调用流程，
    让读者先理解 Host、Client、Server、tools/list、tools/call 的关系。
    """

    # ===================== 第1步：返回 MCP 架构角色 =====================
    def list_roles(self) -> list[McpRole]:
        """解释 Host、Client、Server 在项目中的位置。"""

        return [
            McpRole(
                name="Host",
                responsibility="承载 AI 应用，负责组织对话、上下文和工具调用决策。",
                example="AtlasAgent 的主 API 和前端工作台共同组成 Host 体验。",
            ),
            McpRole(
                name="Client",
                responsibility="由 Host 创建，负责和某一个 MCP Server 建立连接并发送协议请求。",
                example="第 32 章会在主 API 中实现 MCP Client 适配层。",
            ),
            McpRole(
                name="Server",
                responsibility="对外暴露 tools、resources、prompts 等能力。",
                example="文件系统 MCP Server、浏览器 MCP Server 或第三方业务 MCP Server。",
            ),
        ]

    # ===================== 第2步：返回 MCP 能力类型 =====================
    def list_capabilities(self) -> list[McpCapability]:
        """解释 MCP Server 通常能暴露哪些能力。"""

        return [
            McpCapability(
                name="tools",
                description="可被模型或 Agent 调用的动作，例如搜索、读文件、创建工单。",
                system_mapping="对应当前项目里的 AgentTool 和 tool_called 事件。",
            ),
            McpCapability(
                name="resources",
                description="可读取的上下文资源，例如文件、数据库记录、网页内容。",
                system_mapping="对应上下文工程中的文件引用、消息摘要和外部资料。",
            ),
            McpCapability(
                name="prompts",
                description="Server 提供的提示词模板，帮助 Host 生成更稳定的任务输入。",
                system_mapping="后续可用于预置任务模板、工具使用说明和业务流程提示词。",
            ),
        ]

    # ===================== 第3步：模拟 tools/list 工具发现 =====================
    def list_demo_tools(self) -> list[McpToolDemo]:
        """返回一个本地模拟 MCP Server 暴露的工具列表。"""

        return [
            McpToolDemo(
                name="mcp_echo",
                description="返回调用方传入的文本，用来观察 MCP tools/call 的参数流动。",
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
            McpToolDemo(
                name="mcp_add_note",
                description="模拟把一条笔记写入外部系统，并返回笔记摘要。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "笔记标题。",
                        },
                        "content": {
                            "type": "string",
                            "description": "笔记正文。",
                        },
                    },
                    "required": ["title", "content"],
                },
            ),
        ]

    # ===================== 第4步：模拟 tools/call 工具调用 =====================
    def call_demo_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolCallDemo:
        """根据工具名模拟一次 MCP 工具调用。"""

        tool_names = {tool.name for tool in self.list_demo_tools()}
        if tool_name not in tool_names:
            raise AppException(
                message=f"mcp demo tool not found: {tool_name}",
                code=404,
                status_code=404,
            )

        steps = [
            McpCallStep(
                index=1,
                action="tools/list",
                detail="Host 先通过 MCP Client 向 Server 获取可用工具列表。",
            ),
            McpCallStep(
                index=2,
                action="tool selection",
                detail=f"Agent 根据任务选择工具 {tool_name}，并整理调用参数。",
            ),
            McpCallStep(
                index=3,
                action="tools/call",
                detail="MCP Client 把工具名和参数发送给 MCP Server。",
            ),
            McpCallStep(
                index=4,
                action="content response",
                detail="MCP Server 返回 content 数组，Host 再把结果写入工具事件。",
            ),
        ]

        if tool_name == "mcp_echo":
            text = str(arguments.get("text") or "")
            if not text:
                raise AppException(
                    message="argument is required: text",
                    code=400,
                    status_code=400,
                )
            content = [{"type": "text", "text": f"echo: {text}"}]
        else:
            title = str(arguments.get("title") or "")
            body = str(arguments.get("content") or "")
            if not title or not body:
                raise AppException(
                    message="arguments are required: title, content",
                    code=400,
                    status_code=400,
                )
            content = [
                {
                    "type": "text",
                    "text": f"note created: {title} ({len(body)} chars)",
                }
            ]

        return McpToolCallDemo(
            tool_name=tool_name,
            arguments=arguments,
            content=content,
            steps=steps,
        )

