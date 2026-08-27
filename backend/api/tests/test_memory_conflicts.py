import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.memories.conflicts import (
    MemoryConflictService,
    MemoryConflictStrategy,
    detect_conflicts,
)
from app.domain.memories.entities import (
    AgentMemory,
    MemoryAuthority,
    MemoryKind,
    MemoryStatus,
)


class FakeMemoryRepository:
    """内存版记忆仓库，记录 superseded 标记和审计事件。"""

    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = {memory.id: memory for memory in memories}
        self.superseded: list[tuple] = []
        self.audit_events: list[dict[str, object]] = []
        self.updated_metadata: dict = {}

    async def list_for_lifecycle(self, *, limit: int | None = None) -> list[AgentMemory]:
        items = [m for m in self.memories.values() if m.deleted_at is None]
        return items[:limit] if limit is not None else items

    async def mark_superseded(self, memory_id, *, replacement_id) -> AgentMemory | None:
        memory = self.memories.get(memory_id)
        if memory is None:
            return None
        memory.status = MemoryStatus.superseded
        memory.enabled = False
        memory.metadata["superseded_by"] = str(replacement_id)
        self.superseded.append((memory_id, replacement_id))
        return memory

    async def update(
        self,
        memory_id,
        *,
        metadata: dict[str, object] | None = None,
        **_ignored,
    ) -> AgentMemory | None:
        memory = self.memories.get(memory_id)
        if memory is None:
            return None
        if metadata is not None:
            memory.metadata = metadata
            self.updated_metadata[memory_id] = metadata
        return memory

    async def record_audit_event(
        self, *, memory_id, event_type: str, payload: dict[str, object]
    ) -> uuid4:
        self.audit_events.append(
            {"memory_id": memory_id, "event_type": event_type, "payload": payload}
        )
        return uuid4()


def build_memory(
    *,
    subject: str = "",
    predicate: str = "states",
    value: dict[str, object] | None = None,
    age_hours: float = 0.0,
    authority: MemoryAuthority = MemoryAuthority.explicit_user,
    status: MemoryStatus = MemoryStatus.verified,
    deleted: bool = False,
) -> AgentMemory:
    now = datetime.now(UTC)
    return AgentMemory(
        id=uuid4(),
        kind=MemoryKind.project_fact,
        content=f"{subject} {predicate} {value}",
        importance=3,
        enabled=True,
        source_session_id=None,
        source_event_id=None,
        expires_at=None,
        status=status,
        subject=subject,
        predicate=predicate,
        value=value or {"text": "默认值"},
        authority=authority,
        created_at=now - timedelta(hours=age_hours),
        updated_at=now - timedelta(hours=age_hours),
        deleted_at=now if deleted else None,
    )


