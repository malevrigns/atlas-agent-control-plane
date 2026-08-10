from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class KnowledgeDocumentStatus(StrEnum):
    """知识文档的摄取生命周期。

    RAG 的第一条生产纪律是：检索只能命中"摄取成功"的内容。
    半成品文档绝不允许进入向量索引，否则会污染引用链。
    """

    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class KnowledgeSourceType(StrEnum):
    """文档的来源类型，用于引用展示与审计。

    manual 手工粘贴、upload 文件上传、url 网页抓取、
    session 会话沉淀、image 图片视觉解析（多模态 RAG）。
    """

    manual = "manual"
    upload = "upload"
    url = "url"
    session = "session"
    image = "image"


@dataclass(slots=True)
class KnowledgeBase:
    """一个知识库。

    知识库是 RAG 的租户边界：不同项目、不同业务域的文档
    落在不同知识库里，检索永远不会跨库串数据。
    """

    id: UUID
    name: str
    description: str
    project_id: str
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    document_count: int = 0
    chunk_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


@dataclass(slots=True)
class KnowledgeDocument:
    """知识库中的一份文档。

    文档保存原文与摄取状态；切分后的 chunk 才是检索单元。
    ``error`` 记录摄取失败原因，方便运维在管理面板中定位。
    """

    id: UUID
    knowledge_base_id: UUID
    title: str
    source_type: KnowledgeSourceType
    source_ref: str
    content: str
    content_sha256: str
    status: KnowledgeDocumentStatus
    chunk_count: int = 0
    error: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class KnowledgeChunk:
    """文档切分后的最小检索单元。

    chunk 与向量记录一一对应：chunk 存正文与位置信息，
    向量存储只保存 embedding 与回链 id，二者通过 chunk_id 关联。
    """

    id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    seq: int
    content: str
    char_start: int
    char_end: int
    token_estimate: int
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(slots=True)
class RetrievedChunk:
    """一次检索命中的 chunk，附带可解释的评分明细。"""

    chunk_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    document_title: str
    seq: int
    content: str
    vector_score: float
    lexical_score: float
    final_score: float
    matched_terms: list[str] = field(default_factory=list)
    citation: str = ""


@dataclass(slots=True)
class RagQueryResult:
    """一次 RAG 查询的完整结果。

    除了命中 chunk，还包含检索计划与预算信息，
    与 Memory Control Plane 的 retrieval trace 使用同一套审计语言。
    """

    query: str
    knowledge_base_id: UUID
    backend: str
    embedding_provider: str
    top_k: int
    candidate_count: int
    chunks: list[RetrievedChunk] = field(default_factory=list)
    total_chars: int = 0
    context_text: str = ""
