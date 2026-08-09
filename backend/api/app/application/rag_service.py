"""RAG 应用服务。

负责知识库生命周期与"摄取 → 检索 → 引用"闭环：

- 摄取管线：去重 → 切分 → 向量化 → 写入向量存储 → 标记 ready。
  任何一步失败都会把文档标记为 failed 并记录原因，绝不留下半成品索引。
- 检索管线：查询向量化 → 向量召回 → 词法混合重排 → 预算裁剪 →
  生成带 [编号] 引用的上下文，并写入 retrieval trace 审计。
"""

import hashlib
import re
from uuid import UUID, uuid4

from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.rag.chunking import split_text
from app.domain.rag.embedding import EmbeddingProvider
from app.domain.rag.entities import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeSourceType,
    RagQueryResult,
    RetrievedChunk,
)
from app.domain.rag.vector_store import VectorRecord, VectorStore
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
    ) -> None:
        # 依赖注入优先，方便单元测试替换向量存储与向量化实现。
        self.uow = uow
        self.vector_store = vector_store or build_vector_store(uow.db_session)
        self.embedding = embedding_provider or build_embedding_provider()

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
            # 2. 按知识库冻结的切分配置生成 chunk。
            spans = split_text(
                document.content,
                chunk_size=knowledge_base.chunk_size,
                chunk_overlap=knowledge_base.chunk_overlap,
            )
            if not spans:
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
                    metadata={"title": document.title},
                )
                for index, span in enumerate(spans)
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
        """向量召回 + 词法混合重排，返回带引用的上下文。"""

        knowledge_base = await self.get_knowledge_base(knowledge_base_id)
        clean_query = " ".join(query.split())
        if not clean_query:
            raise AppException(message="query is required", code=400, status_code=400)
        limit = top_k or settings.rag_top_k
        threshold = min_score if min_score is not None else settings.rag_min_score

        # 1. 查询向量化 + 向量召回（候选数大于 top_k，留给重排空间）。
        query_embedding = await self.embedding.embed_query(clean_query)
        matches = await self.vector_store.query(
            knowledge_base_id=knowledge_base_id,
            embedding=query_embedding,
            top_k=max(limit, settings.rag_candidate_limit),
        )

        # 2. 回读 chunk 正文（向量库只存回链，不存正文）。
        chunk_map = {
            chunk.id: chunk
            for chunk in await self.uow.knowledge_chunks.get_many(
                [match.chunk_id for match in matches]
            )
        }
        documents: dict[UUID, KnowledgeDocument] = {}
        query_terms = self._tokenize(clean_query)
        ranked: list[RetrievedChunk] = []
        for match in matches:
            chunk = chunk_map.get(match.chunk_id)
            if chunk is None:
                continue
            document = documents.get(chunk.document_id)
            if document is None:
                document = await self.uow.knowledge_documents.get(chunk.document_id)
                if document is None:
                    continue
                documents[chunk.document_id] = document
            # 只检索 ready 文档，摄取中/失败的内容绝不给模型。
            if document.status is not KnowledgeDocumentStatus.ready:
                continue

            # 3. 词法重叠作为第二信号，缓解纯向量召回的"高分幻觉"。
            chunk_terms = self._tokenize(chunk.content)
            matched = sorted(query_terms & chunk_terms, key=lambda term: (-len(term), term))[:12]
            matched_weight = sum(max(len(term), 1) for term in matched)
            query_weight = min(sum(max(len(term), 1) for term in query_terms) or 1, 40)
            lexical_score = min(matched_weight / query_weight, 1.0)
            final_score = round(match.score * 0.7 + lexical_score * 0.3, 4)
            if final_score < threshold:
                continue
            ranked.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    knowledge_base_id=knowledge_base_id,
                    document_title=document.title,
                    seq=chunk.seq,
                    content=chunk.content,
                    vector_score=round(match.score, 4),
                    lexical_score=round(lexical_score, 4),
                    final_score=final_score,
                    matched_terms=matched,
                )
            )

        ranked.sort(key=lambda item: item.final_score, reverse=True)

        # 4. 字符预算裁剪 + 生成 [编号] 引用。
        included: list[RetrievedChunk] = []
        used_chars = 0
        for item in ranked:
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
        result = RagQueryResult(
            query=clean_query[:1000],
            knowledge_base_id=knowledge_base_id,
            backend=self.vector_store.backend_name,
            embedding_provider=self.embedding.provider_name,
            top_k=limit,
            candidate_count=len(matches),
            chunks=included,
            total_chars=used_chars,
            context_text="\n".join(context_lines),
        )

        # 5. 写入 retrieval trace，与记忆检索共用一条审计链路。
        if record_trace and hasattr(self.uow, "control_plane"):
            await self.uow.control_plane.record_retrieval_trace({
                "task_id": None,
                "project_id": knowledge_base.project_id,
                "query": result.query,
                "plan": {
                    "channels": ["vector", "lexical"],
                    "backend": self.vector_store.backend_name,
                    "embedding": {
                        "provider": self.embedding.provider_name,
                        "model": self.embedding.model_name,
                    },
                    "weights": {"vector": 0.7, "lexical": 0.3},
                    "knowledge_base_id": str(knowledge_base_id),
                },
                "candidates": [
                    {
                        "chunk_id": str(item.chunk_id),
                        "score": item.final_score,
                        "reason": f"vector={item.vector_score} lexical={item.lexical_score}",
                    }
                    for item in ranked[: settings.rag_candidate_limit]
                ],
                "selected_memory_ids": [str(item.chunk_id) for item in included],
                "token_budget": settings.rag_max_context_chars // 4,
            })
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

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """与记忆检索一致的中英文混合分词。"""

        normalized = text.lower()
        terms = set(re.findall(r"[a-z0-9_]+", normalized))
        for block in re.findall(r"[一-鿿]+", normalized):
            for size in (2, 3, 4):
                if len(block) < size:
                    continue
                terms.update(
                    block[index : index + size] for index in range(len(block) - size + 1)
                )
        return terms
