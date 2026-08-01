from fastapi import APIRouter, Depends

from app.application.agent_thinking_service import AgentThinkingService
from app.domain.agent_thinking.entities import (
    ThinkingComparison,
    ThinkingModeDemo,
    ThinkingModeInfo,
)
from app.schemas.agent_thinking import (
    ThinkingCompareRequest,
    ThinkingComparisonResponse,
    ThinkingModeDemoResponse,
    ThinkingModeListResponse,
    ThinkingModeResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/agent-thinking", tags=["agent-thinking"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_agent_thinking_service() -> AgentThinkingService:
    """创建 AgentThinkingService。

    当前服务没有数据库连接，也没有外部 HTTP 客户端，所以可以直接实例化。
    后续如果接入真实 Agent 配置，再在这里注入依赖。
    """

    return AgentThinkingService()


# ===================== 第2步：把领域对象转换成接口响应 =====================
def to_mode_response(mode: ThinkingModeInfo) -> ThinkingModeResponse:
    """把领域层的模式说明转换成 API schema。"""

    return ThinkingModeResponse(
        mode=mode.mode.value,
        name=mode.name,
        summary=mode.summary,
        best_for=mode.best_for,
        risk=mode.risk,
    )


def to_demo_response(demo: ThinkingModeDemo) -> ThinkingModeDemoResponse:
    """把单个模式的演示结果转换成前端需要的结构。"""

    return ThinkingModeDemoResponse(
        mode=demo.mode.value,
        name=demo.name,
        headline=demo.headline,
        steps=demo.steps,
        tool_calls=demo.tool_calls,
        final_answer=demo.final_answer,
    )


def to_comparison_response(
    comparison: ThinkingComparison,
) -> ThinkingComparisonResponse:
    """把整体对比结果转换成统一响应 data。"""

    return ThinkingComparisonResponse(
        task=comparison.task,
        demos=[to_demo_response(demo) for demo in comparison.demos],
    )


# ===================== 第3步：提供模式列表接口 =====================
@router.get("/modes", response_model=ApiResponse[ThinkingModeListResponse])
async def list_modes(
    service: AgentThinkingService = Depends(build_agent_thinking_service),
) -> ApiResponse[ThinkingModeListResponse]:
    """返回 ChatBot、CoT、ReAct 和任务拆解的基础说明。"""

    modes = service.list_modes()
    return ApiResponse(
        data=ThinkingModeListResponse(
            items=[to_mode_response(mode) for mode in modes],
        )
    )


# ===================== 第4步：提供任务对比接口 =====================
@router.post("/compare", response_model=ApiResponse[ThinkingComparisonResponse])
async def compare_thinking_modes(
    payload: ThinkingCompareRequest,
    service: AgentThinkingService = Depends(build_agent_thinking_service),
) -> ApiResponse[ThinkingComparisonResponse]:
    """对同一个任务生成多种 Agent 思维模式的可视化对比。"""

    comparison = service.compare(payload.task)
    return ApiResponse(data=to_comparison_response(comparison))

