from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agent_core_service import AgentCoreService
from app.application.llm_service import LLMService
from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.application.unit_of_work import UnitOfWork
from app.domain.agent_core.memory import MemoryMessage
from app.domain.agent_core.tools import ToolCallResult, ToolDefinition, ToolParameter
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry
from app.infrastructure.database.session import get_db_session
from app.schemas.agent_core import (
    AgentCoreDemoRequest,
    AgentCoreDemoResponse,
    MemoryMessageResponse,
    ToolCallResultResponse,
    ToolDefinitionResponse,
    ToolListResponse,
    ToolParameterResponse,
    ToolInvokeRequest,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/agent-core", tags=["agent-core"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_agent_core_service() -> AgentCoreService:
    """创建 AgentCoreService。

    当前服务只依赖内置工具注册表，不需要数据库连接。
    """

    model = LLMService()
    return AgentCoreService(build_builtin_tool_registry(content_model=model))


# ===================== 第2步：把领域对象转换成接口响应 =====================
def to_parameter_response(parameter: ToolParameter) -> ToolParameterResponse:
    return ToolParameterResponse(
        name=parameter.name,
        type=parameter.type,
        description=parameter.description,
        required=parameter.required,
    )


def to_tool_response(definition: ToolDefinition) -> ToolDefinitionResponse:
    return ToolDefinitionResponse(
        name=definition.name,
        description=definition.description,
        parameters=[
            to_parameter_response(parameter)
            for parameter in definition.parameters
        ],
        version=definition.version,
        risk_level=definition.risk_level.value,
        required_permissions=list(definition.required_permissions),
        idempotent=definition.idempotent,
        timeout_seconds=definition.timeout_seconds,
        output_mode=definition.output_mode,
    )


def to_memory_message_response(message: MemoryMessage) -> MemoryMessageResponse:
    return MemoryMessageResponse(
        id=message.id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
        name=message.name,
    )


def to_tool_result_response(result: ToolCallResult) -> ToolCallResultResponse:
    return ToolCallResultResponse(
        tool_name=result.tool_name,
        arguments=result.arguments,
        output=result.output,
        invocation_id=result.invocation_id,
        status=result.status.value,
        risk_level=result.risk_level.value,
        duration_ms=result.duration_ms,
        artifact_id=result.artifact_id,
        output_truncated=result.output_truncated,
        audit=result.audit,
    )


# ===================== 第3步：提供工具列表接口 =====================
@router.get("/tools", response_model=ApiResponse[ToolListResponse])
async def list_tools(
    service: AgentCoreService = Depends(build_agent_core_service),
) -> ApiResponse[ToolListResponse]:
    """返回当前 Agent 可以调用的工具 schema。"""

    return ApiResponse(
        data=ToolListResponse(
            items=[to_tool_response(tool) for tool in service.list_tools()],
        )
    )


@router.post(
    "/tools/{tool_name}/invoke",
    response_model=ApiResponse[ToolCallResultResponse],
)
async def invoke_tool(
    tool_name: str,
    payload: ToolInvokeRequest,
    db_session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ToolCallResultResponse]:
    runtime = ToolRuntime(
        build_builtin_tool_registry(content_model=LLMService()),
        uow=UnitOfWork(db_session),
    )
    result = await runtime.execute(
        tool_name,
        payload.arguments,
        ToolExecutionContext(
            project_id=payload.project_id,
            task_id=payload.task_id,
            session_id=payload.session_id,
            actor=payload.actor,
            allowed_permissions=set(payload.allowed_permissions),
            approved=payload.approved,
            approval_reason=payload.approval_reason,
            idempotency_key=payload.idempotency_key,
        ),
    )
    return ApiResponse(data=to_tool_result_response(result))


# ===================== 第4步：提供最小 Agent 演示接口 =====================
@router.post("/demo", response_model=ApiResponse[AgentCoreDemoResponse])
async def run_demo(
    payload: AgentCoreDemoRequest,
    service: AgentCoreService = Depends(build_agent_core_service),
) -> ApiResponse[AgentCoreDemoResponse]:
    """运行一次 Memory + 工具调用演示。"""

    messages, selected_tool, tool_result, next_step = service.run_demo(
        task=payload.task,
        tool_name=payload.tool_name,
    )
    return ApiResponse(
        data=AgentCoreDemoResponse(
            messages=[
                to_memory_message_response(message)
                for message in messages
            ],
            selected_tool=to_tool_response(selected_tool),
            tool_result=to_tool_result_response(tool_result),
            next_step=next_step,
        )
    )
