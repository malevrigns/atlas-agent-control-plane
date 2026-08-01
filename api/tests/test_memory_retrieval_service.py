import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.memory_retrieval_service import MemoryRetrievalService
from app.domain.memories.entities import AgentMemory, MemoryKind


class FakeMemoryRepository:
    """为单元测试提供固定长期记忆，不连接 PostgreSQL。"""

    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = memories

    async def list_retrievable(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[AgentMemory]:
        return [
            memory
            for memory in self.memories
            if memory.enabled
            and memory.deleted_at is None
            and (memory.expires_at is None or memory.expires_at > now)
        ][:limit]


class FakeUnitOfWork:
    def __init__(self, memories: list[AgentMemory]) -> None:
        self.memories = FakeMemoryRepository(memories)


def build_memory(
    *,
    kind: MemoryKind,
    content: str,
    importance: int = 3,
    enabled: bool = True,
    updated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> AgentMemory:
    now = datetime.now(UTC)
    return AgentMemory(
        id=uuid4(),
        kind=kind,
        content=content,
        importance=importance,
        enabled=enabled,
        source_session_id=None,
        source_event_id=None,
        expires_at=expires_at,
        created_at=now,
        updated_at=updated_at or now,
    )


class MemoryRetrievalServiceTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：验证禁用和过期记忆不会被注入 =====================
    async def test_retrieve_excludes_disabled_and_expired_memories(self) -> None:
        now = datetime.now(UTC)
        service = MemoryRetrievalService(
            FakeUnitOfWork(
                [
                    build_memory(
                        kind=MemoryKind.project_fact,
                        content="项目后端使用 FastAPI 和 PostgreSQL",
                    ),
                    build_memory(
                        kind=MemoryKind.constraint,
                        content="不要提交 API Key",
                        enabled=False,
                    ),
                    build_memory(
                        kind=MemoryKind.task_experience,
                        content="部署前需要执行数据库迁移",
                        expires_at=now - timedelta(days=1),
                    ),
                ]
            )
        )

        context = await service.retrieve(
            query="请检查 FastAPI 项目的数据库架构",
            now=now,
        )

        self.assertEqual(len(context.items), 1)
        self.assertIn("FastAPI", context.items[0].content)

    # ===================== 第2步：验证相关度、重要度和更新时间共同参与排序 =====================
    async def test_retrieve_ranks_relevant_memory_first(self) -> None:
        now = datetime.now(UTC)
        service = MemoryRetrievalService(
            FakeUnitOfWork(
                [
                    build_memory(
                        kind=MemoryKind.project_fact,
                        content="项目使用 FastAPI 构建后端 API",
                        importance=4,
                        updated_at=now - timedelta(days=10),
                    ),
                    build_memory(
                        kind=MemoryKind.user_preference,
                        content="用户偏好中文解释",
                        importance=5,
                        updated_at=now,
                    ),
                    build_memory(
                        kind=MemoryKind.task_experience,
                        content="修改 FastAPI 路由后需要检查 OpenAPI 和编译结果",
                        importance=5,
                        updated_at=now - timedelta(days=1),
                    ),
                ]
            )
        )

        context = await service.retrieve(
            query="请修改 FastAPI 路由并检查接口",
            now=now,
        )

        self.assertEqual(context.items[0].kind, MemoryKind.task_experience)
        self.assertGreater(context.items[0].relevance_score, 0)
        self.assertIn("fastapi", context.items[0].matched_terms)

    # ===================== 第3步：验证数量和字符预算 =====================
    async def test_retrieve_respects_item_and_character_budget(self) -> None:
        now = datetime.now(UTC)
        memories = [
            build_memory(
                kind=MemoryKind.constraint,
                content=f"项目约束 {index}：修改代码后必须执行完整验证。",
                importance=5,
                updated_at=now - timedelta(minutes=index),
            )
            for index in range(8)
        ]
        service = MemoryRetrievalService(FakeUnitOfWork(memories))

        context = await service.retrieve(
            query="修改项目代码并执行验证",
            limit=3,
            max_chars=80,
            max_item_chars=40,
            now=now,
        )

        self.assertLessEqual(len(context.items), 3)
        self.assertLessEqual(context.total_chars, 80)
        self.assertTrue(all(len(item.content) <= 50 for item in context.items))
        self.assertGreater(context.omitted_count, 0)

    # ===================== 第4步：验证无关项目事实不会只靠重要度进入上下文 =====================
    async def test_retrieve_excludes_unmatched_non_global_memory(self) -> None:
        now = datetime.now(UTC)
        service = MemoryRetrievalService(
            FakeUnitOfWork(
                [
                    build_memory(
                        kind=MemoryKind.project_fact,
                        content="移动端项目使用 Flutter 和 SQLite",
                        importance=5,
                    ),
                    build_memory(
                        kind=MemoryKind.project_fact,
                        content="后端 API 使用 FastAPI 和 PostgreSQL",
                        importance=3,
                    ),
                ]
            )
        )

        context = await service.retrieve(
            query="请优化 FastAPI 数据库接口",
            now=now,
        )

        self.assertEqual(len(context.items), 1)
        self.assertIn("FastAPI", context.items[0].content)


if __name__ == "__main__":
    unittest.main()
