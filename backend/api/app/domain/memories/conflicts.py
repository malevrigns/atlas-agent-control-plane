"""记忆冲突检测与消解（Conflict Resolution）。

同一条事实被新证据改写是最常见的记忆腐化场景：例如旧记忆
"项目使用 SQLite"，后来新记忆说 "项目使用 PostgreSQL"。两者 subject
和 predicate 相同但 value 不同，就是冲突。

冲突判定（``detect_conflicts``）是纯函数，只依赖领域实体；
``MemoryConflictService`` 负责按策略消解并写入审计事件：

- ``latest_wins``（默认）：新记忆胜出，旧记忆标记 superseded。
- ``authority_wins``：权威度更高的记忆胜出，另一方标记 superseded。
- ``manual_review``：不动状态，在双方 metadata 上挂起人工复核标记。

旧记忆的 superseded 标记复用 ``mark_superseded``（superseded_by
替代关系字段），保证与既有的 supersedes 链一致。
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Awaitable, Callable

from app.core.config import Settings, settings as global_settings
from app.domain.memories.entities import AgentMemory, MemoryAuthority, MemoryStatus
from app.domain.memories.repositories import AgentMemoryRepository


class MemoryConflictStrategy(StrEnum):
    """冲突消解策略。"""

    latest_wins = "latest_wins"
    authority_wins = "authority_wins"
    manual_review = "manual_review"


# 权威度高低排序：值越大越可信。
_AUTHORITY_RANK: dict[MemoryAuthority, int] = {
    MemoryAuthority.explicit_user: 5,
    MemoryAuthority.verified: 4,
    MemoryAuthority.tool_verified: 3,
    MemoryAuthority.test_verified: 3,
    MemoryAuthority.suggested: 2,
    MemoryAuthority.agent_inferred: 1,
}


@dataclass(slots=True)
class MemoryConflict:
    """一对 subject/predicate 相同但 value 不同的记忆。"""

    subject: str
    predicate: str
    new_memory: AgentMemory
    existing_memory: AgentMemory
    strategy: MemoryConflictStrategy = MemoryConflictStrategy.latest_wins


def _canonical_value(value: dict[str, object]) -> str:
    """把 value 序列化成稳定字符串用于比较。

    JSON 键序不稳定，必须 sort_keys；非 JSON 可序列化的值退回 str。
    """
    try:
        return json.dumps(value or {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(sorted((value or {}).items(), key=str))


def _memory_time(memory: AgentMemory) -> datetime | None:
    """取记忆用于"谁更新"比较的时间戳。"""
    anchor = memory.updated_at or memory.created_at or memory.valid_from
    if anchor is None:
        return None
    return anchor if anchor.tzinfo else anchor.replace(tzinfo=UTC)


def detect_conflicts(
    new_memory: AgentMemory,
    existing_memories: list[AgentMemory],
) -> list[MemoryConflict]:
    """在存量记忆中找出与新记忆冲突的记录。

    冲突判定：同 subject + 同 predicate 但 value 不同。没有 subject
    的记忆无法定位事实，不参与冲突检测；已软删除或已 superseded
    的记忆是历史版本，不再冲突。
    """
    if not new_memory.subject:
        return []
    new_value = _canonical_value(new_memory.value)
    conflicts: list[MemoryConflict] = []
    for existing in existing_memories:
        if existing.id == new_memory.id:
            continue
        if existing.deleted_at is not None:
            continue
        if existing.status is MemoryStatus.superseded:
            continue
        if existing.subject != new_memory.subject or existing.predicate != new_memory.predicate:
            continue
        if _canonical_value(existing.value) == new_value:
            continue
        conflicts.append(
            MemoryConflict(
                subject=new_memory.subject,
                predicate=new_memory.predicate,
                new_memory=new_memory,
                existing_memory=existing,
            )
        )
    return conflicts


class MemoryConflictService:
    """按策略消解记忆冲突，并留下审计事件。

    与 ``MemoryLifecycleService`` 一样只依赖领域层仓库协议；
    应用层（如 MemoryService.create_memory）复用同一个事务时，
    不传 ``commit``，由调用方统一提交。
    """

    def __init__(
        self,
        repository: AgentMemoryRepository,
        *,
        commit: Callable[[], Awaitable[None]] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.commit = commit
        # 未注入 settings 时回退到全局配置对象；参数名遮蔽模块导入，用别名。
        self.settings = settings if settings is not None else global_settings

    # ===================== 第1步：检测存量冲突 =====================
    async def detect(
        self,
        new_memory: AgentMemory,
        *,
        scan_limit: int | None = None,
    ) -> list[MemoryConflict]:
        """扫描存量记忆，返回与新记忆的全部冲突对。"""
        existing = await self.repository.list_for_lifecycle(
            limit=scan_limit or self.settings.memory_conflict_scan_limit
        )
        return detect_conflicts(new_memory, existing)

    # ===================== 第2步：按策略消解 =====================
    def pick_winner(
        self,
        new_memory: AgentMemory,
        existing_memory: AgentMemory,
        *,
        strategy: MemoryConflictStrategy,
        now: datetime | None = None,
    ) -> tuple[AgentMemory, AgentMemory]:
        """返回 (winner, loser)。

        latest_wins：时间戳更新的胜出，时间戳缺失时新记忆胜出。
        authority_wins：权威度更高的胜出，平级时退回 latest_wins。
        """
        if strategy is MemoryConflictStrategy.authority_wins:
            new_rank = _AUTHORITY_RANK.get(new_memory.authority, 0)
            old_rank = _AUTHORITY_RANK.get(existing_memory.authority, 0)
            if new_rank != old_rank:
                return (
                    (new_memory, existing_memory)
                    if new_rank > old_rank
                    else (existing_memory, new_memory)
                )
        # latest_wins，以及 authority_wins 平级时的回退规则。
        current_time = now or datetime.now(UTC)
        new_time = _memory_time(new_memory) or current_time
        old_time = _memory_time(existing_memory) or current_time
        if new_time >= old_time:
            return new_memory, existing_memory
        return existing_memory, new_memory

    async def resolve(
        self,
        new_memory: AgentMemory,
        *,
        strategy: MemoryConflictStrategy | str | None = None,
        now: datetime | None = None,
    ) -> list[MemoryConflict]:
        """检测并消解新记忆与存量记忆的全部冲突。

        manual_review 策略不改变任何状态，只在双方 metadata 上写入
        conflict_review 标记并留审计事件；其余策略把 loser 标记为
        superseded（复用替代关系字段），同样写审计事件。
        """
        resolved_strategy = (
            MemoryConflictStrategy(strategy)
            if strategy is not None
            else MemoryConflictStrategy(self.settings.memory_conflict_strategy)
        )
        current_time = now or datetime.now(UTC)
        conflicts = await self.detect(new_memory)
        for conflict in conflicts:
            conflict.strategy = resolved_strategy
            await self._resolve_one(conflict, now=current_time)
        if conflicts and self.commit is not None:
            await self.commit()
        return conflicts

    # ===================== 第3步：单条冲突消解 =====================
    async def _resolve_one(
        self,
        conflict: MemoryConflict,
        *,
        now: datetime,
    ) -> None:
        if conflict.strategy is MemoryConflictStrategy.manual_review:
            marker = {
                "subject": conflict.subject,
                "predicate": conflict.predicate,
                "counterpart_id": str(conflict.existing_memory.id),
                "detected_at": now.isoformat(),
            }
            for memory in (conflict.new_memory, conflict.existing_memory):
                metadata = dict(memory.metadata)
                metadata["conflict_review"] = marker
                await self.repository.update(memory.id, metadata=metadata)
            await self.repository.record_audit_event(
                memory_id=conflict.new_memory.id,
                event_type="memory_conflict_manual_review",
                payload={
                    "subject": conflict.subject,
                    "predicate": conflict.predicate,
                    "counterpart_id": str(conflict.existing_memory.id),
                    "strategy": conflict.strategy.value,
                    "resolved_at": now.isoformat(),
                },
            )
            return

        winner, loser = self.pick_winner(
            conflict.new_memory,
            conflict.existing_memory,
            strategy=conflict.strategy,
            now=now,
        )
        await self.repository.mark_superseded(
            loser.id, replacement_id=winner.id
        )
        await self.repository.record_audit_event(
            memory_id=loser.id,
            event_type="memory_conflict_resolved",
            payload={
                "subject": conflict.subject,
                "predicate": conflict.predicate,
                "strategy": conflict.strategy.value,
                "winner_id": str(winner.id),
                "loser_id": str(loser.id),
                "resolved_at": now.isoformat(),
            },
        )
