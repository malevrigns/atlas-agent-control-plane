"""Todo 清单的 HTTP 响应/请求 schema（T6）。

字段全部显式声明：board 是 plan 事件的派生视图，
progress 内嵌在 board 响应里，前端可直接渲染进度。
"""

from pydantic import BaseModel, Field


class TodoItemResponse(BaseModel):
    """单个 todo 子任务。"""

    # 对应 plan step 的 id（字符串），是状态标记的标识。
    id: str
    title: str
    description: str
    # pending / in_progress / done / failed / skipped
    status: str
    # 该项完成前要跑的验证命令（接 T1 验收门禁）；未声明为 null。
    verify_command: str | None
    # 前置 todo id 列表（拓扑依赖）。
    depends_on: list[str]
    # 映射回 plan steps 的位置下标（0 起）。
    step_index: int


class TodoProgressResponse(BaseModel):
    """进度快照（percent = done / total * 100，1 位小数）。"""

    total: int
    done: int
    failed: int
    pending: int
    percent: float


class TodoBoardResponse(BaseModel):
    """会话 Todo 看板：items + 内嵌 progress + 下一个可执行项。"""

    items: list[TodoItemResponse]
    progress: TodoProgressResponse
    # 按依赖拓扑的下一个可执行项；无可执行项（含全部完成）时为 null。
    next_runnable: TodoItemResponse | None = None


class TodoStatusUpdateRequest(BaseModel):
    """手动标记请求体：{"status": "in_progress"}。"""

    # 只接受 5 个合法状态字面量之一，其余 422。
    status: str = Field(
        pattern="^(pending|in_progress|done|failed|skipped)$",
        description="目标状态：pending / in_progress / done / failed / skipped",
    )
