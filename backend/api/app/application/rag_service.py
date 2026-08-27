"""RAG 应用服务。

负责知识库生命周期与"摄取 → 检索 → 引用"闭环：

- 摄取管线：去重 → 切分 → 向量化 → 写入向量存储 → 标记 ready。
  任何一步失败都会把文档标记为 failed 并记录原因，绝不留下半成品索引。
- 检索管线：查询向量化 → 向量召回 → 词法混合重排 → 预算裁剪 →
  生成带 [编号] 引用的上下文，并写入 retrieval trace 审计。
"""

import hashlib
import time
from pathlib import Path
from uuid import UUID, uuid4

from app.application.llm_service import LLMService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.rag.chunking import TextSpan, split_text, split_with_parents
from app.domain.rag.embedding import EmbeddingProvider
from app.domain.rag.entities import (
    ExpandedQuery,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
    RagQueryResult,
    RetrievedChunk,
)
from app.domain.rag.parent_context import PARENT_TEXT_KEY, expand_to_parent_context
from app.domain.rag.query_processing import (
    expand_query,
    tokenize_mixed_text,
)
from app.domain.rag.reranking import confidence_score, rerank_chunks
from app.domain.rag.retrieval import (
    blend_final_score,
    build_retrieval_metadata,
    build_trace_payload,
    fuse_recall_scores,
    score_retrieval_candidates,
)
from app.domain.rag.vector_store import VectorMatch, VectorRecord, VectorStore
from app.infrastructure.rag.embeddings import build_embedding_provider
from app.infrastructure.rag.vector_stores.factory import build_vector_store


