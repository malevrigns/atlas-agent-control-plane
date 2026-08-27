from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    project_id: str = Field(default="default", max_length=128)
    chunk_size: int | None = Field(default=None, gt=0, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    metadata: dict[str, object] | None = None


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    name: str
    description: str
    project_id: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    document_count: int
    chunk_count: int
    metadata: dict[str, object]
    created_at: datetime | None
    updated_at: datetime | None


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]


class DocumentIngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1)
    source_type: str = "manual"
    source_ref: str = Field(default="", max_length=512)
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    title: str
    source_type: str
    source_ref: str
    status: str
    chunk_count: int
    content_chars: int
    error: str
    metadata: dict[str, object]
    created_at: datetime | None
    updated_at: datetime | None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    min_score: float | None = Field(default=None, ge=0, le=1)


class RetrievedChunkResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    seq: int
    content: str
    vector_score: float
    lexical_score: float
    final_score: float
    matched_terms: list[str]
    citation: str
    # RRF 多查询融合信号（归一化到 0-1）；None 表示该候选未参与多查询融合。
    fusion_score: float | None = None
    # 重排器给出的相关分（0-1）；None 表示该候选未参与重排。
    rerank_score: float | None = None
    # 引用置信度（0-1）：相关分 × 文档新鲜度 × 来源类型加权的综合评估。
    confidence: float | None = None


class RagQueryResponse(BaseModel):
    query: str
    knowledge_base_id: UUID
    backend: str
    embedding_provider: str
    top_k: int
    candidate_count: int
    total_chars: int
    context_text: str
    chunks: list[RetrievedChunkResponse]
    # 检索过程元数据：耗时、候选数、查询变体、重排开关与权重等，
    # 供前端展示与运维审计；旧版结果可能为 None（向后兼容）。
    retrieval_metadata: dict[str, object] | None = None


class RagHealthResponse(BaseModel):
    vector_store: dict[str, object]
    embedding: dict[str, object]
    chunking: dict[str, object]
