import unittest
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.application.memory_retrieval_service import MemoryRetrievalService
from app.domain.memories.entities import AgentMemory, MemoryKind


class FakeMemoryRepository:
    """内存版记忆仓库，模拟 DB 侧过滤 + 检索命中统计 + 图谱邻居读取。"""

    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = {memory.id: memory for memory in memories}
        self.touch_calls: list[UUID] = []

    async def list_retrievable(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        project_id: str | None = None,
        task_id: object = None,
        user_id: str | None = None,
    ) -> list[AgentMemory]:
        """模拟数据库侧过滤：未删除、未禁用、未过期。"""
        reference = now or datetime.now(UTC)
        items = []
        for memory in self.memories.values():
            if memory.deleted_at is not None or not memory.enabled:
                continue
            if memory.expires_at is not None and memory.expires_at <= reference:
                continue
            items.append(memory)
        items.sort(key=lambda m: m.created_at, reverse=True)
        return items[:limit] if limit is not None else items

    async def get(self, memory_id) -> AgentMemory | None:
        return self.memories.get(memory_id)

    async def touch_access(self, memory_id, *, now: datetime | None = None) -> AgentMemory | None:
        memory = self.memories.get(memory_id)
        if memory is None:
            return None
        memory.access_count += 1
        memory.last_accessed_at = now or datetime.now(UTC)
        self.touch_calls.append(memory_id)
        return memory


class FakeUow:
    """只带 memories 仓库的假 UnitOfWork（不触发检索追踪）。"""

    def __init__(self, repository: FakeMemoryRepository) -> None:
        self.memories = repository


def build_memory(
    *,
    content: str,
    created_days_ago: int = 0,
    related_ids: list | None = None,
    enabled: bool = True,
) -> AgentMemory:
    now = datetime.now(UTC)
    return AgentMemory(
        id=uuid4(),
        kind=MemoryKind.project_fact,
        content=content,
        importance=4,
        enabled=enabled,
        source_session_id=None,
        source_event_id=None,
        expires_at=None,
        related_ids=related_ids or [],
        created_at=now - timedelta(days=created_days_ago),
        updated_at=now - timedelta(days=created_days_ago),
    )


