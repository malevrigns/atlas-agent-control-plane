from fastapi import APIRouter, Depends

from app.application.agent_harness_service import AgentHarnessService
from app.domain.harness.entities import (
    HarnessAssertion,
    HarnessCase,
    HarnessExpectation,
    HarnessRun,
)
from app.schemas.common import ApiResponse
from app.schemas.harness import (
    HarnessAssertionResponse,
    HarnessCaseListResponse,
    HarnessCaseResponse,
    HarnessEventResponse,
    HarnessExpectationResponse,
    HarnessReplayResponse,
    HarnessRunRequest,
    HarnessRunResponse,
)

router = APIRouter(prefix="/harness", tags=["harness"])

# Harness 运行记录需要跨请求查询和回放，所以这里使用模块级 service。
# 第 45 章先保存在进程内，后续如果要落库，只需要替换 service 内部存储。
harness_service = AgentHarnessService()


def build_harness_service() -> AgentHarnessService:
    return harness_service


def to_expectation_response(
    expectation: HarnessExpectation,
) -> HarnessExpectationResponse:
    return HarnessExpectationResponse(
        required_events=expectation.required_events,
        required_tools=expectation.required_tools,
        required_files=expectation.required_files,
        forbidden_events=expectation.forbidden_events,
    )


def to_case_response(case: HarnessCase) -> HarnessCaseResponse:
    return HarnessCaseResponse(
        id=case.id,
        title=case.title,
        task=case.task,
        description=case.description,
        tags=case.tags,
        expectation=to_expectation_response(case.expectation),
    )


def to_assertion_response(
    assertion: HarnessAssertion,
) -> HarnessAssertionResponse:
    return HarnessAssertionResponse(
        name=assertion.name,
        passed=assertion.passed,
        detail=assertion.detail,
    )


def to_event_response(event: dict) -> HarnessEventResponse:
    return HarnessEventResponse(
        id=str(event["id"]),
        type=str(event["type"]),
        payload=dict(event.get("payload") or {}),
        created_at=str(event["created_at"]),
    )


def to_run_response(run: HarnessRun) -> HarnessRunResponse:
    return HarnessRunResponse(
        id=run.id,
        case_id=run.case_id,
        mode=run.mode,
        status=run.status,
        task=run.task,
        prompt_summary=run.prompt_summary,
        events=[to_event_response(event) for event in run.events],
        assertions=[
            to_assertion_response(assertion)
            for assertion in run.assertions
        ],
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/cases", response_model=ApiResponse[HarnessCaseListResponse])
async def list_harness_cases(
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessCaseListResponse]:
    # ===================== 第1步：读取固定任务集 =====================
    cases = service.list_cases()

    # ===================== 第2步：转换成 HTTP 响应模型 =====================
    return ApiResponse(
        data=HarnessCaseListResponse(
            items=[to_case_response(case) for case in cases],
        )
    )


@router.post(
    "/cases/{case_id}/run",
    response_model=ApiResponse[HarnessRunResponse],
)
async def run_harness_case(
    case_id: str,
    payload: HarnessRunRequest,
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessRunResponse]:
    # 第 45 章默认使用 simulate，先保证断言和回放链路稳定可验。
    run = service.run_case(case_id=case_id, mode=payload.mode)
    return ApiResponse(data=to_run_response(run))


@router.get("/runs/{run_id}", response_model=ApiResponse[HarnessRunResponse])
async def get_harness_run(
    run_id: str,
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessRunResponse]:
    run = service.get_run(run_id)
    return ApiResponse(data=to_run_response(run))


@router.get(
    "/runs/{run_id}/replay",
    response_model=ApiResponse[HarnessReplayResponse],
)
async def replay_harness_run(
    run_id: str,
    service: AgentHarnessService = Depends(build_harness_service),
) -> ApiResponse[HarnessReplayResponse]:
    # 回放接口返回运行信息和事件流，前端可以按时间线重新渲染失败过程。
    run = service.replay_run(run_id)
    return ApiResponse(
        data=HarnessReplayResponse(
            run=to_run_response(run),
            events=[to_event_response(event) for event in run.events],
        )
    )