class DetectConflictsTest(unittest.TestCase):
    # ===================== 第1步：验证冲突判定规则 =====================
    def test_same_subject_and_predicate_with_different_value(self) -> None:
        new = build_memory(subject="project.database", value={"engine": "postgresql"})
        existing = build_memory(
            subject="project.database",
            value={"engine": "sqlite"},
            age_hours=24,
        )
        conflicts = detect_conflicts(new, [existing])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].subject, "project.database")
        self.assertEqual(conflicts[0].existing_memory.id, existing.id)

    def test_same_value_is_not_a_conflict(self) -> None:
        new = build_memory(subject="project.database", value={"engine": "sqlite"})
        existing = build_memory(
            subject="project.database", value={"engine": "sqlite"}, age_hours=24
        )
        self.assertEqual(detect_conflicts(new, [existing]), [])

    def test_value_key_order_does_not_matter(self) -> None:
        new = build_memory(
            subject="project.database", value={"engine": "sqlite", "port": 5432}
        )
        existing = build_memory(
            subject="project.database",
            value={"port": 5432, "engine": "sqlite"},
            age_hours=24,
        )
        self.assertEqual(detect_conflicts(new, [existing]), [])

    def test_different_predicate_is_not_a_conflict(self) -> None:
        new = build_memory(subject="project.database", predicate="states", value={"engine": "sqlite"})
        existing = build_memory(
            subject="project.database", predicate="uses", value={"engine": "postgres"},
            age_hours=24,
        )
        self.assertEqual(detect_conflicts(new, [existing]), [])

    def test_memory_without_subject_never_conflicts(self) -> None:
        new = build_memory(subject="", value={"engine": "sqlite"})
        existing = build_memory(subject="", value={"engine": "postgres"}, age_hours=24)
        self.assertEqual(detect_conflicts(new, [existing]), [])

    def test_deleted_and_superseded_memories_are_ignored(self) -> None:
        new = build_memory(subject="project.database", value={"engine": "postgresql"})
        deleted = build_memory(
            subject="project.database", value={"engine": "sqlite"}, deleted=True
        )
        superseded = build_memory(
            subject="project.database",
            value={"engine": "sqlite"},
            status=MemoryStatus.superseded,
        )
        self.assertEqual(detect_conflicts(new, [deleted, superseded]), [])

    def test_self_is_never_a_conflict(self) -> None:
        memory = build_memory(subject="project.database", value={"engine": "sqlite"})
        self.assertEqual(detect_conflicts(memory, [memory]), [])


class PickWinnerTest(unittest.TestCase):
    # ===================== 第2步：验证策略选择胜者 =====================
    def setUp(self) -> None:
        self.repository = FakeMemoryRepository([])
        self.service = MemoryConflictService(self.repository)

    def test_latest_wins_prefers_newer_memory(self) -> None:
        newer = build_memory(subject="s", value={"v": 2}, age_hours=1)
        older = build_memory(subject="s", value={"v": 1}, age_hours=48)
        winner, loser = self.service.pick_winner(
            newer, older, strategy=MemoryConflictStrategy.latest_wins
        )
        self.assertIs(winner, newer)
        self.assertIs(loser, older)
        # 新记忆其实更旧时，胜者换成存量记忆。
        winner, loser = self.service.pick_winner(
            older, newer, strategy=MemoryConflictStrategy.latest_wins
        )
        self.assertIs(winner, newer)

    def test_authority_wins_prefers_higher_authority(self) -> None:
        low = build_memory(
            subject="s", value={"v": 1}, age_hours=1, authority=MemoryAuthority.agent_inferred
        )
        high = build_memory(
            subject="s",
            value={"v": 2},
            age_hours=48,
            authority=MemoryAuthority.explicit_user,
        )
        # 新记忆权威低：旧的高权威记忆胜出。
        winner, loser = self.service.pick_winner(
            low, high, strategy=MemoryConflictStrategy.authority_wins
        )
        self.assertIs(winner, high)
        self.assertIs(loser, low)
        # 新记忆权威高：新记忆胜出。
        winner, _ = self.service.pick_winner(
            high, low, strategy=MemoryConflictStrategy.authority_wins
        )
        self.assertIs(winner, high)

    def test_authority_wins_falls_back_to_latest_on_tie(self) -> None:
        newer = build_memory(subject="s", value={"v": 2}, age_hours=1)
        older = build_memory(subject="s", value={"v": 1}, age_hours=48)
        winner, _ = self.service.pick_winner(
            newer, older, strategy=MemoryConflictStrategy.authority_wins
        )
        self.assertIs(winner, newer)


class ResolveTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第3步：验证 latest_wins 消解 + 审计事件 =====================
    async def test_latest_wins_supersedes_older_memory(self) -> None:
        now = datetime.now(UTC)
        new = build_memory(subject="project.database", value={"engine": "postgresql"})
        existing = build_memory(
            subject="project.database", value={"engine": "sqlite"}, age_hours=24
        )
        repository = FakeMemoryRepository([existing])
        service = MemoryConflictService(repository)
        conflicts = await service.resolve(new, now=now)

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(repository.superseded), 1)
        self.assertEqual(repository.superseded[0][0], existing.id)
        self.assertEqual(repository.superseded[0][1], new.id)
        self.assertEqual(repository.memories[existing.id].status, MemoryStatus.superseded)
        self.assertEqual(
            repository.memories[existing.id].metadata["superseded_by"], str(new.id)
        )
        # 审计事件记录在败者名下。
        self.assertEqual(len(repository.audit_events), 1)
        self.assertEqual(repository.audit_events[0]["event_type"], "memory_conflict_resolved")
        self.assertEqual(repository.audit_events[0]["memory_id"], existing.id)
        self.assertEqual(
            repository.audit_events[0]["payload"]["strategy"], "latest_wins"
        )

    # ===================== 第4步：验证 authority_wins 消解 =====================
    async def test_authority_wins_keeps_high_authority_memory(self) -> None:
        now = datetime.now(UTC)
        # 新记忆是 Agent 推测，存量记忆是用户显式确认：新记忆应被 superseded。
        new = build_memory(
            subject="project.database",
            value={"engine": "postgresql"},
            authority=MemoryAuthority.agent_inferred,
        )
        existing = build_memory(
            subject="project.database",
            value={"engine": "sqlite"},
            age_hours=24,
            authority=MemoryAuthority.explicit_user,
        )
        repository = FakeMemoryRepository([new, existing])
        service = MemoryConflictService(repository)
        await service.resolve(new, strategy=MemoryConflictStrategy.authority_wins, now=now)

        self.assertEqual(repository.superseded[0][0], new.id)
        self.assertEqual(repository.superseded[0][1], existing.id)
        self.assertEqual(repository.memories[existing.id].status, MemoryStatus.verified)

    # ===================== 第5步：验证 manual_review 只挂起不改状态 =====================
    async def test_manual_review_marks_both_memories(self) -> None:
        now = datetime.now(UTC)
        new = build_memory(subject="project.database", value={"engine": "postgresql"})
        existing = build_memory(
            subject="project.database", value={"engine": "sqlite"}, age_hours=24
        )
        repository = FakeMemoryRepository([new, existing])
        service = MemoryConflictService(repository)
        conflicts = await service.resolve(
            new, strategy=MemoryConflictStrategy.manual_review, now=now
        )

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(repository.superseded, [])
        self.assertEqual(repository.memories[new.id].status, MemoryStatus.verified)
        self.assertEqual(repository.memories[existing.id].status, MemoryStatus.verified)
        for memory_id in (new.id, existing.id):
            marker = repository.memories[memory_id].metadata["conflict_review"]
            self.assertEqual(marker["subject"], "project.database")
        # 审计事件标记为待人工复核。
        self.assertEqual(
            repository.audit_events[0]["event_type"], "memory_conflict_manual_review"
        )

    # ===================== 第6步：验证无冲突时不做任何事 =====================
    async def test_resolve_without_conflict_is_noop(self) -> None:
        now = datetime.now(UTC)
        new = build_memory(subject="project.database", value={"engine": "sqlite"})
        existing = build_memory(
            subject="project.other", value={"engine": "sqlite"}, age_hours=24
        )
        repository = FakeMemoryRepository([existing])
        service = MemoryConflictService(repository)
        conflicts = await service.resolve(new, now=now)
        self.assertEqual(conflicts, [])
        self.assertEqual(repository.superseded, [])
        self.assertEqual(repository.audit_events, [])

    # ===================== 第7步：验证 strategy 可用字符串传入 =====================
    async def test_resolve_accepts_strategy_string(self) -> None:
        now = datetime.now(UTC)
        new = build_memory(subject="project.database", value={"engine": "postgresql"})
        existing = build_memory(
            subject="project.database", value={"engine": "sqlite"}, age_hours=24
        )
        repository = FakeMemoryRepository([existing])
        service = MemoryConflictService(repository)
        conflicts = await service.resolve(new, strategy="latest_wins", now=now)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(repository.superseded), 1)


if __name__ == "__main__":
    unittest.main()
