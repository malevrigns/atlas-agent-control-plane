import math
import re
from datetime import UTC, datetime
from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.context_engineering.entities import MemoryContext, MemoryContextItem
from app.domain.memories.entities import AgentMemory, MemoryKind
from app.domain.memories.graph import MemoryGraphService


class MemoryRetrievalService:
    """把长期记忆候选压缩成适合当前任务的 MemoryContext。

    第 41 章使用可解释的混合评分：
    - 相关度：当前任务和记忆正文匹配了多少关键词。
    - 重要度：第 40 章保存的 1-5 级重要度。
    - 新鲜度：最近更新的记忆获得少量加分。

    第 43 章可以在不改变 MemoryContext 结构的情况下，把相关度部分
    替换成 embedding、全文检索或模型重排。
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        # 图谱扩展复用同一个数据库会话；事务归属由调用方统一提交。
        self._graph = MemoryGraphService(uow.memories)

    # ===================== 第1步：检索并压缩长期记忆 =====================
    async def retrieve(
        self,
        *,
        query: str,
        limit: int | None = None,
        max_chars: int | None = None,
        max_item_chars: int | None = None,
        now: datetime | None = None,
        project_id: str | None = None,
        task_id=None,
        user_id: str | None = None,
    ) -> MemoryContext:
        """根据当前任务返回少量可注入上下文的长期记忆。"""

        # 1. 统一检索参数。显式参数主要供测试使用，运行时读取全局配置。
        current_time = now or datetime.now(UTC)
        item_limit = limit or settings.context_memory_limit
        total_char_limit = max_chars or settings.context_memory_max_chars
        item_char_limit = max_item_chars or settings.context_memory_item_max_chars

        # 2. 先让数据库过滤禁用、删除和过期记录。
        repository_arguments = {
            "now": current_time,
            "limit": settings.context_memory_candidate_limit,
        }
        if project_id is not None:
            repository_arguments["project_id"] = project_id
        if task_id is not None:
            repository_arguments["task_id"] = task_id
        if user_id is not None:
            repository_arguments["user_id"] = user_id
        candidates = await self.uow.memories.list_retrievable(**repository_arguments)
        memory_by_id = {memory.id: memory for memory in candidates}

        # 3. 计算混合分数，并过滤完全不相关的普通记忆。
        ranked_items = []
        for memory in candidates:
            item = self._rank_memory(
                memory=memory,
                query=query,
                now=current_time,
            )
            if item.relevance_score < settings.context_memory_min_score:
                continue

            # 普通项目事实和任务经验必须与当前任务有关键词交集。
            # 用户偏好和长期约束属于全局记忆，可以在无直接命中时保留。
            is_global_memory = item.kind in {
                MemoryKind.user_preference,
                MemoryKind.constraint,
            }
            if not item.matched_terms and not is_global_memory:
                continue
            ranked_items.append(item)
        ranked_items.sort(
            key=lambda item: (
                item.relevance_score,
                item.importance,
                item.updated_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )

        # 4. 同时应用“条数预算”和“字符预算”。
        included: list[MemoryContextItem] = []
        used_chars = 0
        for item in ranked_items:
            if len(included) >= item_limit:
                break

            remaining_chars = total_char_limit - used_chars
            if remaining_chars <= 0:
                break

            allowed_chars = min(item_char_limit, remaining_chars)
            compressed = self._compress_item(item, allowed_chars)
            if not compressed.content:
                continue

            included.append(compressed)
            used_chars += len(compressed.content)

        # 5. 使用统计：检索命中自动 +1，并刷新 last_accessed_at。
        #    last_accessed_at 是记忆衰减公式的时间锚点，命中越多遗忘越慢。
        for item in included:
            await self._touch_access(item.id, current_time)

        # 6. 图谱关联扩展：对入选记忆顺带取直接关联记忆（深度 1、条数有上限），
        #    让相关事实/经验一起进入上下文；仍受总字符预算约束。
        if settings.memory_graph_expand_enabled:
            related_budget = settings.memory_graph_max_links
            # 已入选的记忆 id，防止图谱邻居与直接命中重复进入上下文。
            included_ids = {item.id for item in included}
            for item in list(included):
                if related_budget <= 0:
                    break
                source = memory_by_id.get(item.id)
                if source is None or not source.related_ids:
                    continue
                neighbors = await self._graph.expand_context(
                    source,
                    depth=settings.memory_graph_expand_depth,
                    limit=related_budget,
                )
                for neighbor in neighbors:
                    if neighbor.id in included_ids:
                        # 该邻居已作为直接命中入选，跳过避免重复。
                        continue
                    if related_budget <= 0 or used_chars >= total_char_limit:
                        break
                    remaining = total_char_limit - used_chars
                    neighbor_item = self._related_item(neighbor, parent=item)
                    compressed = self._compress_item(
                        neighbor_item, min(item_char_limit, remaining)
                    )
                    if not compressed.content:
                        continue
                    included.append(compressed)
                    included_ids.add(neighbor.id)
                    used_chars += len(compressed.content)
                    related_budget -= 1
                    await self._touch_access(neighbor.id, current_time)

        context = MemoryContext(
            query=" ".join(query.split())[:1000],
            items=included,
            candidate_count=len(candidates),
            omitted_count=max(len(candidates) - len(included), 0),
            total_chars=used_chars,
            max_chars=total_char_limit,
        )
        if project_id is not None and hasattr(self.uow, "control_plane"):
            await self.uow.control_plane.record_retrieval_trace({
                "task_id": task_id,
                "project_id": project_id,
                "query": context.query,
                "plan": {
                    "channels": ["metadata", "lexical", "semantic_proxy", "temporal"],
                    "scope": {"project_id": project_id, "task_id": str(task_id) if task_id else None, "user_id": user_id},
                    "weights": {"semantic": 0.30, "lexical": 0.25, "task": 0.15, "authority": 0.10, "confidence": 0.10, "temporal": 0.10},
                },
                "candidates": [
                    {"memory_id": str(item.id), "score": item.relevance_score, "reason": item.reason_retrieved}
                    for item in ranked_items
                ],
                "selected_memory_ids": [str(item.id) for item in included],
                "token_budget": total_char_limit // 4,
            })
        return context

    # ===================== 使用统计与图谱扩展辅助 =====================
    async def _touch_access(self, memory_id: UUID, now: datetime) -> None:
        """记录一次检索命中；测试假仓库未实现该能力时静默跳过。"""
        if not hasattr(self.uow.memories, "touch_access"):
            return
        await self.uow.memories.touch_access(memory_id, now=now)

    @staticmethod
    def _related_item(
        neighbor: AgentMemory,
        *,
        parent: MemoryContextItem,
    ) -> MemoryContextItem:
        """为图谱关联记忆构建上下文条目。

        相关度按父节点打六折：关联记忆是佐证而非直接命中，排序上
        必须低于真正的查询命中结果。
        """
        return MemoryContextItem(
            id=neighbor.id,
            kind=neighbor.kind,
            content=neighbor.content,
            importance=neighbor.importance,
            relevance_score=round(parent.relevance_score * 0.6, 4),
            matched_terms=[],
            original_chars=len(neighbor.content),
            truncated=False,
            source_session_id=neighbor.source_session_id,
            source_event_id=neighbor.source_event_id,
            updated_at=neighbor.updated_at,
            scope=neighbor.scope.value,
            status=neighbor.status.value,
            confidence=neighbor.confidence,
            authority=neighbor.authority.value,
            provenance=list(neighbor.provenance),
            reason_retrieved=f"graph_link={parent.id}",
        )

    # ===================== 第2步：计算单条记忆的混合分数 =====================
    def _rank_memory(
        self,
        *,
        memory: AgentMemory,
        query: str,
        now: datetime,
    ) -> MemoryContextItem:
        query_terms = self._tokenize(query)
        memory_terms = self._tokenize(memory.content)
        matched_terms = sorted(
            query_terms & memory_terms,
            key=lambda value: (-len(value), value),
        )[:12]

        # 1. 关键词重叠形成主要相关度。较长关键词权重略高。
        # 中文会生成较多 n-gram。如果直接用全部权重做分母，
        # FastAPI、PostgreSQL 这类明确关键词会被大量中文片段稀释。
        query_weight = min(
            sum(max(len(term), 1) for term in query_terms) or 1,
            40,
        )
        matched_weight = sum(max(len(term), 1) for term in matched_terms)
        lexical_score = min(matched_weight / query_weight, 1.0)

        # 2. 用户偏好和长期约束具有跨任务价值，即使没有直接命中关键词，
        #    也给一个很小的基础分，之后仍受数量和字符预算控制。
        global_memory_bonus = (
            0.04
            if memory.kind in {MemoryKind.user_preference, MemoryKind.constraint}
            else 0.0
        )

        # 3. importance 已经是 1-5，归一化到 0-1。
        importance_score = max(1, min(5, memory.importance)) / 5

        # 4. 新鲜度使用平滑衰减。越接近当前时间，分数越接近 1。
        updated_at = memory.updated_at or memory.created_at or now
        age_days = max((now - updated_at).total_seconds() / 86400, 0)
        recency_score = math.exp(-age_days / 90)

        # 5. 权威度、置信度、任务亲和度和时效性共同参与重排。
        authority_score = {
            "explicit_user": 1.0,
            "verified": 1.0,
            "test_verified": 1.0,
            "tool_verified": 0.9,
            "suggested": 0.4,
            "agent_inferred": 0.2,
        }.get(memory.authority.value, 0.2)
        task_affinity = 1.0 if memory.task_id else (0.75 if memory.project_id else 0.5)
        semantic_proxy = lexical_score
        final_score = min(
            semantic_proxy * 0.30
            + lexical_score * 0.25
            + task_affinity * 0.15
            + authority_score * 0.10
            + max(0.0, min(1.0, memory.confidence)) * 0.10
            + recency_score * 0.10
            + importance_score * 0.04
            + global_memory_bonus,
            1.0,
        )

        reason_parts = []
        if matched_terms:
            reason_parts.append("lexical=" + ",".join(matched_terms[:5]))
        if memory.task_id:
            reason_parts.append("same_task")
        elif memory.project_id:
            reason_parts.append("same_project")
        reason_parts.append(f"authority={memory.authority.value}")

        return MemoryContextItem(
            id=memory.id,
            kind=memory.kind,
            content=memory.content,
            importance=memory.importance,
            relevance_score=round(final_score, 4),
            matched_terms=matched_terms,
            original_chars=len(memory.content),
            truncated=False,
            source_session_id=memory.source_session_id,
            source_event_id=memory.source_event_id,
            updated_at=memory.updated_at,
            scope=memory.scope.value,
            status=memory.status.value,
            confidence=memory.confidence,
            authority=memory.authority.value,
            provenance=list(memory.provenance),
            reason_retrieved=" + ".join(reason_parts),
        )

    # ===================== 第3步：按单条字符预算压缩记忆 =====================
    @staticmethod
    def _compress_item(
        item: MemoryContextItem,
        max_chars: int,
    ) -> MemoryContextItem:
        if max_chars <= 0:
            content = ""
        elif len(item.content) <= max_chars:
            content = item.content
        elif max_chars <= 12:
            content = item.content[:max_chars]
        else:
            content = item.content[: max_chars - 9] + "...[已裁剪]"

        return MemoryContextItem(
            id=item.id,
            kind=item.kind,
            content=content,
            importance=item.importance,
            relevance_score=item.relevance_score,
            matched_terms=item.matched_terms,
            original_chars=item.original_chars,
            truncated=len(content) < item.original_chars,
            source_session_id=item.source_session_id,
            source_event_id=item.source_event_id,
            updated_at=item.updated_at,
            scope=item.scope,
            status=item.status,
            confidence=item.confidence,
            authority=item.authority,
            provenance=list(item.provenance or []),
            reason_retrieved=item.reason_retrieved,
        )

    # ===================== 第4步：提取中英文检索词 =====================
    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """提取英文单词和中文 2-4 字片段。

        这是第 41 章的轻量检索实现，不需要额外分词或向量依赖。
        """

        normalized = text.lower()
        terms = set(re.findall(r"[a-z0-9_]+", normalized))
        chinese_blocks = re.findall(r"[\u4e00-\u9fff]+", normalized)
        for block in chinese_blocks:
            for size in (2, 3, 4):
                if len(block) < size:
                    continue
                terms.update(
                    block[index : index + size]
                    for index in range(len(block) - size + 1)
                )
        return terms
