"""Todo 清单 HTTP 路由（T6）。

- GET  /sessions/{session_id}/todos                       读看板 + progress
- POST /sessions/{session_id}/todos/{todo_id}/status       手动标记状态

board 是 plan_created 事件的派生视图（不落库），
本路由只做读视图与写 todo_updated 事件两件事。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.todo_service import TodoService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.todo import TodoBoard, TodoItem, TodoStatus
from app.infrastructure.database.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.todo import (
    TodoBoardResponse,
    TodoItemResponse,
    TodoProgressResponse,
    TodoStatusUpdateRequest,
)

router = APIRouter(prefix="/sessions", tags=["todos"])


def build_todo_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> TodoService:
    """构建 TodoService（与同包路由相同的 db session 依赖模式）。"""

    return TodoService(UnitOfWork(db_session))


@router.get(
    "/{session_id}/todos",
    response_model=ApiResponse[TodoBoardResponse],
)
async def get_session_todos(
    session_id: UUID,
    service: TodoService = Depends(build_todo_service),
) -> ApiResponse[TodoBoardResponse]:
    """读取会话 Todo 看板（items + 内嵌 progress + 下一个可执行项）。"""

    board = await service.get_board(session_id)
    return ApiResponse(data=to_board_response(board))


@router.post(
    "/{session_id}/todos/{todo_id}/status",
    response_model=ApiResponse[TodoProgressResponse],
)
async def update_todo_status(
    session_id: UUID,
    todo_id: str,
    payload: TodoStatusUpdateRequest,
    service: TodoService = Depends(build_todo_service),
) -> ApiResponse[TodoProgressResponse]:
    """手动标记 todo 状态；返回流转后的 progress 快照。"""

    try:
        status = TodoStatus(payload.status)
    except ValueError as exc:
        raise AppException(
            message=f"invalid status: {payload.status}",
            code=400,
            status_code=400,
        ) from exc
    progress = await service.update_status(session_id, todo_id, status)
    return ApiResponse(data=to_progress_response(progress))


# ===================== 响应构建 =====================
def to_item_response(item: TodoItem) -> TodoItemResponse:
    """TodoItem -> 响应模型。"""

    return TodoItemResponse(
        id=item.id,
        title=item.title,
        description=item.description,
        status=item.status.value,
        verify_command=item.verify_command,
        depends_on=list(item.depends_on),
        step_index=item.step_index,
    )


def to_progress_response(progress: dict[str, int | float]) -> TodoProgressResponse:
    """progress 快照 -> 响应模型。"""

    return TodoProgressResponse(
        total=int(progress["total"]),
        done=int(progress["done"]),
        failed=int(progress["failed"]),
        pending=int(progress["pending"]),
        percent=float(progress["percent"]),
    )


def to_board_response(board: TodoBoard) -> TodoBoardResponse:
    """TodoBoard -> 响应模型（progress 内嵌）。"""

    next_runnable = board.next_runnable()
    return TodoBoardResponse(
        items=[to_item_response(item) for item in board.items],
        progress=to_progress_response(board.progress()),
        next_runnable=to_item_response(next_runnable) if next_runnable else None,
    )
