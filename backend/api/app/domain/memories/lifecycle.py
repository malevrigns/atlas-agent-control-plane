"""记忆衰减与巩固（Decay & Consolidation）。

长期记忆如果只增不减，上下文会越来越被陈旧事实污染。这里实现
艾宾浩斯式遗忘曲线：

    new_confidence = confidence * exp(-λ * days_since_last_access)

λ 按记忆类型区分：偏好最稳定（λ=0.005），一般事实居中（λ=0.01），
事件类经验遗忘最快（λ=0.05）。时间锚点优先取 ``last_accessed_at``
（检索命中统计），没有命中记录时退回 ``created_at``。

巩固机制则与之互补：被检索命中 ≥3 次且已经过写入门禁验证的记忆，
其 authority 从 ``suggested`` 晋升为 ``verified``，同时把置信度抬到
巩固下限，表示这条记忆已经被反复使用佐证过。
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import UUID

from app.core.config import Settings, settings as global_settings
from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryStatus,
)
from app.domain.memories.repositories import AgentMemoryRepository

# ===================== 衰减系数按记忆类型分组 =====================
# 偏好类：用户偏好长期稳定，衰减最慢。
_PREFERENCE_KINDS: frozenset[MemoryKind] = frozenset({MemoryKind.user_preference})
# 事件类：情景记忆、任务经验、缺陷教训都是“当时有效”的经验，衰减最快。
_EVENT_KINDS: frozenset[MemoryKind] = frozenset(
    {MemoryKind.episode, MemoryKind.task_experience, MemoryKind.bug_lesson}
)
# 其余类型（项目事实、代码事实、约束、决策等）按一般事实处理。

_SECONDS_PER_DAY = 86400


@dataclass(slots=True)
class MemoryDecayRecord:
    """单条记忆的衰减结果，用于生命周期报告。"""

    memory_id: UUID
    kind: MemoryKind
    old_confidence: float
    new_confidence: float


@dataclass(slots=True)
class MemoryLifecycleReport:
    """一次生命周期扫描（衰减 + 巩固）的汇总报告。"""

    scanned: int = 0
    decayed: list[MemoryDecayRecord] = field(default_factory=list)
    consolidated: list[UUID] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """是否有任何记忆被实际修改。"""
        return bool(self.decayed or self.consolidated)


class MemoryLifecycleService:
    """记忆衰减与巩固服务。

    依赖只有领域层的 ``AgentMemoryRepository`` 协议和一个可选的
    ``commit`` 回调（由应用层传入 ``uow.commit``），因此既可以被
    后台定时任务调度，也可以在应用服务内按需调用。
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
        # 未注入 settings 时回退到全局配置对象，保证独立构造也能工作。
        # （参数名 settings 遮蔽了模块级导入，必须用别名。）
        self.settings = settings if settings is not None else global_settings

    # ===================== 第1步：艾宾浩斯式衰减 =====================
    def decay_lambda(self, kind: MemoryKind) -> float:
        """返回该记忆类型对应的衰减系数 λ。"""
        if kind in _PREFERENCE_KINDS:
            return self.settings.memory_decay_lambda_preference
        if kind in _EVENT_KINDS:
            return self.settings.memory_decay_lambda_event
        return self.settings.memory_decay_lambda_fact

    def decay_confidence(self, memory: AgentMemory, *, now: datetime | None = None) -> float:
        """按 ``confidence * exp(-λ * days_since_last_access)`` 计算衰减后的置信度。

        时间锚点优先级：last_accessed_at > created_at > valid_from > now。
        从未被命中过的记忆按创建时间开始遗忘。
        """
        current_time = now or datetime.now(UTC)
        base = max(0.0, min(1.0, memory.confidence))
        anchor = memory.last_accessed_at or memory.created_at or memory.valid_from
        if anchor is None:
            return base
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        days = max((current_time - anchor).total_seconds() / _SECONDS_PER_DAY, 0.0)
        return base * math.exp(-self.decay_lambda(memory.kind) * days)

    async def apply_decay(
        self,
        all_memories: list[AgentMemory],
        *,
        now: datetime | None = None,
        min_drop: float | None = None,
    ) -> MemoryLifecycleReport:
        """对给定记忆批量应用衰减，只写回变化幅度超过阈值的记录。

        已软删除的记忆跳过；单次衰减幅度小于 ``min_drop``（默认读取
        ``settings.memory_decay_min_drop``）时不写库，避免无意义更新。
        """
        current_time = now or datetime.now(UTC)
        threshold = (
            self.settings.memory_decay_min_drop if min_drop is None else min_drop
        )
        report = MemoryLifecycleReport(scanned=len(all_memories))
        for memory in all_memories:
            if memory.deleted_at is not None:
                continue
            new_confidence = max(
                self.decay_confidence(memory, now=current_time),
                self.settings.memory_decay_floor,
            )
            drop = memory.confidence - new_confidence
            if drop < threshold:
                continue
            updated = await self.repository.update(
                memory.id, confidence=round(new_confidence, 4)
            )
            if updated is None:
                continue
            report.decayed.append(
                MemoryDecayRecord(
                    memory_id=memory.id,
                    kind=memory.kind,
                    old_confidence=memory.confidence,
                    new_confidence=updated.confidence,
                )
            )
        if report.decayed and self.commit is not None:
            await self.commit()
        return report

    # ===================== 第2步：检索命中驱动的巩固 =====================
    @staticmethod
    def is_consolidation_eligible(
        memory: AgentMemory, *, min_accesses: int = 3
    ) -> tuple[bool, list[str]]:
        """判断记忆是否满足巩固条件，返回 (是否满足, 不满足的原因)。

        条件：被检索命中 ≥ min_accesses 次、已通过写入门禁（status
        为 verified 且带有来源 provenance）、当前 authority 仍是
        suggested（agent_inferred 需要外部证据复验，不参与自动晋升）。
        """
        if memory.access_count < min_accesses:
            return False, [f"检索命中次数不足（{memory.access_count}/{min_accesses}）"]
        if memory.status is not MemoryStatus.verified:
            return False, ["记忆状态不是 verified"]
        if not memory.provenance:
            return False, ["缺少来源 provenance，无法视为通过验证"]
        if memory.authority is not MemoryAuthority.suggested:
            return False, [f"当前权威度 {memory.authority.value} 无需巩固晋升"]
        return True, []

    async def consolidate(
        self,
        memory: AgentMemory,
        *,
        now: datetime | None = None,
    ) -> AgentMemory | None:
        """把满足条件的记忆 authority 从 suggested 晋升为 verified。

        不满足条件时返回 None（不做任何写库）。巩固同时会把置信度
        抬到 ``memory_consolidation_confidence`` 下限，并写入审计事件。
        """
        eligible, _ = self.is_consolidation_eligible(
            memory,
            min_accesses=self.settings.memory_consolidation_min_accesses,
        )
        if not eligible:
            return None
        current_time = now or datetime.now(UTC)
        metadata = dict(memory.metadata)
        metadata["consolidated_at"] = current_time.isoformat()
        updated = await self.repository.update(
            memory.id,
            authority=MemoryAuthority.verified,
            confidence=max(
                memory.confidence, self.settings.memory_consolidation_confidence
            ),
            metadata=metadata,
        )
        if updated is not None:
            await self.repository.record_audit_event(
                memory_id=memory.id,
                event_type="memory_consolidated",
                payload={
                    "access_count": memory.access_count,
                    "from_authority": MemoryAuthority.suggested.value,
                    "to_authority": MemoryAuthority.verified.value,
                    "consolidated_at": current_time.isoformat(),
                },
            )
            if self.commit is not None:
                await self.commit()
        return updated

    # ===================== 第3步：供后台定时任务调度的入口 =====================
    async def run_lifecycle(self, *, now: datetime | None = None) -> MemoryLifecycleReport:
        """扫描全部未删除记忆，先批量衰减再逐条尝试巩固。

        这个方法设计上可被外部调度（应用启动时注册的后台循环），
        单次执行失败不影响下一次调度。
        """
        memories = await self.repository.list_for_lifecycle(
            limit=self.settings.memory_lifecycle_limit
        )
        report = await self.apply_decay(memories, now=now)
        for memory in memories:
            eligible, _ = self.is_consolidation_eligible(
                memory,
                min_accesses=self.settings.memory_consolidation_min_accesses,
            )
            if not eligible:
                continue
            updated = await self.consolidate(memory, now=now)
            if updated is not None:
                report.consolidated.append(updated.id)
        return report
