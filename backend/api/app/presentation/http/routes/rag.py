from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.rag_service import RagService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
    RagQueryResult,
)
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.rag import (
    DocumentIngestRequest,
    DocumentListResponse,
    DocumentResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
    RagHealthResponse,
    RagQueryRequest,
    RagQueryResponse,
    RetrievedChunkResponse,
)

router = APIRouter(prefix="/rag", tags=["rag"])


def build_rag_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> RagService:
    return RagService(UnitOfWork(db_session))


def to_knowledge_base_response(knowledge_base: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=knowledge_base.id,
        name=knowledge_base.name,
        description=knowledge_base.description,
        project_id=knowledge_base.project_id,
        embedding_provider=knowledge_base.embedding_provider,
        embedding_model=knowledge_base.embedding_model,
        embedding_dim=knowledge_base.embedding_dim,
        chunk_size=knowledge_base.chunk_size,
        chunk_overlap=knowledge_base.chunk_overlap,
        document_count=knowledge_base.document_count,
        chunk_count=knowledge_base.chunk_count,
        metadata=knowledge_base.metadata,
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )


def to_document_response(document: KnowledgeDocument) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        title=document.title,
        source_type=document.source_type.value,
        source_ref=document.source_ref,
        status=document.status.value,
        chunk_count=document.chunk_count,
        content_chars=len(document.content),
        error=document.error,
        metadata=document.metadata,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def to_query_response(result: RagQueryResult) -> RagQueryResponse:
    return RagQueryResponse(
        query=result.query,
        knowledge_base_id=result.knowledge_base_id,
        backend=result.backend,
        embedding_provider=result.embedding_provider,
        top_k=result.top_k,
        candidate_count=result.candidate_count,
        total_chars=result.total_chars,
        context_text=result.context_text,
        chunks=[
            RetrievedChunkResponse(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                seq=chunk.seq,
                content=chunk.content,
                vector_score=chunk.vector_score,
                lexical_score=chunk.lexical_score,
                final_score=chunk.final_score,
                matched_terms=chunk.matched_terms,
                citation=chunk.citation,
                fusion_score=chunk.fusion_score,
                rerank_score=chunk.rerank_score,
                confidence=chunk.confidence,
            )
            for chunk in result.chunks
        ],
        retrieval_metadata=result.retrieval_metadata,
    )


def parse_source_type(value: str) -> KnowledgeSourceType:
    try:
        return KnowledgeSourceType(value)
    except ValueError as exc:
        raise AppException(
            message=f"unsupported source type: {value}",
            code=400,
            status_code=400,
        ) from exc


# ===================== 第1步：知识库 CRUD =====================
@router.get("/knowledge-bases", response_model=ApiResponse[KnowledgeBaseListResponse])
async def list_knowledge_bases(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[KnowledgeBaseListResponse]:
    knowledge_bases = await service.list_knowledge_bases(project_id=project_id, limit=limit)
    return ApiResponse(
        data=KnowledgeBaseListResponse(
            items=[to_knowledge_base_response(item) for item in knowledge_bases]
        )
    )


@router.post("/knowledge-bases", response_model=ApiResponse[KnowledgeBaseResponse])
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = await service.create_knowledge_base(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        metadata=payload.metadata,
    )
    return ApiResponse(data=to_knowledge_base_response(knowledge_base))


@router.get(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=ApiResponse[KnowledgeBaseResponse],
)
async def get_knowledge_base(
    knowledge_base_id: UUID,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = await service.get_knowledge_base(knowledge_base_id)
    return ApiResponse(data=to_knowledge_base_response(knowledge_base))


@router.patch(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=ApiResponse[KnowledgeBaseResponse],
)
async def update_knowledge_base(
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdateRequest,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = await service.update_knowledge_base(
        knowledge_base_id,
        name=payload.name,
        description=payload.description,
        metadata=payload.metadata,
    )
    return ApiResponse(data=to_knowledge_base_response(knowledge_base))


@router.delete(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=ApiResponse[KnowledgeBaseResponse],
)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = await service.delete_knowledge_base(knowledge_base_id)
    return ApiResponse(data=to_knowledge_base_response(knowledge_base))


# ===================== 第2步：文档摄取与管理 =====================
@router.get(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=ApiResponse[DocumentListResponse],
)
async def list_documents(
    knowledge_base_id: UUID,
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[DocumentListResponse]:
    parsed_status: KnowledgeDocumentStatus | None = None
    if status:
        try:
            parsed_status = KnowledgeDocumentStatus(status)
        except ValueError as exc:
            raise AppException(
                message=f"unsupported document status: {status}",
                code=400,
                status_code=400,
            ) from exc
    documents = await service.list_documents(
        knowledge_base_id, status=parsed_status, limit=limit
    )
    return ApiResponse(
        data=DocumentListResponse(items=[to_document_response(item) for item in documents])
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=ApiResponse[DocumentResponse],
)
async def ingest_document(
    knowledge_base_id: UUID,
    payload: DocumentIngestRequest,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[DocumentResponse]:
    document = await service.ingest_document(
        knowledge_base_id,
        title=payload.title,
        content=payload.content,
        source_type=parse_source_type(payload.source_type),
        source_ref=payload.source_ref,
        metadata=payload.metadata,
    )
    return ApiResponse(data=to_document_response(document))


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents/image",
    response_model=ApiResponse[DocumentResponse],
)
async def ingest_image_document(
    knowledge_base_id: UUID,
    upload: UploadFile = File(...),
    title: str = Form(""),
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[DocumentResponse]:
    """多模态摄取：上传图片，由视觉模型解析成文本后切分入库。"""

    data = await upload.read()
    document = await service.ingest_image_document(
        knowledge_base_id,
        filename=upload.filename or "image",
        content_type=upload.content_type or "",
        data=data,
        title=title,
    )
    return ApiResponse(data=to_document_response(document))


@router.post(
    "/documents/{document_id}/reingest",
    response_model=ApiResponse[DocumentResponse],
)
async def reingest_document(
    document_id: UUID,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[DocumentResponse]:
    document = await service.reingest_document(document_id)
    return ApiResponse(data=to_document_response(document))


@router.delete("/documents/{document_id}", response_model=ApiResponse[DocumentResponse])
async def delete_document(
    document_id: UUID,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[DocumentResponse]:
    document = await service.delete_document(document_id)
    return ApiResponse(data=to_document_response(document))


# ===================== 第3步：RAG 查询与健康检查 =====================
@router.post(
    "/knowledge-bases/{knowledge_base_id}/query",
    response_model=ApiResponse[RagQueryResponse],
)
async def query_knowledge_base(
    knowledge_base_id: UUID,
    payload: RagQueryRequest,
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[RagQueryResponse]:
    result = await service.query(
        knowledge_base_id,
        query=payload.query,
        top_k=payload.top_k,
        min_score=payload.min_score,
    )
    return ApiResponse(data=to_query_response(result))


@router.get("/health", response_model=ApiResponse[RagHealthResponse])
async def rag_health(
    service: RagService = Depends(build_rag_service),
) -> ApiResponse[RagHealthResponse]:
    payload = await service.health()
    return ApiResponse(
        data=RagHealthResponse(
            vector_store=payload["vector_store"],
            embedding=payload["embedding"],
            chunking=payload["chunking"],
        )
    )
