from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.memory_service import MemoryService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.memory import (
    MemoryCandidateListResponse,
    MemoryCandidateResponse,
    MemoryCreateRequest,
    MemoryExtractRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdateRequest,
    MemoryVerifyRequest,
)

router = APIRouter(prefix="/memories", tags=["memories"])


def build_memory_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> MemoryService:
    return MemoryService(UnitOfWork(db_session))


def to_memory_response(memory: AgentMemory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        kind=memory.kind.value,
        content=memory.content,
        importance=memory.importance,
        enabled=memory.enabled,
        source_session_id=memory.source_session_id,
        source_event_id=memory.source_event_id,
        expires_at=memory.expires_at,
        metadata=memory.metadata,
        scope=memory.scope.value,
        status=memory.status.value,
        subject=memory.subject,
        predicate=memory.predicate,
        value=memory.value,
        confidence=memory.confidence,
        authority=memory.authority.value,
        valid_from=memory.valid_from,
        valid_to=memory.valid_to,
        ttl_seconds=memory.ttl_seconds,
        provenance=memory.provenance,
        supersedes=memory.supersedes,
        sensitivity=memory.sensitivity.value,
        project_id=memory.project_id,
        task_id=memory.task_id,
        user_id=memory.user_id,
        created_by=memory.created_by,
        verification=memory.verification,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        related_ids=memory.related_ids or None,
        access_count=memory.access_count or None,
        last_accessed_at=memory.last_accessed_at,
    )


def to_candidate_response(candidate: MemoryCandidate) -> MemoryCandidateResponse:
    return MemoryCandidateResponse(
        kind=candidate.kind.value,
        content=candidate.content,
        importance=candidate.importance,
        reason=candidate.reason,
        source_session_id=candidate.source_session_id,
        source_event_id=candidate.source_event_id,
        metadata=candidate.metadata,
    )


def parse_memory_kind(value: str) -> MemoryKind:
    try:
        return MemoryKind(value)
    except ValueError as exc:
        raise AppException(
            message=f"unsupported memory kind: {value}",
            code=400,
            status_code=400,
        ) from exc


def parse_enum(enum_type, value: str, label: str):
    try:
        return enum_type(value)
    except ValueError as exc:
        raise AppException(
            message=f"unsupported {label}: {value}",
            code=400,
            status_code=400,
        ) from exc


# ===================== 第1步：读取长期记忆列表 =====================
@router.get("", response_model=ApiResponse[MemoryListResponse])
async def list_memories(
    kind: str | None = Query(default=None),
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryListResponse]:
    memory_kind = parse_memory_kind(kind) if kind else None
    memories = await service.list_memories(
        kind=memory_kind,
        enabled_only=enabled_only,
        limit=limit,
    )
    return ApiResponse(
        data=MemoryListResponse(
            items=[to_memory_response(memory) for memory in memories]
        )
    )


# ===================== 第2步：手动新增长期记忆 =====================
@router.post("", response_model=ApiResponse[MemoryResponse])
async def create_memory(
    payload: MemoryCreateRequest,
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryResponse]:
    memory = await service.create_memory(
        kind=parse_memory_kind(payload.kind),
        content=payload.content,
        importance=payload.importance,
        source_session_id=payload.source_session_id,
        source_event_id=payload.source_event_id,
        expires_at=payload.expires_at,
        metadata=payload.metadata,
        scope=parse_enum(MemoryScope, payload.scope, "memory scope"),
        requested_status=parse_enum(MemoryStatus, payload.status, "memory status"),
        subject=payload.subject,
        predicate=payload.predicate,
        value=payload.value,
        confidence=payload.confidence,
        authority=parse_enum(MemoryAuthority, payload.authority, "memory authority"),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        ttl_seconds=payload.ttl_seconds,
        provenance=payload.provenance,
        supersedes=payload.supersedes,
        sensitivity=parse_enum(MemorySensitivity, payload.sensitivity, "memory sensitivity"),
        project_id=payload.project_id,
        task_id=payload.task_id,
        user_id=payload.user_id,
        created_by=payload.created_by,
        verification=payload.verification,
    )
    return ApiResponse(data=to_memory_response(memory))


@router.post("/{memory_id}/verify", response_model=ApiResponse[MemoryResponse])
async def verify_memory(
    memory_id: UUID,
    payload: MemoryVerifyRequest,
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryResponse]:
    memory = await service.verify_memory(
        memory_id,
        provenance=payload.provenance,
        verification=payload.verification,
        authority=parse_enum(MemoryAuthority, payload.authority, "memory authority"),
    )
    return ApiResponse(data=to_memory_response(memory))


# ===================== 第3步：更新长期记忆 =====================
@router.patch("/{memory_id}", response_model=ApiResponse[MemoryResponse])
async def update_memory(
    memory_id: UUID,
    payload: MemoryUpdateRequest,
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryResponse]:
    memory = await service.update_memory(
        memory_id,
        content=payload.content,
        importance=payload.importance,
        enabled=payload.enabled,
        expires_at=payload.expires_at,
        metadata=payload.metadata,
    )
    return ApiResponse(data=to_memory_response(memory))


# ===================== 第4步：删除长期记忆 =====================
@router.delete("/{memory_id}", response_model=ApiResponse[MemoryResponse])
async def delete_memory(
    memory_id: UUID,
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryResponse]:
    memory = await service.delete_memory(memory_id)
    return ApiResponse(data=to_memory_response(memory))


# ===================== 第5步：从会话抽取记忆候选 =====================
@router.post("/extract", response_model=ApiResponse[MemoryCandidateListResponse])
async def extract_memory_candidates(
    payload: MemoryExtractRequest,
    service: MemoryService = Depends(build_memory_service),
) -> ApiResponse[MemoryCandidateListResponse]:
    candidates = await service.extract_candidates(payload.session_id)
    return ApiResponse(
        data=MemoryCandidateListResponse(
            items=[
                to_candidate_response(candidate)
                for candidate in candidates
            ]
        )
    )
