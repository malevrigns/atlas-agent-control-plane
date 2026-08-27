import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.memories.entities import AgentMemory, MemoryKind, MemoryStatus
from app.domain.memories.graph import MemoryGraphService, MemoryRelation


class FakeMemoryRepository:
    """内存版记忆仓库，支撑图谱链接/展开测试。"""

    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = {memory.id: memory for memory in memories}
        self.updates: list[tuple] = []

    async def get(self, memory_id) -> AgentMemory | None:
        return self.memories.get(memory_id)

    async def update(
        self,
        memory_id,
        *,
        related_ids: list | None = None,
        metadata: dict[str, object] | None = None,
        **_ignored,
    ) -> AgentMemory | None:
        memory = self.memories.get(memory_id)
        if memory is None:
            return None
        if related_ids is not None:
            memory.related_ids = related_ids
        if metadata is not None:
            memory.metadata = metadata
        self.updates.append((memory_id, related_ids, metadata))
        return memory


def build_memory(
    *,
    enabled: bool = True,
    status: MemoryStatus = MemoryStatus.verified,
    related_ids: list | None = None,
    age_hours: float = 0.0,
    subject: str = "",
) -> AgentMemory:
    now = datetime.now(UTC)
    return AgentMemory(
        id=uuid4(),
        kind=MemoryKind.project_fact,
        content=f"记忆 {subject}",
        importance=3,
        enabled=enabled,
        source_session_id=None,
        source_event_id=None,
        expires_at=None,
        status=status,
        subject=subject,
        related_ids=related_ids or [],
        created_at=now - timedelta(hours=age_hours),
        updated_at=now - timedelta(hours=age_hours),
    )


class LinkMemoriesTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：验证 link_memories 双向写入 =====================
    async def test_link_is_bidirectional_with_relation_metadata(self) -> None:
        memory_a = build_memory(subject="a")
        memory_b = build_memory(subject="b", age_hours=1)
        repository = FakeMemoryRepository([memory_a, memory_b])
        service = MemoryGraphService(repository)

        updated_a, updated_b = await service.link_memories(
            memory_a, memory_b, relation=MemoryRelation.supports
        )

        self.assertIsNotNone(updated_a)
        self.assertIsNotNone(updated_b)
        self.assertEqual(memory_a.related_ids, [memory_b.id])
        self.assertEqual(memory_b.related_ids, [memory_a.id])
        # 关系名记录在双方 metadata 中，便于后续展示与治理。
        self.assertEqual(
            memory_a.metadata["graph_relations"][str(memory_b.id)], "supports"
        )
        self.assertEqual(
            memory_b.metadata["graph_relations"][str(memory_a.id)], "supports"
        )

    async def test_link_is_idempotent_when_already_linked(self) -> None:
        memory_a = build_memory(subject="a")
        memory_b = build_memory(subject="b")
        repository = FakeMemoryRepository([memory_a, memory_b])
        service = MemoryGraphService(repository)
        await service.link_memories(memory_a, memory_b, relation=MemoryRelation.supports)
        await service.link_memories(memory_a, memory_b, relation=MemoryRelation.extends)
        # 已关联时直接返回，关系不重复追加也不改写。
        self.assertEqual(memory_a.related_ids, [memory_b.id])
        self.assertEqual(memory_b.related_ids, [memory_a.id])
        self.assertEqual(
            memory_a.metadata["graph_relations"][str(memory_b.id)], "supports"
        )

    # ===================== 第2步：验证自链接被拒绝 =====================
    async def test_link_rejects_self_link(self) -> None:
        memory_a = build_memory(subject="a")
        repository = FakeMemoryRepository([memory_a])
        service = MemoryGraphService(repository)
        with self.assertRaises(ValueError):
            await service.link_memories(
                memory_a, memory_a, relation=MemoryRelation.supports
            )
        # 仓库未被改动。
        self.assertEqual(repository.updates, [])

    async def test_link_repairs_half_edge(self) -> None:
        memory_a = build_memory(subject="a")
        memory_b = build_memory(subject="b", age_hours=1)
        # 只有一侧记录了关联（历史脏数据），link 应把另一侧补齐。
        memory_a.related_ids = [memory_b.id]
        repository = FakeMemoryRepository([memory_a, memory_b])
        service = MemoryGraphService(repository)
        await service.link_memories(memory_a, memory_b, relation=MemoryRelation.supports)
        # a 侧已有边，不重复追加；b 侧补齐并写入关系。
        self.assertEqual(memory_a.related_ids, [memory_b.id])
        self.assertEqual(memory_b.related_ids, [memory_a.id])
        self.assertEqual(
            memory_b.metadata["graph_relations"][str(memory_a.id)], "supports"
        )

    # ===================== 第3步：验证 max_links 上限 =====================
    async def test_link_respects_max_links(self) -> None:
        memory_a = build_memory(subject="a")
        others = [build_memory(subject=f"b{i}", age_hours=i + 1) for i in range(4)]
        # a 已有关联 b0；默认上限 memory_graph_max_links=3。
        memory_a.related_ids = [others[0].id]
        repository = FakeMemoryRepository([memory_a, *others])
        service = MemoryGraphService(repository)
        await service.link_memories(memory_a, others[0], relation=MemoryRelation.supports)
        await service.link_memories(memory_a, others[1], relation=MemoryRelation.supports)
        await service.link_memories(memory_a, others[2], relation=MemoryRelation.supports)
        # 达到上限：a 的关联边数停在 3。
        self.assertEqual(len(memory_a.related_ids), 3)
        # 第 4 条：a 侧不再追加，但对方侧仍记录关联。
        await service.link_memories(memory_a, others[3], relation=MemoryRelation.supports)
        self.assertEqual(len(memory_a.related_ids), 3)
        self.assertIn(memory_a.id, others[3].related_ids)

    # ===================== 第4步：验证 relation 可用字符串传入 =====================
    async def test_link_accepts_relation_string(self) -> None:
        memory_a = build_memory(subject="a")
        memory_b = build_memory(subject="b")
        repository = FakeMemoryRepository([memory_a, memory_b])
        service = MemoryGraphService(repository)
        updated_a, _ = await service.link_memories(
            memory_a, memory_b, relation="contradicts"
        )
        self.assertIsNotNone(updated_a)
        self.assertEqual(
            memory_a.metadata["graph_relations"][str(memory_b.id)], "contradicts"
        )


class ExpandContextTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第5步：验证 expand_context 默认返回 1 层邻居 =====================
    async def test_expand_context_returns_neighbours(self) -> None:
        center = build_memory(subject="center")
        neighbour = build_memory(subject="n", age_hours=1)
        unrelated = build_memory(subject="x", age_hours=2)
        repository = FakeMemoryRepository([center, neighbour, unrelated])
        service = MemoryGraphService(repository)
        # 先建立关联边（center 侧也持有边）。
        await service.link_memories(center, neighbour, relation=MemoryRelation.extends)

        expanded = await service.expand_context(center)
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].id, neighbour.id)
        # 关联类型记录在 center 的 metadata 中。
        self.assertEqual(
            center.metadata["graph_relations"][str(neighbour.id)], "extends"
        )

    async def test_expand_context_ignores_self_deleted_disabled_and_superseded(self) -> None:
        center = build_memory(subject="center")
        deleted = build_memory(subject="d", related_ids=[center.id], age_hours=1)
        disabled = build_memory(
            subject="o", related_ids=[center.id], enabled=False, age_hours=2
        )
        superseded = build_memory(
            subject="p",
            related_ids=[center.id],
            status=MemoryStatus.superseded,
            age_hours=3,
        )
        good = build_memory(subject="g", related_ids=[center.id], age_hours=4)
        # center 的 related_ids 里混入自己，应被 seen 集合过滤。
        center.related_ids = [deleted.id, disabled.id, superseded.id, good.id, center.id]
        deleted.deleted_at = datetime.now(UTC)
        repository = FakeMemoryRepository(
            [center, deleted, disabled, superseded, good]
        )
        service = MemoryGraphService(repository)
        expanded = await service.expand_context(center)
        self.assertEqual([m.id for m in expanded], [good.id])

    # ===================== 第6步：验证 limit 截断（按 related_ids 顺序） =====================
    async def test_expand_context_limits_result(self) -> None:
        center = build_memory(subject="center")
        neighbours = [
            build_memory(subject=f"n{i}", related_ids=[center.id], age_hours=i + 1)
            for i in range(5)
        ]
        center.related_ids = [m.id for m in neighbours]
        repository = FakeMemoryRepository([center, *neighbours])
        service = MemoryGraphService(repository)
        expanded = await service.expand_context(center, limit=2)
        self.assertEqual(len(expanded), 2)
        # 按 related_ids 的既有顺序取前 N。
        self.assertEqual(expanded[0].id, neighbours[0].id)
        self.assertEqual(expanded[1].id, neighbours[1].id)

    async def test_expand_context_default_limit_is_max_links(self) -> None:
        center = build_memory(subject="center")
        neighbours = [
            build_memory(subject=f"n{i}", related_ids=[center.id], age_hours=i + 1)
            for i in range(5)
        ]
        center.related_ids = [m.id for m in neighbours]
        repository = FakeMemoryRepository([center, *neighbours])
        service = MemoryGraphService(repository)
        expanded = await service.expand_context(center)
        # 默认条数上限为 memory_graph_max_links=3，防止上下文爆炸。
        self.assertEqual(len(expanded), 3)

    async def test_expand_context_clamps_depth_and_unknown_ids(self) -> None:
        center = build_memory(subject="center")
        neighbour = build_memory(subject="n", related_ids=[center.id], age_hours=1)
        # center 的 related_ids 里混入一个不存在的 uuid，应被安全忽略。
        center.related_ids = [neighbour.id, uuid4()]
        repository = FakeMemoryRepository([center, neighbour])
        service = MemoryGraphService(repository)
        expanded = await service.expand_context(center, depth=3)  # depth 被钳制到 1
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].id, neighbour.id)

    async def test_expand_context_empty_when_no_links(self) -> None:
        center = build_memory(subject="center")
        repository = FakeMemoryRepository([center])
        service = MemoryGraphService(repository)
        self.assertEqual(await service.expand_context(center), [])


if __name__ == "__main__":
    unittest.main()
