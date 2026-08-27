"""检索管线纯计算核心：RRF 融合、粗排打分、最终分融合、审计载荷。

把 RagService.query 里的纯计算逻辑集中到这里（不碰任何 I/O）：
服务层只负责编排（向量召回、正文回读、提交事务），本模块全部是
确定性纯函数，方便单元测试与行为复现。
"""

from uuid import UUID

from app.domain.rag.entities import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    RetrievedChunk,
)
from app.domain.rag.query_processing import (
    reciprocal_rank_fuse,
    tokenize_mixed_text,
)
from app.domain.rag.vector_store import VectorMatch


def fuse_recall_scores(
    recall_lists: list[list[VectorMatch]], *, k: int
) -> tuple[list[UUID], dict[UUID, float], bool]:
    """RRF 融合多查询召回结果。

    返回 (候选 id 有序列表, 归一化融合分 {id: 0-1}, 是否多查询)；
    归一化以最高融合分为 1，供与原始余弦分做等权混合。
    """

    fused = reciprocal_rank_fuse(
        [[match.chunk_id for match in ranked] for ranked in recall_lists], k=k
    )
    max_rrf = fused[0][1] if fused else 0.0
    fusion = {
        chunk_id: score / max_rrf if max_rrf > 0 else 0.0
        for chunk_id, score in fused
    }
    return [chunk_id for chunk_id, _ in fused], fusion, len(recall_lists) > 1


def score_retrieval_candidates(
    *,
    chunk_map: dict[UUID, KnowledgeChunk],
    documents: dict[UUID, KnowledgeDocument],
    candidate_ids: list[UUID],
    best_vector: dict[UUID, float],
    fusion: dict[UUID, float],
    query_terms: set[str],
    knowledge_base_id: UUID,
    multi_query: bool,
) -> list[RetrievedChunk]:
    """逐候选打粗排分（向量/融合/词法），过滤不可用候选。

    - 向量库回链缺失、文档缺失、文档非 ready 的候选直接跳过
      （半成品文档绝不进入引用链）；
    - 词法重叠作为第二信号，缓解纯向量召回的"高分幻觉"；
    - 返回的 RetrievedChunk.final_score 为 0，由
      ``blend_final_score`` 在重排之后统一填充。
    """

    query_weight = min(sum(max(len(term), 1) for term in query_terms) or 1, 40)
    scored: list[RetrievedChunk] = []
    for chunk_id in candidate_ids:
        chunk = chunk_map.get(chunk_id)
        if chunk is None:
            continue
        document = documents.get(chunk.document_id)
        if document is None or document.status is not KnowledgeDocumentStatus.ready:
            continue
        chunk_terms = tokenize_mixed_text(chunk.content)
        matched = sorted(
            query_terms & chunk_terms, key=lambda term: (-len(term), term)
        )[:12]
        matched_weight = sum(max(len(term), 1) for term in matched)
        lexical_score = min(matched_weight / query_weight, 1.0)
        raw_vector = best_vector.get(chunk_id, 0.0)
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                knowledge_base_id=knowledge_base_id,
                document_title=document.title,
                seq=chunk.seq,
                content=chunk.content,
                vector_score=round(raw_vector, 4),
                lexical_score=round(lexical_score, 4),
                final_score=0.0,
                matched_terms=matched,
                fusion_score=round(fusion.get(chunk_id, 0.0), 4)
                if multi_query
                else None,
            )
        )
    return scored


def vector_component_of(item: RetrievedChunk, *, multi_query: bool) -> float:
    """向量信号：单查询=原始余弦分；多查询=余弦分与 RRF 归一化分各半。"""

    if not multi_query:
        return item.vector_score
    return 0.5 * item.vector_score + 0.5 * (item.fusion_score or 0.0)


def blend_final_score(
    item: RetrievedChunk,
    *,
    multi_query: bool,
    vector_weight: float,
    lexical_weight: float,
    rerank_weight: float,
) -> float:
    """最终分融合：0.5*向量 + 0.3*词法 + 0.2*重排。

    候选未参与重排（top_n 之外或重排关闭）时回退旧公式
    0.7*向量 + 0.3*词法，保持历史行为兼容。
    """

    component = vector_component_of(item, multi_query=multi_query)
    if item.rerank_score is None:
        return round(component * 0.7 + item.lexical_score * 0.3, 4)
    return round(
        vector_weight * component
        + lexical_weight * item.lexical_score
        + rerank_weight * item.rerank_score,
        4,
    )


def build_retrieval_metadata(
    *,
    elapsed_ms: float,
    candidate_count: int,
    queries: list[str],
    expand_method: str,
    rrf_k: int | None,
    rerank_applied: bool,
    rerank_top_n: int,
    parent_expanded: bool,
    weights: dict[str, float],
) -> dict[str, object]:
    """组装 RagQueryResult.retrieval_metadata（检索过程元数据）。"""

    return {
        "elapsed_ms": round(elapsed_ms, 1),
        "candidate_count": candidate_count,
        "queries": queries,
        "query_expand_method": expand_method,
        "rrf_k": rrf_k,
        "reranked": rerank_applied,
        "rerank_top_n": rerank_top_n if rerank_applied else None,
        "parent_expanded": parent_expanded,
        "weights": weights,
    }


def build_trace_payload(
    *,
    project_id: str,
    query: str,
    backend: str,
    embedding_provider: str,
    embedding_model: str,
    knowledge_base_id: UUID,
    queries: list[str],
    expand_method: str,
    rrf_k: int,
    multi_query: bool,
    rerank_applied: bool,
    rerank_top_n: int,
    weights: dict[str, float],
    candidates: list[RetrievedChunk],
    selected: list[str],
    token_budget: int,
) -> dict[str, object]:
    """组装 retrieval trace 载荷（与记忆检索共用一条审计链路）。"""

    return {
        "task_id": None,
        "project_id": project_id,
        "query": query,
        "plan": {
            "channels": ["vector", "lexical"],
            "backend": backend,
            "embedding": {
                "provider": embedding_provider,
                "model": embedding_model,
            },
            "queries": queries,
            "query_expand_method": expand_method,
            "rrf": {"k": rrf_k, "applied": multi_query},
            "rerank": {"applied": rerank_applied, "top_n": rerank_top_n},
            "weights": weights,
            "knowledge_base_id": str(knowledge_base_id),
        },
        "candidates": [
            {
                "chunk_id": str(item.chunk_id),
                "score": item.final_score,
                "reason": (
                    f"vector={item.vector_score} lexical={item.lexical_score}"
                    + (
                        f" rerank={item.rerank_score}"
                        if item.rerank_score is not None
                        else ""
                    )
                ),
            }
            for item in candidates
        ],
        "selected_memory_ids": selected,
        "token_budget": token_budget,
    }