class RagService:
    """知识库与 RAG 查询的统一入口。"""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        llm_service: LLMService | None = None,
    ) -> None:
        # 依赖注入优先，方便单元测试替换向量存储与向量化实现。
        self.uow = uow
        self.vector_store = vector_store or build_vector_store(uow.db_session)
        self.embedding = embedding_provider or build_embedding_provider()
        # 视觉模型仅在多模态摄取时使用，懒加载配置。
        self._llm_service = llm_service

    @property
    def llm_service(self) -> LLMService:
        if self._llm_service is None:
            self._llm_service = LLMService()
        return self._llm_service

    # ===================== 第1步：知识库生命周期 =====================
    async def create_knowledge_base(
        self,
        *,
        name: str,
        description: str = "",
        project_id: str = "default",
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeBase:
        clean_name = name.strip()
        if not clean_name:
            raise AppException(message="knowledge base name is required", code=400, status_code=400)
        size = chunk_size or settings.rag_chunk_size
        overlap = chunk_overlap if chunk_overlap is not None else settings.rag_chunk_overlap
        if size <= 0 or overlap < 0 or overlap >= size:
            raise AppException(
                message="invalid chunking config: overlap must be in [0, chunk_size)",
                code=400,
                status_code=400,
            )
        knowledge_base = await self.uow.knowledge_bases.add(
            name=clean_name,
            description=description.strip(),
            project_id=project_id,
            embedding_provider=self.embedding.provider_name,
            embedding_model=self.embedding.model_name,
            embedding_dim=self.embedding.dim,
            chunk_size=size,
            chunk_overlap=overlap,
            metadata=metadata,
        )
        await self.uow.commit()
        return knowledge_base

    async def list_knowledge_bases(
        self,
        *,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        return await self.uow.knowledge_bases.list_active(project_id=project_id, limit=limit)

    async def get_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self.uow.knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            raise AppException(message="knowledge base not found", code=404, status_code=404)
        return knowledge_base

    async def update_knowledge_base(
        self,
        knowledge_base_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeBase:
        updated = await self.uow.knowledge_bases.update(
            knowledge_base_id,
            name=name.strip() if name else None,
            description=description,
            metadata=metadata,
        )
        if updated is None:
            raise AppException(message="knowledge base not found", code=404, status_code=404)
        await self.uow.commit()
        return updated

    async def delete_knowledge_base(self, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self.get_knowledge_base(knowledge_base_id)
        # 先清向量再清事实源：向量库删除失败时整体回滚，不留孤儿索引。
        await self.vector_store.delete_knowledge_base(knowledge_base_id=knowledge_base_id)
        await self.uow.knowledge_chunks.delete_by_knowledge_base(knowledge_base_id)
        deleted = await self.uow.knowledge_bases.soft_delete(knowledge_base_id)
        await self.uow.commit()
        return deleted or knowledge_base

    # ===================== 第1.5步：多模态摄取（图片 → 视觉解析 → 文本入库） =====================
    async def ingest_image_document(
        self,
        knowledge_base_id: UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        title: str = "",
    ) -> KnowledgeDocument:
        """把一张图片解析成结构化文本后走标准摄取管线。

        视觉模型（llm.vision_model，如 qwen-vl-plus）负责 OCR 与图表理解；
        解析结果作为文档内容切分向量化，检索侧与普通文本完全一致。
        """

        clean_type = (content_type or "").split(";")[0].strip().lower()
        if not clean_type.startswith("image/"):
            raise AppException(
                message=f"unsupported image content type: {content_type or 'unknown'}",
                code=400,
                status_code=400,
            )
        if len(data) > settings.max_upload_size:
            raise AppException(
                message="image is too large",
                code=413,
                status_code=413,
            )
        if not self.llm_service.vision_enabled():
            raise AppException(
                message="vision model is not configured; set llm.vision_model in llm.yaml",
                code=503,
                status_code=503,
            )

        extracted = await self.llm_service.vision_extract(
            image_bytes=data,
            content_type=clean_type,
        )
        clean_title = title.strip() or Path(filename).stem or "图片文档"
        return await self.ingest_document(
            knowledge_base_id,
            title=clean_title,
            content=extracted,
            source_type=KnowledgeSourceType.image,
            source_ref=filename,
            metadata={
                "vision_model": self.llm_service.config.llm.vision_model,
                "image_content_type": clean_type,
                "image_bytes": len(data),
            },
        )

    # ===================== 第2步：文档摄取管线 =====================
    async def ingest_document(
        self,
        knowledge_base_id: UUID,
        *,
        title: str,
        content: str,
        source_type: KnowledgeSourceType = KnowledgeSourceType.manual,
        source_ref: str = "",
        metadata: dict[str, object] | None = None,
    ) -> KnowledgeDocument:
        """同步摄取一份文本文档，返回终态（ready 或 failed）。"""

        knowledge_base = await self.get_knowledge_base(knowledge_base_id)
        clean_title = title.strip()
        clean_content = content.strip()
        if not clean_title:
            raise AppException(message="document title is required", code=400, status_code=400)
        if not clean_content:
            raise AppException(message="document content is required", code=400, status_code=400)
        if len(clean_content) > settings.rag_max_document_chars:
            raise AppException(
                message=f"document exceeds {settings.rag_max_document_chars} chars",
                code=413,
                status_code=413,
            )

        # 1. 同库去重：内容指纹相同的文档拒绝重复摄取。
        sha256 = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()
        existing = await self.uow.knowledge_documents.find_by_sha256(
            knowledge_base_id=knowledge_base_id,
            content_sha256=sha256,
        )
        if existing is not None:
            raise AppException(
                message="identical document already exists in this knowledge base",
                code=409,
                status_code=409,
                details={"document_id": str(existing.id)},
            )

        document = await self.uow.knowledge_documents.add(
            knowledge_base_id=knowledge_base_id,
            title=clean_title,
            source_type=source_type,
            source_ref=source_ref,
            content=clean_content,
            content_sha256=sha256,
            metadata=metadata,
        )
        await self.uow.commit()
        return await self._process_document(knowledge_base, document)

    def _plan_chunks(
        self,
        content: str,
        knowledge_base: KnowledgeBase,
    ) -> list[tuple[TextSpan, int | None, str | None]]:
        """决定切分策略：返回 (span, parent_seq, parent_text) 三元组列表。

        父文档开关开启且文本超过父块大小时走两级切分（small-to-big）：
        子块是向量索引的检索单元，父块全文记在 parent_text 里作为
        上下文窗口；子块大小/重叠沿用知识库创建时冻结的配置。
        短文本走传统单级切分，与存量数据行为完全一致。
        """
        if settings.rag_parent_enabled and len(content) > settings.rag_parent_size:
            groups = split_with_parents(
                content,
                parent_size=settings.rag_parent_size,
                child_size=knowledge_base.chunk_size,
                child_overlap=knowledge_base.chunk_overlap,
            )
            return [
                (child, group.parent_seq, group.parent.content)
                for group in groups
                for child in group.children
            ]
        return [
            (
                span,
                None,
                None,
            )
            for span in split_text(
                content,
                chunk_size=knowledge_base.chunk_size,
                chunk_overlap=knowledge_base.chunk_overlap,
            )
        ]

    async def _process_document(
        self,
        knowledge_base: KnowledgeBase,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        """执行切分、向量化与索引写入，任何失败都会标记 failed。"""

        await self.uow.knowledge_documents.set_status(
            document.id, status=KnowledgeDocumentStatus.processing
        )
        await self.uow.commit()
        try:
            # 2. 按知识库冻结的切分配置生成 chunk（长文自动走父文档两级切分）。
            planned = self._plan_chunks(document.content, knowledge_base)
            if not planned:
                raise AppException(
                    message="document produced no chunks", code=422, status_code=422
                )
            chunks = [
                KnowledgeChunk(
                    id=uuid4(),
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    seq=index,
                    content=span.content,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    token_estimate=span.token_estimate,
                    parent_seq=parent_seq,
                    metadata={
                        "title": document.title,
                        # 父块全文随子块落库：检索命中后零额外查询即可拼回上下文。
                        **({PARENT_TEXT_KEY: parent_text} if parent_text else {}),
                    },
                )
                for index, (span, parent_seq, parent_text) in enumerate(planned)
            ]

            # 3. 批量向量化，再写入向量存储。
            embeddings = await self.embedding.embed_texts([chunk.content for chunk in chunks])
            await self.vector_store.ensure_ready(
                knowledge_base_id=knowledge_base.id,
                embedding_dim=len(embeddings[0]),
            )
            stored_chunks = await self.uow.knowledge_chunks.add_many(chunks)
            await self.vector_store.upsert(
                [
                    VectorRecord(
                        chunk_id=chunk.id,
                        document_id=document.id,
                        knowledge_base_id=knowledge_base.id,
                        embedding=embedding,
                        metadata={"seq": chunk.seq},
                    )
                    for chunk, embedding in zip(stored_chunks, embeddings, strict=True)
                ]
            )

            # 4. 标记 ready 并刷新知识库统计。
            ready = await self.uow.knowledge_documents.set_status(
                document.id,
                status=KnowledgeDocumentStatus.ready,
                chunk_count=len(stored_chunks),
                error="",
            )
            await self._refresh_statistics(knowledge_base.id)
            await self.uow.commit()
            return ready or document
        except Exception as exc:
            await self.uow.rollback()
            message = exc.message if isinstance(exc, AppException) else f"{type(exc).__name__}: {exc}"
            failed = await self.uow.knowledge_documents.set_status(
                document.id,
                status=KnowledgeDocumentStatus.failed,
                chunk_count=0,
                error=message[:2000],
            )
            await self.uow.commit()
            return failed or document

    async def reingest_document(self, document_id: UUID) -> KnowledgeDocument:
        """失败或过期文档的重建入口：先清旧索引，再走完整摄取管线。"""

        document = await self._require_document(document_id)
        knowledge_base = await self.get_knowledge_base(document.knowledge_base_id)
        await self.vector_store.delete_document(
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
        )
        await self.uow.knowledge_chunks.delete_by_document(document.id)
        await self.uow.commit()
        return await self._process_document(knowledge_base, document)

    async def list_documents(
        self,
        knowledge_base_id: UUID,
        *,
        status: KnowledgeDocumentStatus | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        await self.get_knowledge_base(knowledge_base_id)
        return await self.uow.knowledge_documents.list_by_knowledge_base(
            knowledge_base_id, status=status, limit=limit
        )

    async def delete_document(self, document_id: UUID) -> KnowledgeDocument:
        document = await self._require_document(document_id)
        await self.vector_store.delete_document(
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
        )
        await self.uow.knowledge_chunks.delete_by_document(document.id)
        deleted = await self.uow.knowledge_documents.delete(document.id)
        await self._refresh_statistics(document.knowledge_base_id)
        await self.uow.commit()
        return deleted or document

    # ===================== 第3步：检索与引用生成 =====================
    async def query(
        self,
        knowledge_base_id: UUID,
        *,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        record_trace: bool = True,
    ) -> RagQueryResult:
        """多查询扩展 + 向量召回 + RRF 融合 + 重排，返回带引用与置信度的上下文。

        管线：查询改写（LLM 多查询 / 规则降级）→ 逐查询向量召回 →
        RRF 融合 → 词法信号 → 重排（LLM listwise / 词法降级）→
        权重融合（0.5/0.3/0.2，重排缺失时回退 0.7/0.3）→ 父块上下文扩展 →
        字符预算裁剪 → [编号] 引用 + 置信度 → retrieval trace 审计。
        纯计算部分（融合/打分/元数据）落在 domain.rag.retrieval 模块。
        """
        started_at = time.perf_counter()
        knowledge_base = await self.get_knowledge_base(knowledge_base_id)
        clean_query = " ".join(query.split())
        if not clean_query:
            raise AppException(message="query is required", code=400, status_code=400)
        limit = top_k or settings.rag_top_k
        threshold = min_score if min_score is not None else settings.rag_min_score
        search_llm = self._search_llm()

        # 1. 查询改写与多查询扩展（无 LLM 时自动降级为规则改写）。
        if settings.rag_query_expand_enabled and settings.rag_query_expand_variants > 0:
            expanded = await expand_query(
                clean_query,
                search_llm,
                max_variants=settings.rag_query_expand_variants,
            )
        else:
            expanded = ExpandedQuery(original=clean_query)
        queries = expanded.all_queries

        # 2. 逐查询向量召回（候选数大于 top_k，留给融合与重排空间）。
        recall_limit = max(limit, settings.rag_candidate_limit)
        recall_lists: list[list[VectorMatch]] = []
        best_vector: dict[UUID, float] = {}
        for candidate_query in queries:
            embedding = await self.embedding.embed_query(candidate_query)
            matches = await self.vector_store.query(
                knowledge_base_id=knowledge_base_id,
                embedding=embedding,
                top_k=recall_limit,
            )
            recall_lists.append(matches)
            for match in matches:
                best_vector[match.chunk_id] = max(
                    best_vector.get(match.chunk_id, 0.0), match.score
                )

        # 3. RRF 融合 + 回读正文，逐候选打粗排分（纯计算在 retrieval 模块）。
        candidate_ids, fusion, multi_query = fuse_recall_scores(
            recall_lists, k=settings.rag_rrf_k
        )
        chunk_map = {
            chunk.id: chunk
            for chunk in await self.uow.knowledge_chunks.get_many(candidate_ids)
        }
        documents: dict[UUID, KnowledgeDocument] = {}
        for chunk in chunk_map.values():
            if chunk.document_id in documents:
                continue
            document = await self.uow.knowledge_documents.get(chunk.document_id)
            if document is not None:
                documents[chunk.document_id] = document
        query_terms: set[str] = set()
        for candidate_query in queries:
            query_terms |= tokenize_mixed_text(candidate_query)
        scored = score_retrieval_candidates(
            chunk_map=chunk_map,
            documents=documents,
            candidate_ids=candidate_ids,
            best_vector=best_vector,
            fusion=fusion,
            query_terms=query_terms,
            knowledge_base_id=knowledge_base_id,
            multi_query=multi_query,
        )
        source_chunks = {item.chunk_id: chunk_map[item.chunk_id] for item in scored}

        # 4. 重排：LLM listwise 优先，无 LLM（或调用失败）时降级词法信号。
        rerank_applied = False
        if settings.rag_rerank_enabled and scored:
            rerank_llm = search_llm if settings.rag_rerank_use_llm else None
            scored = await rerank_chunks(
                clean_query, scored, rerank_llm, top_n=settings.rag_rerank_top_n
            )
            rerank_applied = True

        # 5. 融合最终分并做阈值过滤（重排缺失的候选回退 0.7/0.3 旧公式）。
        qualified: list[RetrievedChunk] = []
        for item in scored:
            item.final_score = blend_final_score(
                item,
                multi_query=multi_query,
                vector_weight=settings.rag_weight_vector,
                lexical_weight=settings.rag_weight_lexical,
                rerank_weight=settings.rag_weight_rerank,
            )
            if item.final_score >= threshold:
                qualified.append(item)
        qualified.sort(key=lambda item: item.final_score, reverse=True)

        # 6. 父文档上下文扩展（small-to-big）：命中子块 → 父块窗口。
        parent_expanded = False
        if settings.rag_parent_enabled:
            document_cache: dict[UUID, dict[int, KnowledgeChunk]] = {}
            for item in qualified[:limit]:
                chunk = source_chunks.get(item.chunk_id)
                if chunk is None:
                    continue
                if item.document_id not in document_cache:
                    document_cache[item.document_id] = await self._load_document_chunks(
                        chunk.document_id
                    )
                expanded_content = expand_to_parent_context(
                    chunk,
                    document_cache[item.document_id],
                    neighbor_count=settings.rag_parent_neighbor_expand,
                )
                if expanded_content != item.content:
                    item.content = expanded_content
                    parent_expanded = True

        # 7. 引用置信度：相关分 × 文档新鲜度 × 来源类型加权。
        for item in qualified[:limit]:
            document = documents[item.document_id]
            item.confidence = confidence_score(
                item.final_score,
                source_type=document.source_type,
                updated_at=document.updated_at,
                freshness_half_life_days=settings.rag_confidence_freshness_half_life_days,
            )

        # 8. 字符预算裁剪 + 生成 [编号] 引用。
        included: list[RetrievedChunk] = []
        used_chars = 0
        for item in qualified:
            if len(included) >= limit:
                break
            remaining = settings.rag_max_context_chars - used_chars
            if remaining <= 0:
                break
            content = item.content
            if len(content) > remaining:
                if remaining <= 12:
                    break
                content = content[: remaining - 9] + "...[已裁剪]"
            item.content = content
            item.citation = f"[{len(included) + 1}] {item.document_title} · chunk#{item.seq}"
            included.append(item)
            used_chars += len(content)
        context_lines = [
            f"[{index + 1}] （{item.document_title}）{item.content}"
            for index, item in enumerate(included)
        ]
        weights = (
            {
                "vector": settings.rag_weight_vector,
                "lexical": settings.rag_weight_lexical,
                "rerank": settings.rag_weight_rerank,
            }
            if rerank_applied
            else {"vector": 0.7, "lexical": 0.3}
        )
        result = RagQueryResult(
            query=clean_query[:1000],
            knowledge_base_id=knowledge_base_id,
            backend=self.vector_store.backend_name,
            embedding_provider=self.embedding.provider_name,
            top_k=limit,
            candidate_count=len(candidate_ids),
            chunks=included,
            total_chars=used_chars,
            context_text="\n".join(context_lines),
            retrieval_metadata=build_retrieval_metadata(
                elapsed_ms=(time.perf_counter() - started_at) * 1000,
                candidate_count=len(candidate_ids),
                queries=queries,
                expand_method=(
                    expanded.method
                    if settings.rag_query_expand_enabled and queries
                    else "disabled"
                ),
                rrf_k=settings.rag_rrf_k if multi_query else None,
                rerank_applied=rerank_applied,
                rerank_top_n=settings.rag_rerank_top_n,
                parent_expanded=parent_expanded,
                weights=weights,
            ),
        )

        # 9. 写入 retrieval trace，与记忆检索共用一条审计链路。
        if record_trace and hasattr(self.uow, "control_plane"):
            await self.uow.control_plane.record_retrieval_trace(
                build_trace_payload(
                    project_id=knowledge_base.project_id,
                    query=result.query,
                    backend=self.vector_store.backend_name,
                    embedding_provider=self.embedding.provider_name,
                    embedding_model=self.embedding.model_name,
                    knowledge_base_id=knowledge_base_id,
                    queries=queries,
                    expand_method=expanded.method,
                    rrf_k=settings.rag_rrf_k,
                    multi_query=multi_query,
                    rerank_applied=rerank_applied,
                    rerank_top_n=settings.rag_rerank_top_n,
                    weights=weights,
                    candidates=scored[: settings.rag_candidate_limit],
                    selected=[str(item.chunk_id) for item in included],
                    token_budget=settings.rag_max_context_chars // 4,
                )
            )
            await self.uow.commit()
        return result

    # ===================== 第4步：运行状态 =====================
    async def health(self) -> dict[str, dict[str, object]]:
        store_health = await self.vector_store.health()
        return {
            "vector_store": store_health,
            "embedding": {
                "provider": self.embedding.provider_name,
                "model": self.embedding.model_name,
                "dim": self.embedding.dim,
            },
            "chunking": {
                "default_chunk_size": settings.rag_chunk_size,
                "default_chunk_overlap": settings.rag_chunk_overlap,
            },
        }

    async def _refresh_statistics(self, knowledge_base_id: UUID) -> None:
        document_count = await self.uow.knowledge_documents.count_by_knowledge_base(
            knowledge_base_id
        )
        chunk_count = await self.uow.knowledge_chunks.count_by_knowledge_base(knowledge_base_id)
        await self.uow.knowledge_bases.refresh_statistics(
            knowledge_base_id,
            document_count=document_count,
            chunk_count=chunk_count,
        )

    async def _require_document(self, document_id: UUID) -> KnowledgeDocument:
        document = await self.uow.knowledge_documents.get(document_id)
        if document is None:
            raise AppException(message="document not found", code=404, status_code=404)
        return document

    def _search_llm(self) -> LLMService | None:
        """检索增强用的 LLM：未配置密钥或加载失败时返回 None。

        返回 None 时查询改写与重排自动降级到纯本地策略（规则改写/
        词法信号），检索链路不依赖外部模型可用性。测试注入的 fake
        没有 is_configured 方法时按可用处理，交给其自身行为。
        """
        if self._llm_service is None:
            try:
                self._llm_service = LLMService()
            except AppException:
                return None
        llm = self._llm_service
        is_configured = getattr(llm, "is_configured", None)
        if is_configured is None or is_configured():
            return llm
        return None

    async def _load_document_chunks(self, document_id: UUID) -> dict[int, KnowledgeChunk]:
        """回读文档全部 chunk（seq → chunk），供父块拼回与邻块扩展。

        老版本 fake 仓库没有 get_by_document 时返回空表，父文档扩展
        降级为仅使用子块 metadata 里冻结的父块文本。
        """
        getter = getattr(self.uow.knowledge_chunks, "get_by_document", None)
        if getter is None:
            return {}
        chunks = await getter(document_id)
        return {chunk.seq: chunk for chunk in chunks}
        return terms
