"""Todo 清单应用服务（TodoService）单元测试。

用假 uow（SimpleNamespace）隔离数据库，覆盖：
- get_board：读最新 plan_created 建板、无 plan/无会话 404、
  只回放最新 plan 之后的 todo_updated 事件、回放遇非法流转跳过；
- update_status：写 todo_updated 事件（payload 带 progress 快照）、
  非法流转 400、未知 todo 404；
- sync_from_step_event：step_completed/step_failed 按 step_id / index
  定位同步、无匹配静默、已同态幂等、非 step 事件忽略。
"""

import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.application.todo_service import TodoService
from app.core.exceptions import AppException
from app.domain.agent_core.todo import TodoStatus
from app.domain.sessions.entities import SessionEventType


def _session() -> SimpleNamespace:
    """最小 Session（服务只判存在性）。"""

    return SimpleNamespace(id=uuid4(), title="t", status="running")


def _event(event_type: SessionEventType, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        type=event_type,
        payload=payload,
        created_at=None,
    )


def _plan_event(steps: list[dict]) -> SimpleNamespace:
    return _event(
        SessionEventType.plan_created,
        {"id": "plan-1", "title": "计划", "goal": "目标", "steps": steps},
    )


def _todo_event(todo_id: str, status: str) -> SimpleNamespace:
    return _event(
        SessionEventType.todo_updated,
        {"todo_id": todo_id, "status": status, "progress": {}},
    )


def _step(step_id: str, **extra) -> dict:
    step = {"id": step_id, "title": f"步骤 {step_id}", "description": ""}
    step.update(extra)
    return step


class FakeSessionEvents:
    """假 session_events 仓储：存事件列表，add 追加并记录。"""

    def __init__(self, events: list[SimpleNamespace]) -> None:
        self.events = list(events)
        self.added: list[SimpleNamespace] = []

    async def list_by_session(self, session_id):
        return list(self.events)

    async def add(self, session_id, event_type, payload) -> SimpleNamespace:
        """与真实仓储一致：新事件立即对后续 list_by_session 可见。"""
        event = SimpleNamespace(
            id=uuid4(),
            session_id=session_id,
            type=event_type,
            payload=payload,
            created_at=None,
        )
        self.events.append(event)
        self.added.append(event)
        return event


class FakeUow:
    """最小假 UnitOfWork：sessions / session_events / commit。"""

    def __init__(self, events: list[SimpleNamespace], session=None) -> None:
        self.sessions = SimpleNamespace(get=lambda _sid: _get(session))
        self.session_events = FakeSessionEvents(events)
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


async def _get(session):
    """FakeUow.sessions.get 的异步实现（闭包共享 session）。"""

    return session


class GetBoardTest(unittest.IsolatedAsyncioTestCase):
    async def test_no_session_raises_404(self) -> None:
        """会话不存在 -> AppException 404。"""

        uow = FakeUow([], session=None)
        service = TodoService(uow)
        with self.assertRaises(AppException) as ctx:
            await service.get_board(uuid4())
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_no_plan_raises_404(self) -> None:
        """会话存在但没有 plan_created 事件 -> 404 "plan not found"。"""

        uow = FakeUow([], session=_session())
        service = TodoService(uow)
        with self.assertRaises(AppException) as ctx:
            await service.get_board(uuid4())
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("plan not found", ctx.exception.message)

    async def test_builds_from_latest_plan_only(self) -> None:
        """多个 plan 时以最新为准；旧 plan 后的 todo_updated 不再回放。"""

        uow = FakeUow(
            [
                _plan_event([_step("old-1")]),
                _todo_event("old-1", "done"),
                _plan_event([_step("new-1"), _step("new-2")]),
            ],
            session=_session(),
        )
        service = TodoService(uow)
        board = await service.get_board(uuid4())

        self.assertEqual([item.id for item in board.items], ["new-1", "new-2"])
        self.assertTrue(all(item.status is TodoStatus.pending for item in board.items))

    async def test_replays_todo_updated_after_plan(self) -> None:
        """回放最新 plan 之后的 todo_updated：状态与 progress 反映出来。"""

        uow = FakeUow(
            [
                _plan_event([_step("a"), _step("b")]),
                _todo_event("a", "in_progress"),
                _todo_event("a", "done"),
            ],
            session=_session(),
        )
        service = TodoService(uow)
        board = await service.get_board(uuid4())

        by_id = {item.id: item.status for item in board.items}
        self.assertIs(by_id["a"], TodoStatus.done)
        self.assertIs(by_id["b"], TodoStatus.pending)
        self.assertEqual(board.progress()["done"], 1)
        self.assertEqual(board.progress()["percent"], 50.0)

    async def test_replay_skips_invalid_transition(self) -> None:
        """回放遇到无法应用的流转（done -> pending）时跳过，不炸重建。"""

        uow = FakeUow(
            [
                _plan_event([_step("a")]),
                _todo_event("a", "done"),
                _todo_event("a", "pending"),  # 非法流转：回放时跳过
            ],
            session=_session(),
        )
        service = TodoService(uow)
        board = await service.get_board(uuid4())
        self.assertIs(board.items[0].status, TodoStatus.done)


class UpdateStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_writes_event_with_progress_snapshot(self) -> None:
        """手动标记：写 todo_updated 事件（payload 带 progress）并 commit。"""

        uow = FakeUow([_plan_event([_step("a"), _step("b")])], session=_session())
        service = TodoService(uow)
        progress = await service.update_status(
            uuid4(), "a", TodoStatus.in_progress
        )

        self.assertEqual(len(uow.session_events.added), 1)
        event = uow.session_events.added[0]
        self.assertIs(event.type, SessionEventType.todo_updated)
        self.assertEqual(event.payload["todo_id"], "a")
        self.assertEqual(event.payload["status"], "in_progress")
        self.assertEqual(
            event.payload["progress"],
            {"total": 2, "done": 0, "failed": 0, "pending": 1, "percent": 0.0},
        )
        # 返回值与事件里记录的是同一份快照
        self.assertEqual(progress, event.payload["progress"])
        self.assertEqual(uow.commits, 1)

    async def test_invalid_transition_raises_400(self) -> None:
        """非法流转（done -> pending）-> AppException 400，且不写事件。"""

        uow = FakeUow([_plan_event([_step("a")])], session=_session())
        service = TodoService(uow)
        await service.update_status(uuid4(), "a", TodoStatus.done)
        with self.assertRaises(AppException) as ctx:
            await service.update_status(uuid4(), "a", TodoStatus.pending)
        self.assertEqual(ctx.exception.status_code, 400)
        # 只有第一次合法标记写了事件
        self.assertEqual(len(uow.session_events.added), 1)

    async def test_unknown_todo_raises_404(self) -> None:
        """标记不存在的 todo -> 404。"""

        uow = FakeUow([_plan_event([_step("a")])], session=_session())
        service = TodoService(uow)
        with self.assertRaises(AppException) as ctx:
            await service.update_status(uuid4(), "ghost", TodoStatus.done)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(uow.session_events.added, [])


class SyncFromStepEventTest(unittest.IsolatedAsyncioTestCase):
    def _service(
        self, events: list[SimpleNamespace], session=None
    ) -> tuple[TodoService, FakeUow]:
        uow = FakeUow(events, session=session if session is not None else _session())
        return TodoService(uow), uow

    async def test_step_completed_by_step_id(self) -> None:
        """step_completed 按 step_id 定位：todo 同步为 done + 写事件。"""

        service, uow = self._service(
            [_plan_event([_step("a"), _step("b")])]
        )
        await service.sync_from_step_event(
            uuid4(),
            _event(
                SessionEventType.step_completed,
                {"step_id": "b", "index": 2},
            ),
        )

        board = await service.get_board(uuid4())
        by_id = {item.id: item.status for item in board.items}
        self.assertIs(by_id["b"], TodoStatus.done)
        self.assertIs(by_id["a"], TodoStatus.pending)
        self.assertEqual(len(uow.session_events.added), 1)
        self.assertEqual(uow.session_events.added[0].payload["status"], "done")

    async def test_step_failed_by_index_fallback(self) -> None:
        """payload 没有 step_id 时按 1 起的 index 兜底定位（index=1 -> step_index 0）。"""

        service, uow = self._service(
            [_plan_event([_step("a"), _step("b")])]
        )
        await service.sync_from_step_event(
            uuid4(), _event(SessionEventType.step_failed, {"index": 1})
        )

        board = await service.get_board(uuid4())
        self.assertIs(board.items[0].status, TodoStatus.failed)
        self.assertIs(board.items[1].status, TodoStatus.pending)
        self.assertEqual(uow.session_events.added[0].payload["status"], "failed")

    async def test_no_match_is_silent(self) -> None:
        """step_id 与 index 都匹配不上：静默返回，不写事件不 commit。"""

        service, uow = self._service([_plan_event([_step("a")])])
        await service.sync_from_step_event(
            uuid4(),
            _event(
                SessionEventType.step_completed,
                {"step_id": "ghost", "index": 99},
            ),
        )
        self.assertEqual(uow.session_events.added, [])
        self.assertEqual(uow.commits, 0)

    async def test_already_same_status_is_idempotent(self) -> None:
        """todo 已是目标状态时不重复写事件（幂等）。"""

        events = [
            _plan_event([_step("a")]),
            _todo_event("a", "done"),
        ]
        service, uow = self._service(events)
        await service.sync_from_step_event(
            uuid4(),
            _event(SessionEventType.step_completed, {"step_id": "a", "index": 1}),
        )
        self.assertEqual(uow.session_events.added, [])
        self.assertEqual(uow.commits, 0)

    async def test_invalid_transition_is_silent(self) -> None:
        """todo 已 done 又收到 step_failed（非法流转）：静默保持原状态。"""

        events = [
            _plan_event([_step("a")]),
            _todo_event("a", "done"),
        ]
        service, uow = self._service(events)
        await service.sync_from_step_event(
            uuid4(),
            _event(SessionEventType.step_failed, {"step_id": "a", "index": 1}),
        )
        self.assertEqual(uow.session_events.added, [])
        board = await service.get_board(uuid4())
        self.assertIs(board.items[0].status, TodoStatus.done)

    async def test_non_step_event_ignored(self) -> None:
        """step_started 等其它事件不触发同步。"""

        service, uow = self._service([_plan_event([_step("a")])])
        await service.sync_from_step_event(
            uuid4(),
            _event(SessionEventType.step_started, {"step_id": "a", "index": 1}),
        )
        self.assertEqual(uow.session_events.added, [])

    async def test_session_without_plan_is_silent(self) -> None:
        """会话没有 plan 时静默返回（不抛错，不阻断执行主流程）。"""

        service, uow = self._service([], session=_session())
        await service.sync_from_step_event(
            uuid4(),
            _event(SessionEventType.step_completed, {"step_id": "a", "index": 1}),
        )
        self.assertEqual(uow.session_events.added, [])


if __name__ == "__main__":
    unittest.main()
