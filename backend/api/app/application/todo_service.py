"""Todo 清单应用服务（Task Todo Service）。

职责：
- :meth:`TodoService.get_board`：读最新 plan_created 事件，用
  ``TodoBoard.from_plan`` 建板，再回放其后的 todo_updated 事件，
  得到当前进度视图（事件是事实源，board 只是派生）；
- :meth:`TodoService.update_status`：手动标记（前端勾选），校验状态
  流转后写 todo_updated 事件（payload 记 progress 快照）；
- :meth:`TodoService.sync_from_step_event`：执行机发出
  step_completed / step_failed 时，把对应 step_index 的 todo 同步为
  done / failed（供 T7 接线调用）。

不落库、不新增表：board 全部状态都可以通过事件流重建。
"""

from uuid import UUID

from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.todo import TodoBoard, TodoItem, TodoStatus
from app.domain.sessions.entities import SessionEvent, SessionEventType

# 事件 -> todo 目标状态 的映射（执行机 step 事件同步用）。
_STEP_EVENT_STATUS: dict[SessionEventType, TodoStatus] = {
    SessionEventType.step_completed: TodoStatus.done,
    SessionEventType.step_failed: TodoStatus.failed,
}


class TodoService:
    """会话级 Todo 清单服务：事件派生视图 + 状态标记。"""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    # ===================== 读看板 =====================
    async def get_board(self, session_id: UUID) -> TodoBoard:
        """读最新 plan_created 事件并回放其后的 todo_updated 事件。

        会话不存在 -> 404；会话没有 plan -> 404（"plan not found"）。
        """

        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found", code=404, status_code=404
            )

        events = await self.uow.session_events.list_by_session(session_id)
        plan_index = self._latest_plan_index(events)
        if plan_index is None:
            raise AppException(
                message="plan not found", code=404, status_code=404
            )

        board = TodoBoard.from_plan(events[plan_index].payload)
        # 只回放最新 plan 之后的 todo_updated 事件（重新规划后旧进度作废）。
        for event in events[plan_index + 1 :]:
            if event.type is SessionEventType.todo_updated:
                self._apply_todo_event(board, event.payload)
        return board

    # ===================== 手动标记 =====================
    async def update_status(
        self,
        session_id: UUID,
        todo_id: str,
        status: TodoStatus,
    ) -> dict[str, int | float]:
        """手动标记 todo 状态：校验流转 -> 写 todo_updated 事件。

        返回流转后的 progress 快照（事件 payload 中记录同一份快照）。
        """

        board = await self.get_board(session_id)
        if not any(item.id == todo_id for item in board.items):
            raise AppException(
                message=f"todo not found: {todo_id}", code=404, status_code=404
            )
        try:
            board.mark(status, todo_id)
        except ValueError as exc:
            raise AppException(
                message=str(exc), code=400, status_code=400
            ) from exc

        progress = board.progress()
        await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.todo_updated,
            payload=self._todo_event_payload(todo_id, status, progress),
        )
        await self.uow.commit()
        return progress

    # ===================== step 事件同步（供 T7 接线） =====================
    async def sync_from_step_event(
        self,
        session_id: UUID,
        step_event: SessionEvent,
    ) -> None:
        """把执行机的 step_completed / step_failed 事件同步到对应 todo。

        定位规则：优先按 payload 的 ``step_id`` 匹配 todo id；
        否则按 1 起的 ``index`` 换算成 0 起的 step_index 匹配。
        找不到对应 todo、目标状态与当前相同、或流转非法时静默返回
        （同步是尽力而为，不阻断执行主流程）。
        """

        target = _STEP_EVENT_STATUS.get(step_event.type)
        if target is None:
            return
        board = await self._board_or_none(session_id)
        if board is None:
            return
        item = self._match_step(board, step_event.payload)
        if item is None or item.status is target:
            return
        try:
            board.mark(target, item.id)
        except ValueError:
            # 流转非法（例如重试期间重复的 step_failed）：保持原状态。
            return

        progress = board.progress()
        await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.todo_updated,
            payload=self._todo_event_payload(item.id, target, progress),
        )
        await self.uow.commit()

    # ===================== 内部工具 =====================
    @staticmethod
    def _latest_plan_index(events: list[SessionEvent]) -> int | None:
        """返回最新 plan_created 事件在事件列表（升序）中的下标。"""

        index = None
        for i, event in enumerate(events):
            if event.type is SessionEventType.plan_created:
                index = i
        return index

    @staticmethod
    def _todo_event_payload(
        todo_id: str,
        status: TodoStatus,
        progress: dict[str, int | float],
    ) -> dict[str, object]:
        """todo_updated 事件 payload：todo 标识 + 状态 + progress 快照。"""

        return {
            "todo_id": todo_id,
            "status": status.value,
            "progress": dict(progress),
        }

    @staticmethod
    def _apply_todo_event(board: TodoBoard, payload: dict) -> None:
        """回放单条 todo_updated 事件；引用缺失或流转非法时跳过。"""

        todo_id = payload.get("todo_id")
        raw_status = payload.get("status")
        if not isinstance(todo_id, str) or not isinstance(raw_status, str):
            return
        try:
            status = TodoStatus(raw_status)
        except ValueError:
            return
        try:
            board.mark(status, todo_id)
        except ValueError:
            # 事件回放是重建视图：遇到无法应用的流转载继续，
            # 保证 board 总能从事件流完整重建。
            pass

    async def _board_or_none(self, session_id: UUID) -> TodoBoard | None:
        """内部读板：会话或 plan 不存在时返回 None（不抛错）。"""

        try:
            return await self.get_board(session_id)
        except AppException:
            return None

    @staticmethod
    def _match_step(board: TodoBoard, payload: dict) -> TodoItem | None:
        """按 step_id 优先、index 兜底的方式定位 todo。"""

        step_id = payload.get("step_id")
        if isinstance(step_id, str):
            for item in board.items:
                if item.id == step_id:
                    return item
        index = payload.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            for item in board.items:
                if item.step_index == index - 1:
                    return item
        return None
