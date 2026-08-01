from fastapi import APIRouter, Depends

from app.application.mcp_intro_service import (
    McpCapability,
    McpCallStep,
    McpIntroService,
    McpRole,
    McpToolCallDemo,
    McpToolDemo,
)
from app.application.mcp_service import McpService
from app.domain.mcp.entities import McpServerInfo, McpTool, McpToolResult
from app.schemas.common import ApiResponse
from app.schemas.mcp import (
    McpCallStepResponse,
    McpCapabilityResponse,
    McpConceptsResponse,
    McpDiscoveredToolListResponse,
    McpDiscoveredToolResponse,
    McpServerListResponse,
    McpServerResponse,
    McpRoleResponse,
    McpToolCallRequest,
    McpToolCallResponse,
    McpToolDemoResponse,
    McpToolInvokeRequest,
    McpToolInvokeResponse,
    McpToolListResponse,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ===================== 第1步：创建 MCP 入门应用服务 =====================
def build_mcp_intro_service() -> McpIntroService:
    """创建第 31 章的 MCP 入门服务。

    当前服务只返回确定性演示数据，不需要数据库连接和外部 MCP 进程。
    第 32 章接入真实 MCP Client 时，会在这里注入配置和连接管理器。
    """

    return McpIntroService()


def build_mcp_service() -> McpService:
    """创建第 32 章真实 MCP 工具接入服务。"""

    return McpService()


# ===================== 第2步：领域对象转换为 API 响应 =====================
def to_role_response(role: McpRole) -> McpRoleResponse:
    return McpRoleResponse(
        name=role.name,
        responsibility=role.responsibility,
        example=role.example,
    )


def to_capability_response(capability: McpCapability) -> McpCapabilityResponse:
    return McpCapabilityResponse(
        name=capability.name,
        description=capability.description,
        system_mapping=capability.system_mapping,
    )


def to_tool_response(tool: McpToolDemo) -> McpToolDemoResponse:
    return McpToolDemoResponse(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
    )


def to_step_response(step: McpCallStep) -> McpCallStepResponse:
    return McpCallStepResponse(
        index=step.index,
        action=step.action,
        detail=step.detail,
    )


def to_call_response(demo: McpToolCallDemo) -> McpToolCallResponse:
    return McpToolCallResponse(
        tool_name=demo.tool_name,
        arguments=demo.arguments,
        content=demo.content,
        steps=[to_step_response(step) for step in demo.steps],
    )


def to_server_response(server: McpServerInfo) -> McpServerResponse:
    return McpServerResponse(
        name=server.name,
        enabled=server.enabled,
        transport=server.transport,
        description=server.description,
    )


def to_discovered_tool_response(tool: McpTool) -> McpDiscoveredToolResponse:
    return McpDiscoveredToolResponse(
        server_name=tool.server_name,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
    )


def to_invoke_response(result: McpToolResult) -> McpToolInvokeResponse:
    return McpToolInvokeResponse(
        server_name=result.server_name,
        tool_name=result.tool_name,
        arguments=result.arguments,
        content=result.content,
    )


# ===================== 第3步：MCP 概念说明接口 =====================
@router.get("/concepts", response_model=ApiResponse[McpConceptsResponse])
async def get_mcp_concepts(
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpConceptsResponse]:
    """返回 Host、Client、Server 和 MCP 能力类型说明。"""

    return ApiResponse(
        data=McpConceptsResponse(
            roles=[to_role_response(role) for role in service.list_roles()],
            capabilities=[
                to_capability_response(capability)
                for capability in service.list_capabilities()
            ],
            transports=["stdio", "Streamable HTTP"],
            protocol="JSON-RPC 2.0 message format",
        )
    )


# ===================== 第4步：模拟 MCP tools/list =====================
@router.get("/demo/tools", response_model=ApiResponse[McpToolListResponse])
async def list_mcp_demo_tools(
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpToolListResponse]:
    """模拟 MCP Client 向 Server 发起 tools/list 后拿到的工具列表。"""

    return ApiResponse(
        data=McpToolListResponse(
            items=[to_tool_response(tool) for tool in service.list_demo_tools()],
        )
    )


# ===================== 第5步：模拟 MCP tools/call =====================
@router.post("/demo/call", response_model=ApiResponse[McpToolCallResponse])
async def call_mcp_demo_tool(
    payload: McpToolCallRequest,
    service: McpIntroService = Depends(build_mcp_intro_service),
) -> ApiResponse[McpToolCallResponse]:
    """模拟一次 MCP tools/call 调用流程。"""

    demo = service.call_demo_tool(
        tool_name=payload.tool_name,
        arguments=payload.arguments,
    )
    return ApiResponse(data=to_call_response(demo))


# ===================== 第6步：真实 MCP Server 配置列表 =====================
@router.get("/servers", response_model=ApiResponse[McpServerListResponse])
async def list_mcp_servers(
    service: McpService = Depends(build_mcp_service),
) -> ApiResponse[McpServerListResponse]:
    """返回配置文件中的 MCP Server 列表。"""

    return ApiResponse(
        data=McpServerListResponse(
            items=[to_server_response(server) for server in service.list_servers()],
        )
    )


# ===================== 第7步：真实 MCP 工具发现 =====================
@router.get("/tools", response_model=ApiResponse[McpDiscoveredToolListResponse])
async def list_mcp_tools(
    server_name: str | None = None,
    service: McpService = Depends(build_mcp_service),
) -> ApiResponse[McpDiscoveredToolListResponse]:
    """读取一个或全部已启用 MCP Server 暴露的工具。"""

    return ApiResponse(
        data=McpDiscoveredToolListResponse(
            items=[
                to_discovered_tool_response(tool)
                for tool in service.list_tools(server_name=server_name)
            ],
        )
    )


# ===================== 第8步：真实 MCP 工具调用 =====================
@router.post("/call", response_model=ApiResponse[McpToolInvokeResponse])
async def call_mcp_tool(
    payload: McpToolInvokeRequest,
    service: McpService = Depends(build_mcp_service),
) -> ApiResponse[McpToolInvokeResponse]:
    """调用已配置 MCP Server 上的工具。"""

    result = service.call_tool(
        server_name=payload.server_name,
        tool_name=payload.tool_name,
        arguments=payload.arguments,
    )
    return ApiResponse(data=to_invoke_response(result))
