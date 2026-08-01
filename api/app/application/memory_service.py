from datetime import UTC, datetime
from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.application.memory_write_gate import MemoryWriteGate
from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)


class MemoryService:
    """长期记忆应用服务。

    第40章只负责“沉淀和管理记忆”：
    - 手动新增记忆。
    - 从会话消息和事件中抽取候选。
    - 启用、禁用、删除记忆。

    第41章再把这些记忆接入上下文检索和 Agent 执行流程。
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.write_gate = MemoryWriteGate()

    # ===================== 第1步：读取长期记忆列表 =====================
    async def list_memories(
        self,
        *,
        kind: MemoryKind | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[AgentMemory]:
        return await self.uow.memories.list_active(
            kind=kind,
            enabled_only=enabled_only,
            limit=limit,
        )

    # ===================== 第2步：手动新增长期记忆 =====================
    async def create_memory(
        self,
        *,
        kind: MemoryKind,
        content: str,
        importance: int = 3,
        source_session_id: UUID | None = None,
        source_event_id: UUID | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
        scope: MemoryScope = MemoryScope.project,
        requested_status: MemoryStatus = MemoryStatus.candidate,
        subject: str = "",
        predicate: str = "states",
        value: dict[str, object] | None = None,
        confidence: float = 0.5,
        authority: MemoryAuthority = MemoryAuthority.explicit_user,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        ttl_seconds: int | None = None,
        provenance: list[str] | None = None,
        supersedes: UUID | None = None,
        sensitivity: MemorySensitivity = MemorySensitivity.internal,
        project_id: str | None = "default",
        task_id: UUID | None = None,
        user_id: str | None = None,
        created_by: str = "api",
        verification: dict[str, object] | None = None,
    ) -> AgentMemory:
        # 1. 清理并校验正文。长期记忆会进入后续上下文，不能保存空内容。
        clean_content = content.strip()
        if not clean_content:
            raise AppException(
                message="memory content is required",
                code=400,
                status_code=400,
            )

        # 2. 重要度统一限制在 1-5。后续检索会把重要度作为排序权重。
        safe_importance = max(1, min(5, importance))

        candidate = MemoryCandidate(
            kind=kind,
            content=clean_content,
            importance=safe_importance,
            reason="API memory proposal",
            source_session_id=source_session_id,
            source_event_id=source_event_id,
            metadata=metadata or {},
            scope=scope,
            subject=subject or clean_content[:160],
            predicate=predicate,
            value=value or {"text": clean_content},
            confidence=confidence,
            authority=authority,
            valid_from=valid_from,
            valid_to=valid_to or expires_at,
            ttl_seconds=ttl_seconds,
            provenance=provenance or self._source_provenance(
                source_session_id, source_event_id
            ),
            sensitivity=sensitivity,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            created_by=created_by,
            verification=verification or {},
        )
        decision = self.write_gate.evaluate(
            candidate,
            requested_status=requested_status,
        )
        if not decision.accepted:
            raise AppException(
                message="memory rejected: " + "; ".join(decision.reasons),
                code=400,
                status_code=400,
            )
        candidate = decision.candidate
        audit_metadata = dict(candidate.metadata)
        audit_metadata["write_gate"] = {
            "requested_status": requested_status.value,
            "result_status": decision.target_status.value,
            "reasons": decision.reasons,
            "redactions": decision.redactions,
        }

        # 3. 写入记忆并提交事务。
        memory = await self.uow.memories.add(
            kind=kind,
            content=candidate.content,
            importance=safe_importance,
            source_session_id=source_session_id,
            source_event_id=source_event_id,
            expires_at=expires_at,
            metadata=audit_metadata,
            scope=candidate.scope,
            status=decision.target_status,
            subject=candidate.subject,
            predicate=candidate.predicate,
            value=candidate.value,
            confidence=candidate.confidence,
            authority=candidate.authority,
            valid_from=candidate.valid_from,
            valid_to=candidate.valid_to,
            ttl_seconds=candidate.ttl_seconds,
            provenance=candidate.provenance,
            supersedes=supersedes,
            sensitivity=candidate.sensitivity,
            project_id=candidate.project_id,
            task_id=candidate.task_id,
            user_id=candidate.user_id,
            created_by=candidate.created_by,
            verification=candidate.verification,
        )
        if supersedes is not None:
            await self.uow.memories.mark_superseded(
                supersedes,
                replacement_id=memory.id,
            )
        await self.uow.commit()
        return memory

    async def verify_memory(
        self,
        memory_id: UUID,
        *,
        provenance: list[str],
        verification: dict[str, object],
        authority: MemoryAuthority,
    ) -> AgentMemory:
        memory = await self.uow.memories.get(memory_id)
        if memory is None:
            raise AppException(message="memory not found", code=404, status_code=404)
        candidate = MemoryCandidate(
            kind=memory.kind,
            content=memory.content,
            importance=memory.importance,
            reason="verification request",
            source_session_id=memory.source_session_id,
            source_event_id=memory.source_event_id,
            metadata=memory.metadata,
            scope=memory.scope,
            subject=memory.subject,
            predicate=memory.predicate,
            value=memory.value,
            confidence=memory.confidence,
            authority=authority,
            valid_from=memory.valid_from,
            valid_to=memory.valid_to,
            ttl_seconds=memory.ttl_seconds,
            provenance=provenance,
            sensitivity=memory.sensitivity,
            project_id=memory.project_id,
            task_id=memory.task_id,
            user_id=memory.user_id,
            created_by=memory.created_by,
            verification=verification,
        )
        decision = self.write_gate.evaluate(
            candidate,
            requested_status=MemoryStatus.verified,
        )
        if decision.target_status is not MemoryStatus.verified:
            raise AppException(
                message="memory verification failed: " + "; ".join(decision.reasons),
                code=422,
                status_code=422,
            )
        updated = await self.uow.memories.update(
            memory_id,
            status=MemoryStatus.verified,
            provenance=decision.candidate.provenance,
            verification=decision.candidate.verification,
            valid_to=decision.candidate.valid_to,
        )
        await self.uow.commit()
        if updated is None:
            raise AppException(message="memory not found", code=404, status_code=404)
        return updated

    # ===================== 第3步：更新长期记忆 =====================
    async def update_memory(
        self,
        memory_id: UUID,
        *,
        content: str | None = None,
        importance: int | None = None,
        enabled: bool | None = None,
        expires_at=None,
        metadata: dict[str, object] | None = None,
    ) -> AgentMemory:
        clean_content = content.strip() if content is not None else None
        if content is not None and not clean_content:
            raise AppException(
                message="memory content is required",
                code=400,
                status_code=400,
            )

        safe_importance = (
            max(1, min(5, importance)) if importance is not None else None
        )
        memory = await self.uow.memories.update(
            memory_id,
            content=clean_content,
            importance=safe_importance,
            enabled=enabled,
            expires_at=expires_at,
            metadata=metadata,
        )
        await self.uow.commit()
        if memory is None:
            raise AppException(
                message="memory not found",
                code=404,
                status_code=404,
            )
        return memory

    # ===================== 第4步：删除长期记忆 =====================
    async def delete_memory(self, memory_id: UUID) -> AgentMemory:
        memory = await self.uow.memories.soft_delete(memory_id)
        await self.uow.commit()
        if memory is None:
            raise AppException(
                message="memory not found",
                code=404,
                status_code=404,
            )
        return memory

    # ===================== 第5步：从会话中抽取长期记忆候选 =====================
    async def extract_candidates(self, session_id: UUID) -> list[MemoryCandidate]:
        """基于规则从会话消息和事件中抽取记忆候选。

        这里故意不直接写入 `agent_memories`：
        长期记忆一旦进入上下文，会影响后续所有任务，所以第40章先让用户确认。
        第41章可以继续接入 LLM 抽取、相似度去重和自动确认策略。
        """

        # 1. 会话不存在时直接返回 404，避免用户以为抽取成功但没有数据。
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        # 2. 读取会话消息和事件。消息更适合抽取用户偏好，事件更适合抽取任务经验。
        messages = await self.uow.session_messages.list_by_session(session_id)
        events = await self.uow.session_events.list_by_session(session_id)

        # 3. 逐条消息应用简单规则。
        candidates: list[MemoryCandidate] = []
        for message in messages:
            candidates.extend(
                self._extract_from_text(
                    text=message.content,
                    source_session_id=session_id,
                    source_event_id=None,
                    source="message",
                )
            )

        # 4. 从工具事件、任务完成事件中抽取“任务经验”。
        for event in events:
            text = " ".join(str(value) for value in event.payload.values())
            candidates.extend(
                self._extract_from_text(
                    text=text,
                    source_session_id=session_id,
                    source_event_id=event.id,
                    source=f"event:{event.type.value}",
                )
            )

        # 5. 简单去重。后续可以升级为 embedding 相似度去重。
        return self._deduplicate_candidates(candidates)

    @staticmethod
    def _source_provenance(
        source_session_id: UUID | None,
        source_event_id: UUID | None,
    ) -> list[str]:
        if source_event_id:
            return [f"event:{source_event_id}"]
        if source_session_id:
            return [f"session:{source_session_id}"]
        return []

    # ===================== 第6步：候选抽取规则 =====================
    def _extract_from_text(
        self,
        *,
        text: str,
        source_session_id: UUID,
        source_event_id: UUID | None,
        source: str,
    ) -> list[MemoryCandidate]:
        clean_text = " ".join(text.strip().split())
        if len(clean_text) < 8:
            return []

        candidates: list[MemoryCandidate] = []

        if self._contains_any(clean_text, ["我喜欢", "我希望", "偏好", "以后", "记住"]):
            candidates.append(
                MemoryCandidate(
                    kind=MemoryKind.user_preference,
                    content=clean_text[:500],
                    importance=4,
                    reason="文本中出现偏好或记住类表达。",
                    source_session_id=source_session_id,
                    source_event_id=source_event_id,
                    metadata={"source": source},
                )
            )

        if self._contains_any(clean_text, ["项目", "架构", "技术栈", "数据库", "前端", "后端"]):
            candidates.append(
                MemoryCandidate(
                    kind=MemoryKind.project_fact,
                    content=clean_text[:500],
                    importance=3,
                    reason="文本中包含项目事实或技术背景。",
                    source_session_id=source_session_id,
                    source_event_id=source_event_id,
                    metadata={"source": source},
                )
            )

        if self._contains_any(clean_text, ["必须", "不要", "不能", "要求", "约束"]):
            candidates.append(
                MemoryCandidate(
                    kind=MemoryKind.constraint,
                    content=clean_text[:500],
                    importance=5,
                    reason="文本中包含长期约束或明确要求。",
                    source_session_id=source_session_id,
                    source_event_id=source_event_id,
                    metadata={"source": source},
                )
            )

        if self._contains_any(clean_text, ["验证", "报错", "修复", "提交", "部署", "经验"]):
            candidates.append(
                MemoryCandidate(
                    kind=MemoryKind.task_experience,
                    content=clean_text[:500],
                    importance=3,
                    reason="文本中包含任务执行经验或排查经验。",
                    source_session_id=source_session_id,
                    source_event_id=source_event_id,
                    metadata={"source": source},
                )
            )

        return candidates

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _deduplicate_candidates(
        candidates: list[MemoryCandidate],
    ) -> list[MemoryCandidate]:
        seen: set[tuple[str, str]] = set()
        result: list[MemoryCandidate] = []
        for candidate in candidates:
            key = (candidate.kind.value, candidate.content)
            if key in seen:
                continue
            seen.add(key)
            result.append(candidate)
        return result[:20]
