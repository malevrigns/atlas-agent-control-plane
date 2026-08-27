import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import Settings
from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryStatus,
)
from app.domain.memories.lifecycle import (
    MemoryLifecycleReport,
    MemoryLifecycleService,
)


class FakeMemoryRepository:
    """内存版记忆仓库，为生命周期单元测试提供读写能力。"""

    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = {memory.id: memory for memory in memories}
        self.updated: list[dict[str, object]] = []
        self.audit_events: list[dict[str, object]] = []

    async def list_for_lifecycle(self, *, limit: int | None = None) -> list[AgentMemory]:
        items = [m for m in self.memories.values() if m.deleted_at is None]
        return items[:limit] if limit is not None else items

    async def update(
        self,
        memory_id,
        *,
        confidence: float | None = None,
        authority: MemoryAuthority | None = None,
        metadata: dict[str, object] | None = None,
        **_ignored,
    ) -> AgentMemory | None:
        current = self.memories.get(memory_id)
        if current is None:
            return None
        updates: dict[str, object] = {}
        if confidence is not None:
            current.confidence = confidence
            updates["confidence"] = confidence
        if authority is not None:
            current.authority = authority
            updates["authority"] = authority
        if metadata is not None:
            current.metadata = metadata
            updates["metadata"] = metadata
        self.updated.append({"memory_id": memory_id, **updates})
        return current

    async def record_audit_event(
        self, *, memory_id, event_type: str, payload: dict[str, object]
    ) -> UUID:
        self.audit_events.append(
            {"memory_id": memory_id, "event_type": event_type, "payload": payload}
        )
        return uuid4()


def build_memory(
    *,
    kind: MemoryKind = MemoryKind.project_fact,
    confidence: float = 0.9,
    created_days_ago: int = 0,
    last_accessed_days_ago: int | None = None,
    access_count: int = 0,
    authority: MemoryAuthority = MemoryAuthority.explicit_user,
    status: MemoryStatus = MemoryStatus.verified,
    provenance: list[str] | None = None,
) -> AgentMemory:
    now = datetime.now(UTC)
    return AgentMemory(
        id=uuid4(),
        kind=kind,
        content=f"测试记忆 {kind.value}",
        importance=3,
        enabled=True,
        source_session_id=None,
        source_event_id=None,
        expires_at=None,
        status=status,
        confidence=confidence,
        authority=authority,
        provenance=provenance or [],
        created_at=now - timedelta(days=created_days_ago),
        updated_at=now - timedelta(days=created_days_ago),
        access_count=access_count,
        last_accessed_at=(
            None
            if last_accessed_days_ago is None
            else now - timedelta(days=last_accessed_days_ago)
        ),
    )


class DecayConfidenceTest(unittest.TestCase):
    # ===================== 第1步：验证 λ 按记忆类型区分 =====================
    def test_lambda_differs_by_kind(self) -> None:
        service = MemoryLifecycleService(FakeMemoryRepository([]))
        self.assertAlmostEqual(service.decay_lambda(MemoryKind.user_preference), 0.005)
        self.assertAlmostEqual(service.decay_lambda(MemoryKind.project_fact), 0.01)
        self.assertAlmostEqual(service.decay_lambda(MemoryKind.episode), 0.05)
        self.assertAlmostEqual(service.decay_lambda(MemoryKind.task_experience), 0.05)

    # ===================== 第2步：验证衰减公式与类型差异 =====================
    def test_decay_formula(self) -> None:
        now = datetime.now(UTC)
        service = MemoryLifecycleService(FakeMemoryRepository([]))
        memory = build_memory(kind=MemoryKind.project_fact, confidence=0.8, created_days_ago=30)
        # 0.8 * exp(-0.01 * 30) ≈ 0.6000
        expected = 0.8 * (2.718281828459045 ** (-0.01 * 30))
        self.assertAlmostEqual(service.decay_confidence(memory, now=now), expected, places=6)

    def test_preference_decays_slower_than_fact(self) -> None:
        now = datetime.now(UTC)
        service = MemoryLifecycleService(FakeMemoryRepository([]))
        preference = build_memory(
            kind=MemoryKind.user_preference, confidence=0.8, created_days_ago=100
        )
        fact = build_memory(
            kind=MemoryKind.project_fact, confidence=0.8, created_days_ago=100
        )
        self.assertGreater(
            service.decay_confidence(preference, now=now),
            service.decay_confidence(fact, now=now),
        )

    # ===================== 第3步：验证 last_accessed_at 是衰减锚点 =====================
    def test_last_accessed_at_anchors_decay(self) -> None:
        now = datetime.now(UTC)
        service = MemoryLifecycleService(FakeMemoryRepository([]))
        stale = build_memory(kind=MemoryKind.project_fact, confidence=0.8, created_days_ago=90)
        fresh = build_memory(
            kind=MemoryKind.project_fact,
            confidence=0.8,
            created_days_ago=90,
            last_accessed_days_ago=1,
        )
        # 最近被命中的记忆遗忘更慢。
        self.assertGreater(
            service.decay_confidence(fresh, now=now),
            service.decay_confidence(stale, now=now),
        )

    def test_no_anchor_means_no_decay(self) -> None:
        now = datetime.now(UTC)
        service = MemoryLifecycleService(FakeMemoryRepository([]))
        memory = AgentMemory(
            id=uuid4(),
            kind=MemoryKind.project_fact,
            content="没有时间锚点的记忆",
            importance=3,
            enabled=True,
            source_session_id=None,
            source_event_id=None,
            expires_at=None,
            confidence=0.7,
        )
        self.assertEqual(service.decay_confidence(memory, now=now), 0.7)


class ApplyDecayTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第4步：验证 apply_decay 批量写回 =====================
    async def test_apply_decay_updates_confidence(self) -> None:
        now = datetime.now(UTC)
        memory = build_memory(kind=MemoryKind.project_fact, confidence=0.9, created_days_ago=30)
        original_confidence = memory.confidence
        repository = FakeMemoryRepository([memory])
        commits = 0

        async def commit() -> None:
            nonlocal commits
            commits += 1

        service = MemoryLifecycleService(repository, commit=commit)
        report: MemoryLifecycleReport = await service.apply_decay(
            list(repository.memories.values()), now=now
        )

        self.assertEqual(len(report.decayed), 1)
        # 0.9 * exp(-0.01 * 30) ≈ 0.6667
        self.assertAlmostEqual(report.decayed[0].new_confidence, 0.6667, places=3)
        self.assertLess(report.decayed[0].new_confidence, original_confidence)
        self.assertEqual(commits, 1)

    async def test_apply_decay_skips_tiny_drops(self) -> None:
        now = datetime.now(UTC)
        # 刚创建、刚命中过的记忆几乎没有衰减，不应写库。
        memory = build_memory(
            kind=MemoryKind.project_fact,
            confidence=0.9,
            created_days_ago=0,
            last_accessed_days_ago=0,
        )
        repository = FakeMemoryRepository([memory])
        service = MemoryLifecycleService(repository)
        report = await service.apply_decay(list(repository.memories.values()), now=now)
        self.assertEqual(report.decayed, [])
        self.assertEqual(repository.updated, [])
        self.assertFalse(report.changed)

    async def test_apply_decay_skips_deleted_memories(self) -> None:
        now = datetime.now(UTC)
        memory = build_memory(kind=MemoryKind.project_fact, confidence=0.9, created_days_ago=30)
        deleted = replace(memory, deleted_at=now)
        repository = FakeMemoryRepository([deleted])
        service = MemoryLifecycleService(repository)
        report = await service.apply_decay(list(repository.memories.values()), now=now)
        self.assertEqual(report.decayed, [])


class ConsolidateTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第5步：验证巩固晋升 suggested -> verified =====================
    async def test_consolidate_promotes_suggested_to_verified(self) -> None:
        now = datetime.now(UTC)
        memory = build_memory(
            kind=MemoryKind.project_fact,
            confidence=0.55,
            access_count=3,
            authority=MemoryAuthority.suggested,
            provenance=["session:abc"],
        )
        repository = FakeMemoryRepository([memory])
        service = MemoryLifecycleService(repository)
        updated = await service.consolidate(memory, now=now)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.authority, MemoryAuthority.verified)
        self.assertGreaterEqual(updated.confidence, 0.9)
        self.assertIn("consolidated_at", updated.metadata)
        self.assertEqual(len(repository.audit_events), 1)
        self.assertEqual(repository.audit_events[0]["event_type"], "memory_consolidated")

    async def test_consolidate_requires_min_accesses(self) -> None:
        now = datetime.now(UTC)
        memory = build_memory(
            kind=MemoryKind.project_fact,
            access_count=2,
            authority=MemoryAuthority.suggested,
            provenance=["session:abc"],
        )
        repository = FakeMemoryRepository([memory])
        service = MemoryLifecycleService(repository)
        self.assertIsNone(await service.consolidate(memory, now=now))
        self.assertEqual(repository.updated, [])

    async def test_consolidate_requires_verified_status_and_provenance(self) -> None:
        now = datetime.now(UTC)
        candidate = build_memory(
            kind=MemoryKind.project_fact,
            access_count=5,
            authority=MemoryAuthority.suggested,
            status=MemoryStatus.candidate,
            provenance=["session:abc"],
        )
        no_provenance = build_memory(
            kind=MemoryKind.project_fact,
            access_count=5,
            authority=MemoryAuthority.suggested,
            provenance=[],
        )
        repository = FakeMemoryRepository([candidate, no_provenance])
        service = MemoryLifecycleService(repository)
        self.assertIsNone(await service.consolidate(candidate, now=now))
        self.assertIsNone(await service.consolidate(no_provenance, now=now))
        self.assertEqual(repository.updated, [])

    async def test_consolidate_ignores_already_high_authority(self) -> None:
        now = datetime.now(UTC)
        memory = build_memory(
            kind=MemoryKind.project_fact,
            access_count=9,
            authority=MemoryAuthority.explicit_user,
            provenance=["session:abc"],
        )
        eligible, reasons = MemoryLifecycleService.is_consolidation_eligible(memory)
        self.assertFalse(eligible)
        self.assertTrue(reasons)
        repository = FakeMemoryRepository([memory])
        service = MemoryLifecycleService(repository)
        self.assertIsNone(await service.consolidate(memory, now=now))


class RunLifecycleTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第6步：验证 run_lifecycle 可作为后台调度入口 =====================
    async def test_run_lifecycle_decays_and_consolidates(self) -> None:
        now = datetime.now(UTC)
        stale = build_memory(
            kind=MemoryKind.project_fact, confidence=0.9, created_days_ago=30
        )
        hot = build_memory(
            kind=MemoryKind.user_preference,
            confidence=0.6,
            created_days_ago=10,
            last_accessed_days_ago=0,
            access_count=4,
            authority=MemoryAuthority.suggested,
            provenance=["session:xyz"],
        )
        repository = FakeMemoryRepository([stale, hot])
        service = MemoryLifecycleService(repository)
        report = await service.run_lifecycle(now=now)

        self.assertEqual(report.scanned, 2)
        self.assertEqual(len(report.decayed), 1)
        self.assertEqual([str(memory_id) for memory_id in report.consolidated], [str(hot.id)])
        self.assertEqual(repository.memories[hot.id].authority, MemoryAuthority.verified)
        # 事实衰减：0.9 * exp(-0.01 * 30) ≈ 0.6667；
        # 偏好刚被命中过（last_accessed_at=now），衰减幅度低于阈值不写库，
        # 随后被巩固把置信度抬到 memory_consolidation_confidence（0.9）。
        self.assertAlmostEqual(repository.memories[stale.id].confidence, 0.6667, places=2)
        self.assertAlmostEqual(repository.memories[hot.id].confidence, 0.9, places=4)


class SettingsOverrideTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第7步：验证可通过配置覆盖阈值 =====================
    async def test_custom_settings_control_thresholds(self) -> None:
        now = datetime.now(UTC)
        settings = Settings(
            _env_file=None,
            memory_consolidation_min_accesses=1,
            memory_decay_min_drop=0.0,
        )
        memory = build_memory(
            kind=MemoryKind.project_fact,
            confidence=0.8,
            access_count=1,
            authority=MemoryAuthority.suggested,
            provenance=["session:one"],
        )
        repository = FakeMemoryRepository([memory])
        service = MemoryLifecycleService(repository, settings=settings)
        report = await service.run_lifecycle(now=now)
        # min_accesses=1 时命中一次即可巩固。
        self.assertEqual(len(report.consolidated), 1)


if __name__ == "__main__":
    unittest.main()
