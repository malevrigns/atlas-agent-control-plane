from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.skill_service import SkillService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.skills.entities import Skill, SkillStatus
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.skill import (
    SkillContextItemResponse,
    SkillContextResponse,
    SkillCreateRequest,
    SkillEnableRequest,
    SkillListResponse,
    SkillNewVersionRequest,
    SkillResponse,
    SkillTestRecordRequest,
    SkillUpdateRequest,
)

router = APIRouter(prefix="/skills", tags=["skills"])


def build_skill_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> SkillService:
    return SkillService(UnitOfWork(db_session))


def to_skill_response(skill: Skill) -> SkillResponse:
    return SkillResponse(
        id=skill.id,
        skill_key=skill.skill_key,
        version=skill.version,
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        definition=skill.definition,
        risk_level=skill.risk_level.value,
        status=skill.status.value,
        enabled=skill.enabled,
        tags=skill.tags,
        test_record=skill.test_record,
        created_by=skill.created_by,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
        published_at=skill.published_at,
    )


def parse_status(value: str) -> SkillStatus:
    try:
        return SkillStatus(value)
    except ValueError as exc:
        raise AppException(
            message=f"unsupported skill status: {value}",
            code=400,
            status_code=400,
        ) from exc


# ===================== 第1步：技能列表与详情 =====================
@router.get("", response_model=ApiResponse[SkillListResponse])
async def list_skills(
    status: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillListResponse]:
    skills = await service.list_skills(
        status=parse_status(status) if status else None,
        enabled_only=enabled_only,
        search=search,
        limit=limit,
    )
    return ApiResponse(
        data=SkillListResponse(items=[to_skill_response(skill) for skill in skills])
    )


@router.get("/context", response_model=ApiResponse[SkillContextResponse])
async def preview_skill_context(
    query: str = Query(min_length=1, max_length=2000),
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillContextResponse]:
    """预览给定任务会注入哪些技能，管理面板用它做"命中调试"。"""

    context = await service.build_skill_context(query=query)
    return ApiResponse(
        data=SkillContextResponse(
            query=context.query,
            items=[
                SkillContextItemResponse(
                    id=item.id,
                    skill_key=item.skill_key,
                    version=item.version,
                    name=item.name,
                    instructions=item.instructions,
                    risk_level=item.risk_level,
                    relevance_score=item.relevance_score,
                    matched_terms=item.matched_terms,
                )
                for item in context.items
            ],
            candidate_count=context.candidate_count,
            omitted_count=context.omitted_count,
            total_chars=context.total_chars,
            rendered=SkillService.render_skill_context(context),
        )
    )


@router.get("/{skill_id}", response_model=ApiResponse[SkillResponse])
async def get_skill(
    skill_id: UUID,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.get_skill(skill_id)
    return ApiResponse(data=to_skill_response(skill))


@router.get("/{skill_key}/versions", response_model=ApiResponse[SkillListResponse])
async def list_skill_versions(
    skill_key: str,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillListResponse]:
    versions = await service.list_versions(skill_key)
    return ApiResponse(
        data=SkillListResponse(items=[to_skill_response(skill) for skill in versions])
    )


# ===================== 第2步：创建、编辑与版本演进 =====================
@router.post("", response_model=ApiResponse[SkillResponse])
async def create_skill(
    payload: SkillCreateRequest,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.create_skill(
        skill_key=payload.skill_key,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        version=payload.version,
        definition=payload.definition,
        risk_level=payload.risk_level,
        tags=payload.tags,
        created_by=payload.created_by,
    )
    return ApiResponse(data=to_skill_response(skill))


@router.patch("/{skill_id}", response_model=ApiResponse[SkillResponse])
async def update_skill(
    skill_id: UUID,
    payload: SkillUpdateRequest,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.update_skill(
        skill_id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        definition=payload.definition,
        risk_level=payload.risk_level,
        tags=payload.tags,
    )
    return ApiResponse(data=to_skill_response(skill))


@router.post("/{skill_id}/versions", response_model=ApiResponse[SkillResponse])
async def create_skill_version(
    skill_id: UUID,
    payload: SkillNewVersionRequest,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.create_new_version(
        skill_id,
        version=payload.version,
        created_by=payload.created_by,
    )
    return ApiResponse(data=to_skill_response(skill))


# ===================== 第3步：发布、启停与治理动作 =====================
@router.post("/{skill_id}/publish", response_model=ApiResponse[SkillResponse])
async def publish_skill(
    skill_id: UUID,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.publish_skill(skill_id)
    return ApiResponse(data=to_skill_response(skill))


@router.post("/{skill_id}/enabled", response_model=ApiResponse[SkillResponse])
async def set_skill_enabled(
    skill_id: UUID,
    payload: SkillEnableRequest,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.set_enabled(skill_id, enabled=payload.enabled)
    return ApiResponse(data=to_skill_response(skill))


@router.post("/{skill_id}/deprecate", response_model=ApiResponse[SkillResponse])
async def deprecate_skill(
    skill_id: UUID,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.deprecate_skill(skill_id)
    return ApiResponse(data=to_skill_response(skill))


@router.post("/{skill_id}/test-record", response_model=ApiResponse[SkillResponse])
async def record_skill_test(
    skill_id: UUID,
    payload: SkillTestRecordRequest,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.record_test(skill_id, test_record=payload.test_record)
    return ApiResponse(data=to_skill_response(skill))


@router.delete("/{skill_id}", response_model=ApiResponse[SkillResponse])
async def delete_skill(
    skill_id: UUID,
    service: SkillService = Depends(build_skill_service),
) -> ApiResponse[SkillResponse]:
    skill = await service.delete_skill(skill_id)
    return ApiResponse(data=to_skill_response(skill))
