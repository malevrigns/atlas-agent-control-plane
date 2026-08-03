from fastapi import APIRouter, Depends

from app.application.multi_agent_service import MultiAgentService
from app.domain.multi_agent.entities import (
    MultiAgentReview,
    MultiAgentRole,
    MultiAgentRunResult,
    MultiAgentSubTask,
)
from app.schemas.common import ApiResponse
from app.schemas.multi_agent import (
    MultiAgentReviewResponse,
    MultiAgentRoleListResponse,
    MultiAgentRoleResponse,
    MultiAgentRunRequest,
    MultiAgentRunResponse,
    MultiAgentSubTaskResponse,
)

router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])


# ===================== 第1步：创建多 Agent 应用服务 =====================
def build_multi_agent_service() -> MultiAgentService:
    """创建多 Agent 协作服务。"""

    # 1. 当前服务不依赖数据库，直接创建即可。
    # 2. 后续多 Agent 配置和运行记录变复杂后，再从这里注入仓库或配置管理器。
    return MultiAgentService()


# ===================== 第2步：领域对象转换为 API 响应 =====================
def to_role_response(role: MultiAgentRole) -> MultiAgentRoleResponse:
    # 角色信息会展示在前端环境面板和接口响应中。
    return MultiAgentRoleResponse(
        key=role.key,
        name=role.name,
        responsibility=role.responsibility,
        capability=role.capability,
    )


def to_subtask_response(subtask: MultiAgentSubTask) -> MultiAgentSubTaskResponse:
    # 子任务是 Manager 分派给 Worker 的最小工作单元。
    return MultiAgentSubTaskResponse(
        id=subtask.id,
        assignee=subtask.assignee,
        title=subtask.title,
        instruction=subtask.instruction,
        expected_output=subtask.expected_output,
        status=subtask.status,
        output=subtask.output,
    )


def to_review_response(review: MultiAgentReview) -> MultiAgentReviewResponse:
    # 评审结果用于说明这次协作是否通过 Reviewer 检查。
    return MultiAgentReviewResponse(
        reviewer=review.reviewer,
        status=review.status,
        comments=review.comments,
        improvement=review.improvement,
    )


def to_run_response(result: MultiAgentRunResult) -> MultiAgentRunResponse:
    # 1. MultiAgentRunResult 是领域对象。
    # 2. API 需要转成 Pydantic DTO，保证前端拿到稳定字段。
    return MultiAgentRunResponse(
        kind=result.kind,
        task=result.task,
        manager=result.manager,
        roles=[to_role_response(role) for role in result.roles],
        subtasks=[to_subtask_response(subtask) for subtask in result.subtasks],
        review=to_review_response(result.review),
        final_answer=result.final_answer,
    )


# ===================== 第3步：查询内置多 Agent 角色 =====================
@router.get("/roles", response_model=ApiResponse[MultiAgentRoleListResponse])
async def list_multi_agent_roles(
    service: MultiAgentService = Depends(build_multi_agent_service),
) -> ApiResponse[MultiAgentRoleListResponse]:
    """返回当前多 Agent 协作中可用的角色。"""

    # 1. 从服务读取角色列表。
    # 2. 转成响应 DTO，给前端环境面板和 curl 验证使用。
    return ApiResponse(
        data=MultiAgentRoleListResponse(
            items=[to_role_response(role) for role in service.list_roles()],
        )
    )


# ===================== 第4步：运行一次多 Agent 协作演示 =====================
@router.post("/run", response_model=ApiResponse[MultiAgentRunResponse])
async def run_multi_agent_collaboration(
    payload: MultiAgentRunRequest,
    service: MultiAgentService = Depends(build_multi_agent_service),
) -> ApiResponse[MultiAgentRunResponse]:
    """围绕一个任务运行 Manager -> Worker -> Reviewer -> 汇总流程。"""

    # 1. 接收调用方传来的 task。
    # 2. 应用服务负责编排角色、分派子任务、评审并汇总。
    result = service.run_collaboration(payload.task)

    # 3. 返回结构化协作结果，便于前端展示多 Agent 过程。
    return ApiResponse(data=to_run_response(result))
