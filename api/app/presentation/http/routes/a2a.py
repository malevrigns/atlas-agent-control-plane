from fastapi import APIRouter, Depends

from app.application.a2a_intro_service import A2aIntroService
from app.application.a2a_service import A2aService
from app.domain.a2a.entities import (
    A2aAgentCard,
    A2aCapability,
    A2aMessageDemo,
    A2aMessagePart,
    A2aRemoteAgentInfo,
    A2aRole,
    A2aTaskResult,
    A2aTaskStep,
)
from app.schemas.a2a import (
    A2aAgentCardRequest,
    A2aAgentCardResponse,
    A2aCapabilityResponse,
    A2aConceptsResponse,
    A2aMessageDemoResponse,
    A2aMessageInvokeRequest,
    A2aMessagePartResponse,
    A2aMessageSendRequest,
    A2aRemoteAgentListResponse,
    A2aRemoteAgentResponse,
    A2aRoleResponse,
    A2aTaskResultResponse,
    A2aTaskStepResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/a2a", tags=["a2a"])


# ===================== 第1步：创建 A2A 入门应用服务 =====================
def build_a2a_intro_service() -> A2aIntroService:
    """创建第 34 章 A2A 入门服务。"""

    # 第 34 章概念接口仍然保留，便于读者对照“概念演示”和“真实接入”。
    return A2aIntroService()


def build_a2a_service() -> A2aService:
    """创建第 35 章真实 A2A 接入服务。"""

    # 第 35 章开始，这个 service 会读取 config/a2a.yaml 并调用远程 Agent。
    return A2aService()


# ===================== 第2步：领域对象转换为 API 响应 =====================
def to_role_response(role: A2aRole) -> A2aRoleResponse:
    return A2aRoleResponse(
        name=role.name,
        responsibility=role.responsibility,
        system_mapping=role.system_mapping,
    )


def to_capability_response(capability: A2aCapability) -> A2aCapabilityResponse:
    return A2aCapabilityResponse(
        name=capability.name,
        description=capability.description,
        example=capability.example,
    )


def to_agent_card_response(card: A2aAgentCard) -> A2aAgentCardResponse:
    # 1. Agent Card 是领域对象，API 响应需要转换成 Pydantic DTO。
    # 2. capabilities 也逐个转换，保证响应结构对前端稳定。
    return A2aAgentCardResponse(
        name=card.name,
        description=card.description,
        url=card.url,
        version=card.version,
        capabilities=[
            to_capability_response(capability)
            for capability in card.capabilities
        ],
        default_input_modes=card.default_input_modes,
        default_output_modes=card.default_output_modes,
    )


def to_part_response(part: A2aMessagePart) -> A2aMessagePartResponse:
    return A2aMessagePartResponse(kind=part.kind, text=part.text)


def to_step_response(step: A2aTaskStep) -> A2aTaskStepResponse:
    return A2aTaskStepResponse(
        index=step.index,
        action=step.action,
        detail=step.detail,
    )


def to_message_demo_response(demo: A2aMessageDemo) -> A2aMessageDemoResponse:
    # 第 34 章 demo 响应仍然使用单独 DTO，避免和第 35 章真实调用混在一起。
    return A2aMessageDemoResponse(
        remote_agent=demo.remote_agent,
        task_id=demo.task_id,
        status=demo.status,
        input_message=[to_part_response(part) for part in demo.input_message],
        output_message=[to_part_response(part) for part in demo.output_message],
        steps=[to_step_response(step) for step in demo.steps],
    )


def to_remote_agent_response(agent: A2aRemoteAgentInfo) -> A2aRemoteAgentResponse:
    # 1. 远程 Agent 列表来自配置文件。
    # 2. 前端环境面板会用 enabled/transport/url 帮助用户判断当前接入状态。
    return A2aRemoteAgentResponse(
        key=agent.key,
        enabled=agent.enabled,
        transport=agent.transport,
        name=agent.name,
        description=agent.description,
        url=agent.url,
        version=agent.version,
        capabilities=[
            to_capability_response(capability)
            for capability in agent.capabilities
        ],
    )


def to_task_result_response(result: A2aTaskResult) -> A2aTaskResultResponse:
    # 1. A2A 调用结果要保留 task_id/status，方便前端展示远程任务状态。
    # 2. input/output/steps 会进入工具预览，帮助用户观察远程 Agent 的执行过程。
    return A2aTaskResultResponse(
        agent_key=result.agent_key,
        remote_agent=result.remote_agent,
        task_id=result.task_id,
        status=result.status,
        input_message=[to_part_response(part) for part in result.input_message],
        output_message=[to_part_response(part) for part in result.output_message],
        steps=[to_step_response(step) for step in result.steps],
    )


# ===================== 第3步：A2A 概念说明接口 =====================
@router.get("/concepts", response_model=ApiResponse[A2aConceptsResponse])
async def get_a2a_concepts(
    service: A2aIntroService = Depends(build_a2a_intro_service),
) -> ApiResponse[A2aConceptsResponse]:
    """返回 A2A 核心角色和协议定位。"""

    return ApiResponse(
        data=A2aConceptsResponse(
            roles=[to_role_response(role) for role in service.list_roles()],
            protocol="Agent-to-Agent task and message collaboration",
            next_step="第 35 章会把远程 Agent 注册成可调用工具。",
        )
    )


# ===================== 第4步：示例 Agent Card 接口 =====================
@router.get("/demo/agent-card", response_model=ApiResponse[A2aAgentCardResponse])
async def get_a2a_demo_agent_card(
    service: A2aIntroService = Depends(build_a2a_intro_service),
) -> ApiResponse[A2aAgentCardResponse]:
    """返回一个课程内置的示例 Agent Card。"""

    return ApiResponse(data=to_agent_card_response(service.get_demo_agent_card()))


# ===================== 第5步：模拟 message/send 接口 =====================
@router.post("/demo/message", response_model=ApiResponse[A2aMessageDemoResponse])
async def send_a2a_demo_message(
    payload: A2aMessageSendRequest,
    service: A2aIntroService = Depends(build_a2a_intro_service),
) -> ApiResponse[A2aMessageDemoResponse]:
    """模拟 Host Agent 向远程 Agent 发送任务消息。"""

    demo = service.send_demo_message(payload.message)
    return ApiResponse(data=to_message_demo_response(demo))


# ===================== 第6步：真实 A2A 远程 Agent 配置列表 =====================
@router.get("/agents", response_model=ApiResponse[A2aRemoteAgentListResponse])
async def list_a2a_agents(
    service: A2aService = Depends(build_a2a_service),
) -> ApiResponse[A2aRemoteAgentListResponse]:
    """返回配置文件中的远程 Agent 列表。"""

    # 1. 从应用服务读取远程 Agent 配置状态。
    # 2. 转换成响应 DTO，避免前端直接依赖 YAML 配置结构。
    return ApiResponse(
        data=A2aRemoteAgentListResponse(
            items=[
                to_remote_agent_response(agent)
                for agent in service.list_agents()
            ],
        )
    )


# ===================== 第7步：读取指定远程 Agent Card =====================
@router.get("/agents/{agent_key}/card", response_model=ApiResponse[A2aAgentCardResponse])
async def get_a2a_agent_card(
    agent_key: str,
    service: A2aService = Depends(build_a2a_service),
) -> ApiResponse[A2aAgentCardResponse]:
    """读取一个已配置远程 Agent 的 Agent Card。"""

    # 1. 路径参数 agent_key 决定读取哪个远程 Agent。
    # 2. service 会校验该 Agent 是否存在、是否启用，再调用对应 transport。
    return ApiResponse(data=to_agent_card_response(service.get_agent_card(agent_key)))


@router.post("/agent-card", response_model=ApiResponse[A2aAgentCardResponse])
async def get_a2a_agent_card_by_payload(
    payload: A2aAgentCardRequest,
    service: A2aService = Depends(build_a2a_service),
) -> ApiResponse[A2aAgentCardResponse]:
    """通过请求体读取 Agent Card，方便前端或工具传入可选 agent_key。"""

    # 1. payload.agent_key 为空时，service 会使用默认远程 Agent。
    # 2. 这个接口适合后续设置页或工具调试面板用 POST 形式读取 Agent Card。
    return ApiResponse(data=to_agent_card_response(service.get_agent_card(payload.agent_key)))


# ===================== 第8步：真实 A2A message/send 调用 =====================
@router.post("/message/send", response_model=ApiResponse[A2aTaskResultResponse])
async def send_a2a_message(
    payload: A2aMessageInvokeRequest,
    service: A2aService = Depends(build_a2a_service),
) -> ApiResponse[A2aTaskResultResponse]:
    """向配置中的远程 Agent 发送任务消息。"""

    # 1. 接收前端或工具传来的 agent_key 和 message。
    # 2. 应用服务负责选择远程 Agent、调用 transport、返回统一 A2A 任务结果。
    result = service.send_message(
        agent_key=payload.agent_key,
        message=payload.message,
    )

    # 3. 把领域对象转换成接口响应，返回给前端或 curl 调试命令。
    return ApiResponse(data=to_task_result_response(result))
