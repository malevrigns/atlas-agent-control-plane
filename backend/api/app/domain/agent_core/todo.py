"""任务清单模型（Task Todo Model）。

把 PlannerAgent 生成的计划（plan_created 事件 payload）升级为**可追踪的
Todo 清单**：每项 todo 有独立状态机、完成前必须通过的验收命令引用
（verify_command，接 T1 验收门禁）以及前置依赖（depends_on）。

事件派生视图（不新增表）
========================
:class:`TodoBoard` 是**从 plan 派生的视图**：由 plan_created 事件的
payload 构建，可再叠加其后的 todo_updated 事件回放，得到当前进度。
它**不落库、不新增数据库表**——plan event（及 todo_updated 事件）
仍是唯一事实源，符合本项目"事件是事实源"的哲学；同一份事件流
重建出来的 board 永远一致，随时可以丢弃重算。

状态机（mark 的合法流转）
=========================
- pending     -> in_progress / done / skipped / failed
- in_progress -> done / failed
- done        -> （终态，不可回退——尤其不允许回 pending）
- failed      -> in_progress（retry 语义）/ skipped（放弃）
- skipped     -> pending（重新入列）

依赖满足语义
============
依赖"满足"= 被依赖项状态为 done **或** skipped：跳过是被依赖项被
显式放弃后的解锁方式，否则整条依赖链会永久阻塞。failed / in_progress
的被依赖项都不满足，其依赖者保持 pending 不可执行。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class TodoStatus(StrEnum):
    """单个 todo 项的状态。"""

    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"
    skipped = "skipped"


# 合法状态流转表：当前状态 -> 允许流转到的状态集合。
# 不在表内（或目标不在集合内）的流转由 TodoBoard.mark 拒绝。
_ALLOWED_TRANSITIONS: dict[TodoStatus, frozenset[TodoStatus]] = {
    # pending 可直接 failed：执行机在 todo 尚未标 in_progress 时就收到
    # step_failed（步骤开跑即失败）是真实存在的时序。
    TodoStatus.pending: frozenset(
        {TodoStatus.in_progress, TodoStatus.done, TodoStatus.skipped, TodoStatus.failed}
    ),
    TodoStatus.in_progress: frozenset({TodoStatus.done, TodoStatus.failed}),
    # done 是终态：不可回退（done 回 pending 是明确禁止的非法流转）。
    TodoStatus.done: frozenset(),
    # failed 允许重开为 in_progress，对应 retry 语义。
    TodoStatus.failed: frozenset({TodoStatus.in_progress, TodoStatus.skipped}),
    # skipped 允许重新入列。
    TodoStatus.skipped: frozenset({TodoStatus.pending}),
}


@dataclass(slots=True)
class TodoItem:
    """Todo 清单中的单个子任务。

    - ``id``：来自 plan step 的 id（字符串），是 mark / 依赖引用的主键；
    - ``verify_command``：该项完成前要跑的验证命令（接 T1 验收门禁），
      plan step 未声明时为 None；
    - ``depends_on``：前置 todo id 列表（拓扑依赖），空列表表示无依赖；
    - ``step_index``：映射回 plan steps 的位置下标（0 起），
      供执行机的 step 事件（payload 里的 1 起 index）定位本项。
    """

    id: str
    title: str
    description: str
    status: TodoStatus
    verify_command: str | None
    depends_on: list[str] = field(default_factory=list)
    step_index: int = 0


@dataclass(slots=True)
class TodoBoard:
    """会话级 Todo 看板：plan steps 的派生视图 + 状态机入口。

    见模块 docstring：本类不落库，事件才是事实源。
    """

    items: list[TodoItem] = field(default_factory=list)

    # ===================== 从 plan payload 构建 =====================
    @staticmethod
    def from_plan(plan: Mapping) -> "TodoBoard":
        """从 plan_created 事件的 payload 构建看板。

        每个 step 生成一个 todo（默认 pending、无依赖）；step 的可选字段
        ``verify_command`` / ``depends_on`` 若存在则读入。

        不变量：
        - ``steps`` 缺失或不是列表 -> ValueError；
        - depends_on 引用了不存在的 todo id -> ValueError；
        - depends_on 成环（含自依赖）-> ValueError，消息带环路径
          （形如 "a -> b -> a"）。
        """

        steps = plan.get("steps")
        if not isinstance(steps, (list, tuple)):
            raise ValueError("plan payload 缺少 steps 列表")

        items: list[TodoItem] = []
        for index, step in enumerate(steps):
            if not isinstance(step, Mapping):
                raise ValueError(f"plan steps[{index}] 必须是对象")
            step_id = str(step.get("id") or f"step-{index}")
            verify_command = step.get("verify_command")
            items.append(
                TodoItem(
                    id=step_id,
                    title=str(step.get("title") or f"步骤 {index + 1}"),
                    description=str(step.get("description") or ""),
                    status=TodoStatus.pending,
                    verify_command=(
                        str(verify_command) if isinstance(verify_command, str) else None
                    ),
                    depends_on=_clean_dependencies(step.get("depends_on")),
                    step_index=index,
                )
            )

        board = TodoBoard(items=items)
        _check_topology(board)
        return board

    # ===================== 下一个可执行项 =====================
    def next_runnable(self) -> TodoItem | None:
        """按依赖拓扑返回下一个可执行项。

        规则：按 step_index 顺序找**第一个** status=pending 且依赖全部
        满足（被依赖项为 done 或 skipped）的项。依赖未满足（含被依赖项
        failed / in_progress / pending）的项跳过。全部完成（或无可执行
        项）时返回 None。
        """

        status_by_id = {item.id: item.status for item in self.items}
        for item in sorted(self.items, key=lambda i: i.step_index):
            if item.status is not TodoStatus.pending:
                continue
            if all(
                status_by_id.get(dep) in (TodoStatus.done, TodoStatus.skipped)
                for dep in item.depends_on
            ):
                return item
        return None

    # ===================== 状态流转 =====================
    def mark(self, status: TodoStatus, todo_id: str) -> TodoItem:
        """把 todo_id 流转到目标状态，校验合法性后返回该项。

        非法流转（如 done -> pending）或 todo_id 不存在时抛 ValueError。
        """

        item = self._find(todo_id)
        current = item.status
        if status not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(
                f"非法 todo 状态流转: {current.value} -> {status.value} "
                f"(todo={todo_id})"
            )
        item.status = status
        return item

    # ===================== 进度快照 =====================
    def progress(self) -> dict[str, int | float]:
        """进度快照：{"total", "done", "failed", "pending", "percent"}。

        percent = done / total * 100（四舍五入到 1 位小数）；
        空看板返回全 0（percent=0.0）。
        """

        total = len(self.items)
        done = sum(1 for item in self.items if item.status is TodoStatus.done)
        failed = sum(1 for item in self.items if item.status is TodoStatus.failed)
        pending = sum(1 for item in self.items if item.status is TodoStatus.pending)
        percent = round(done * 100 / total, 1) if total else 0.0
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "pending": pending,
            "percent": percent,
        }

    # ===================== 内部工具 =====================
    def _find(self, todo_id: str) -> TodoItem:
        for item in self.items:
            if item.id == todo_id:
                return item
        raise ValueError(f"todo 不存在: {todo_id}")


def _clean_dependencies(raw: object) -> list[str]:
    """把 step 的 depends_on 清洗成 str 列表；缺失/空 -> []，类型错 -> 报错。"""

    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("depends_on 必须是列表")
    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("depends_on 的每一项必须是非空字符串")
        cleaned.append(entry.strip())
    return cleaned


def _check_topology(board: TodoBoard) -> None:
    """校验依赖拓扑：引用完整性 + 无环（含自依赖）。

    环用三色 DFS 找出具体路径，ValueError 消息形如：
    "todo 依赖成环: a -> b -> a"。
    """

    known = {item.id for item in board.items}
    for item in board.items:
        for dep in item.depends_on:
            if dep not in known:
                raise ValueError(f"depends_on 引用了不存在的 todo: {dep}")

    white, gray, black = 0, 1, 2
    color: dict[str, int] = {item.id: white for item in board.items}
    deps_by_id: dict[str, list[str]] = {
        item.id: item.depends_on for item in board.items
    }
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = gray
        path.append(node)
        for dep in deps_by_id[node]:
            if color[dep] == gray:
                # 找到环：从 dep 在 path 中的位置截断，首尾闭合。
                start = path.index(dep)
                return path[start:] + [dep]
            if color[dep] == white:
                found = dfs(dep)
                if found is not None:
                    return found
        path.pop()
        color[node] = black
        return None

    for item in board.items:
        if color[item.id] == white:
            cycle = dfs(item.id)
            if cycle is not None:
                raise ValueError("todo 依赖成环: " + " -> ".join(cycle))
