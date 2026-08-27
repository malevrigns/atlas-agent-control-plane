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
    # 父文档检索（small-to-big）：子块所属父块的序号；None 表示传统单级切分。
    parent_seq: int | None = None
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
    # RRF 多查询融合信号（归一化到 0-1）；单查询检索时等于 1。
    fusion_score: float | None = None
    # 重排器给出的相关分（0-1）；None 表示该候选未参与重排。
    rerank_score: float | None = None
    # 引用置信度（0-1）：相关分 × 文档新鲜度 × 来源类型加权的综合评估。
    confidence: float | None = None


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
    # 检索过程元数据：耗时、候选数、使用的查询变体、是否触发重排等，
    # 供前端展示与运维审计（答案溯源链中“怎么找到的”一环）。
    retrieval_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ExpandedQuery:
    """改写后的查询与变体列表。

    ``original`` 是规范化后的原始查询，``variants`` 是 2-3 个改写变体
    （同义改写、上位词扩展、子问题分解）；``method`` 记录生成策略：
    ``llm`` 表示由 LLM 改写，``rule`` 表示降级为规则改写（停用词/
    同义词表/中英扩展）。变体为空时检索退化为单查询，行为与旧版一致。
    """

    original: str
    variants: list[str] = field(default_factory=list)
    method: str = "rule"

    @property
    def all_queries(self) -> list[str]:
        """参与检索的完整查询列表：主查询在前，变体依次跟随。"""

        return [self.original, *self.variants]