class UsageTrackingTest(unittest.IsolatedAsyncioTestCase):
    def _service(self, repository: FakeMemoryRepository) -> MemoryRetrievalService:
        return MemoryRetrievalService(FakeUow(repository))

    # ===================== 第1步：验证检索命中自动累加 access_count =====================
    async def test_retrieval_hits_increment_access_count(self) -> None:
        memory = build_memory(content="项目使用 PostgreSQL 数据库")
        repository = FakeMemoryRepository([memory])
        await self._service(repository).retrieve(query="PostgreSQL")
        self.assertEqual(repository.touch_calls, [memory.id])
        self.assertEqual(memory.access_count, 1)
        self.assertIsNotNone(memory.last_accessed_at)
        # 二次命中继续累加。
        await self._service(repository).retrieve(query="PostgreSQL")
        self.assertEqual(memory.access_count, 2)

    # ===================== 第2步：验证 last_accessed_at 更新为命中时间 =====================
    async def test_retrieval_hits_update_last_accessed_at(self) -> None:
        before = datetime.now(UTC) - timedelta(seconds=1)
        memory = build_memory(content="接口超时时间 5 秒", created_days_ago=30)
        repository = FakeMemoryRepository([memory])
        await self._service(repository).retrieve(query="超时")
        self.assertIsNotNone(memory.last_accessed_at)
        self.assertGreaterEqual(memory.last_accessed_at, before)

    # ===================== 第3步：验证图谱展开把相关记忆加入上下文 =====================
    async def test_retrieval_includes_graph_neighbours(self) -> None:
        center = build_memory(content="项目使用 PostgreSQL 数据库")
        # 邻居内容不含查询词：只能靠图谱关联进入上下文。
        neighbour = build_memory(content="连接池统一使用 asyncpg", created_days_ago=1)
        center.related_ids = [neighbour.id]
        repository = FakeMemoryRepository([center, neighbour])
        context = await self._service(repository).retrieve(query="PostgreSQL")
        item_ids = [item.id for item in context.items]
        self.assertEqual(len(item_ids), 2)
        self.assertIn(center.id, item_ids)
        self.assertIn(neighbour.id, item_ids)
        related_item = next(item for item in context.items if item.id == neighbour.id)
        self.assertTrue(related_item.reason_retrieved.startswith("graph_link="))
        # 图谱邻居进入上下文同样计入使用统计（它们被注入给了模型）。
        self.assertEqual(sorted(repository.touch_calls), sorted([center.id, neighbour.id]))

    # ===================== 第4步：验证图谱展开受 max_links 上限约束 =====================
    async def test_graph_expansion_respects_max_links(self) -> None:
        center = build_memory(content="项目使用 PostgreSQL 数据库")
        neighbours = [
            build_memory(content=f"邻居记忆编号 {i}", created_days_ago=i + 1)
            for i in range(5)
        ]
        center.related_ids = [m.id for m in neighbours]
        repository = FakeMemoryRepository([center, *neighbours])
        context = await self._service(repository).retrieve(query="PostgreSQL")
        # 本体 + 最多 memory_graph_max_links(3) 个邻居。
        self.assertEqual(len(context.items), 4)
        included_neighbours = [item.id for item in context.items if item.id != center.id]
        self.assertEqual(len(included_neighbours), 3)
        # 本体命中 + 3 个被注入的邻居 = 4 次使用统计。
        self.assertEqual(len(repository.touch_calls), 4)

    # ===================== 第5步：验证字符预算占满时跳过展开且不报错 =====================
    async def test_graph_expansion_skipped_when_char_budget_full(self) -> None:
        center = build_memory(content="项目使用 PostgreSQL 数据库")
        neighbour = build_memory(content="邻居记忆", created_days_ago=1)
        center.related_ids = [neighbour.id]
        # 另一条同样命中查询的记忆，配合极小的 max_chars 把字符预算占满。
        filler = build_memory(content="PostgreSQL 迁移注意事项", created_days_ago=2)
        repository = FakeMemoryRepository([center, neighbour, filler])
        context = await self._service(repository).retrieve(query="PostgreSQL", max_chars=15)
        # 字符预算已满：图谱邻居不再进入上下文。
        item_ids = [item.id for item in context.items]
        self.assertEqual(len(item_ids), 2)
        self.assertIn(center.id, item_ids)
        self.assertIn(filler.id, item_ids)
        self.assertNotIn(neighbour.id, item_ids)
        for item in context.items:
            self.assertFalse(item.reason_retrieved.startswith("graph_link="))
        self.assertEqual(sorted(repository.touch_calls), sorted([center.id, filler.id]))

    # ===================== 第6步：验证直接命中的邻居不会因图谱展开重复进入上下文 =====================
    async def test_direct_hit_neighbour_not_duplicated_by_graph_expansion(self) -> None:
        center = build_memory(content="项目使用 PostgreSQL 数据库")
        # 邻居内容也包含查询词：它既会被直接命中，又是 center 的图谱邻居。
        neighbour = build_memory(
            content="PostgreSQL 连接池使用 asyncpg", created_days_ago=1
        )
        center.related_ids = [neighbour.id]
        neighbour.related_ids = [center.id]
        repository = FakeMemoryRepository([center, neighbour])
        context = await self._service(repository).retrieve(query="PostgreSQL")
        item_ids = [item.id for item in context.items]
        # 每条记忆最多出现一次。
        self.assertEqual(len(item_ids), len(set(item_ids)))
        self.assertIn(center.id, item_ids)
        self.assertIn(neighbour.id, item_ids)


if __name__ == "__main__":
    unittest.main()
