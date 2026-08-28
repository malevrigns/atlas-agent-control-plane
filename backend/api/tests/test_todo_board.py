"""Todo 清单模型（TodoBoard）单元测试。

覆盖（见 T6 任务要求）：
- from_plan：常规构建、带依赖/verify_command、环检测报错（含自依赖）、
  引用完整性、空 plan；
- next_runnable：依赖未满足跳过、依赖 done/skipped 解锁、
  failed 阻塞、全部完成返回 None；
- mark：非法流转拒绝（done 不可回退）、failed -> in_progress 允许（retry）、
  pending -> done 直接勾选允许、未知 id 报错；
- progress：百分比数学正确（含空看板）。
"""

import unittest

from app.domain.agent_core.todo import TodoBoard, TodoItem, TodoStatus


def _step(step_id: str, **extra):
    """构造一个 plan step 字典（最小合法形状 + 可选覆盖字段）。"""

    step = {"id": step_id, "title": f"步骤 {step_id}", "description": f"描述 {step_id}"}
    step.update(extra)
    return step


def _plan(steps) -> dict:
    """构造 plan_created 事件 payload 形状。"""

    return {"id": "plan-1", "title": "计划", "goal": "目标", "steps": steps}


def _status_by_id(board: TodoBoard) -> dict[str, TodoStatus]:
    return {item.id: item.status for item in board.items}


class FromPlanTest(unittest.TestCase):
    def test_default_pending_no_dependencies(self) -> None:
        """无可选字段时：全部 pending、无依赖、无验收命令、step_index 0 起。"""

        board = TodoBoard.from_plan(
            _plan([_step("a"), _step("b"), _step("c")])
        )
        self.assertEqual([item.id for item in board.items], ["a", "b", "c"])
        for index, item in enumerate(board.items):
            self.assertIs(item.status, TodoStatus.pending)
            self.assertEqual(item.depends_on, [])
            self.assertIsNone(item.verify_command)
            self.assertEqual(item.step_index, index)
        # 标题/描述从 step 读入
        self.assertEqual(board.items[0].title, "步骤 a")
        self.assertEqual(board.items[0].description, "描述 a")

    def test_reads_optional_verify_command_and_depends_on(self) -> None:
        """step 的 verify_command / depends_on 可选字段被读入。"""

        board = TodoBoard.from_plan(
            _plan(
                [
                    _step("a"),
                    _step(
                        "b",
                        verify_command="uv run pytest tests/",
                        depends_on=["a"],
                    ),
                ]
            )
        )
        b = board.items[1]
        self.assertEqual(b.verify_command, "uv run pytest tests/")
        self.assertEqual(b.depends_on, ["a"])

    def test_missing_steps_raises(self) -> None:
        """steps 缺失或不是列表 -> ValueError。"""

        with self.assertRaises(ValueError):
            TodoBoard.from_plan({"title": "无 steps"})
        with self.assertRaises(ValueError):
            TodoBoard.from_plan(_plan("not-a-list"))

    def test_step_must_be_mapping(self) -> None:
        """steps 里出现非对象 -> ValueError。"""

        with self.assertRaises(ValueError):
            TodoBoard.from_plan(_plan(["不是对象"]))

    def test_cycle_detected_with_path(self) -> None:
        """a/b/c 互相依赖成环：ValueError 且消息带环路径（沿依赖边方向）。"""
        plan = _plan(
            [
                _step("a", depends_on=["c"]),
                _step("b", depends_on=["a"]),
                _step("c", depends_on=["b"]),
            ]
        )
        with self.assertRaises(ValueError) as ctx:
            TodoBoard.from_plan(plan)
        # 环路径沿 depends_on 方向：a 依赖 c、c 依赖 b、b 依赖 a
        self.assertIn("a -> c -> b -> a", str(ctx.exception))

    def test_self_dependency_detected(self) -> None:
        """自依赖（a 依赖 a）也视为环。"""

        plan = _plan([_step("a", depends_on=["a"])])
        with self.assertRaises(ValueError) as ctx:
            TodoBoard.from_plan(plan)
        self.assertIn("a -> a", str(ctx.exception))

    def test_unknown_dependency_raises(self) -> None:
        """depends_on 引用不存在的 todo id -> ValueError（防止永久阻塞）。"""

        plan = _plan([_step("a", depends_on=["ghost"])])
        with self.assertRaises(ValueError) as ctx:
            TodoBoard.from_plan(plan)
        self.assertIn("ghost", str(ctx.exception))

    def test_empty_steps_gives_empty_board(self) -> None:
        """steps 为空列表：空看板，next_runnable 为 None，progress 全 0。"""

        board = TodoBoard.from_plan(_plan([]))
        self.assertEqual(board.items, [])
        self.assertIsNone(board.next_runnable())
        self.assertEqual(
            board.progress(),
            {"total": 0, "done": 0, "failed": 0, "pending": 0, "percent": 0.0},
        )


class NextRunnableTest(unittest.TestCase):
    def test_first_pending_without_deps(self) -> None:
        """无依赖时返回最前 pending 项。"""

        board = TodoBoard.from_plan(_plan([_step("a"), _step("b")]))
        self.assertEqual(board.next_runnable().id, "a")
        board.mark(TodoStatus.in_progress, "a")
        # a 执行中时，b 可执行
        self.assertEqual(board.next_runnable().id, "b")

    def test_unsatisfied_dependency_skipped(self) -> None:
        """依赖未满足（被依赖项 in_progress）时跳过该项。"""

        board = TodoBoard.from_plan(
            _plan([_step("a"), _step("b", depends_on=["a"]), _step("c")])
        )
        board.mark(TodoStatus.in_progress, "a")
        # b 依赖 a（in_progress 不算满足）被跳过，轮到 c
        self.assertEqual(board.next_runnable().id, "c")

    def test_dependency_done_unlocks(self) -> None:
        """被依赖项 done 后，依赖者变为可执行。"""

        board = TodoBoard.from_plan(
            _plan([_step("a"), _step("b", depends_on=["a"])])
        )
        board.mark(TodoStatus.done, "a")
        self.assertEqual(board.next_runnable().id, "b")

    def test_dependency_skipped_unlocks(self) -> None:
        """被依赖项被显式跳过（skipped）后也解锁依赖者，避免永久阻塞。"""

        board = TodoBoard.from_plan(
            _plan([_step("a"), _step("b", depends_on=["a"])])
        )
        board.mark(TodoStatus.skipped, "a")
        self.assertEqual(board.next_runnable().id, "b")

    def test_dependency_failed_blocks(self) -> None:
        """被依赖项 failed 时不满足：依赖者保持不可执行。"""

        board = TodoBoard.from_plan(
            _plan([_step("a"), _step("b", depends_on=["a"])])
        )
        board.mark(TodoStatus.failed, "a")
        self.assertIsNone(board.next_runnable())

    def test_all_done_returns_none(self) -> None:
        """全部完成返回 None。"""

        board = TodoBoard.from_plan(_plan([_step("a"), _step("b")]))
        board.mark(TodoStatus.done, "a")
        board.mark(TodoStatus.done, "b")
        self.assertIsNone(board.next_runnable())

    def test_orders_by_step_index_not_list_order(self) -> None:
        """手工乱序 items 时，按 step_index 而非列表顺序取最前项。"""

        board = TodoBoard(
            items=[
                TodoItem(id="z", title="z", description="", status=TodoStatus.pending,
                         verify_command=None, depends_on=[], step_index=2),
                TodoItem(id="y", title="y", description="", status=TodoStatus.pending,
                         verify_command=None, depends_on=[], step_index=0),
            ]
        )
        self.assertEqual(board.next_runnable().id, "y")


class MarkTransitionTest(unittest.TestCase):
    def test_done_cannot_go_back_to_pending(self) -> None:
        """done 不可回 pending（任务明确要求的非法流转）。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        board.mark(TodoStatus.done, "a")
        with self.assertRaises(ValueError) as ctx:
            board.mark(TodoStatus.pending, "a")
        self.assertIn("done -> pending", str(ctx.exception))

    def test_done_is_terminal(self) -> None:
        """done 是终态：任何流转（含 in_progress / failed）都拒绝。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        board.mark(TodoStatus.done, "a")
        for target in (
            TodoStatus.in_progress,
            TodoStatus.failed,
            TodoStatus.skipped,
        ):
            with self.assertRaises(ValueError):
                board.mark(target, "a")

    def test_failed_to_in_progress_allowed_for_retry(self) -> None:
        """failed 允许重开为 in_progress（retry 语义）。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        board.mark(TodoStatus.in_progress, "a")
        board.mark(TodoStatus.failed, "a")
        board.mark(TodoStatus.in_progress, "a")
        self.assertIs(_status_by_id(board)["a"], TodoStatus.in_progress)
        # 重试后可以再次完成
        board.mark(TodoStatus.done, "a")
        self.assertIs(_status_by_id(board)["a"], TodoStatus.done)

    def test_pending_to_done_allowed(self) -> None:
        """pending 可直接勾选 done（前端直接勾选 / 事件回放都依赖此流转）。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        board.mark(TodoStatus.done, "a")
        self.assertIs(_status_by_id(board)["a"], TodoStatus.done)

    def test_in_progress_to_pending_rejected(self) -> None:
        """in_progress 不可回 pending（开始执行后不能"取消开始"）。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        board.mark(TodoStatus.in_progress, "a")
        with self.assertRaises(ValueError):
            board.mark(TodoStatus.pending, "a")

    def test_unknown_todo_id_raises(self) -> None:
        """mark 不存在的 id -> ValueError。"""

        board = TodoBoard.from_plan(_plan([_step("a")]))
        with self.assertRaises(ValueError) as ctx:
            board.mark(TodoStatus.done, "ghost")
        self.assertIn("ghost", str(ctx.exception))

    def test_status_enum_has_exactly_five_values(self) -> None:
        """状态枚举固定 5 个值，与 schema 的 pattern 校验一致。"""

        self.assertEqual(
            {s.value for s in TodoStatus},
            {"pending", "in_progress", "done", "failed", "skipped"},
        )


class ProgressTest(unittest.TestCase):
    def test_percent_math(self) -> None:
        """百分比 = done / total * 100，四舍五入 1 位。"""

        board = TodoBoard.from_plan(_plan([_step(str(i)) for i in range(4)]))
        # done, done, failed, pending
        board.mark(TodoStatus.done, "0")
        board.mark(TodoStatus.done, "1")
        board.mark(TodoStatus.in_progress, "2")
        board.mark(TodoStatus.failed, "2")
        self.assertEqual(
            board.progress(),
            {"total": 4, "done": 2, "failed": 1, "pending": 1, "percent": 50.0},
        )

    def test_third_is_rounded_to_one_decimal(self) -> None:
        """1/3 -> 33.3（1 位小数）。"""

        board = TodoBoard.from_plan(_plan([_step("a"), _step("b"), _step("c")]))
        board.mark(TodoStatus.done, "a")
        progress = board.progress()
        self.assertEqual(progress["percent"], 33.3)
        self.assertEqual(progress["done"], 1)

    def test_one_of_six(self) -> None:
        """1/6 -> 16.7。"""

        board = TodoBoard.from_plan(_plan([_step(str(i)) for i in range(6)]))
        board.mark(TodoStatus.done, "3")
        self.assertEqual(board.progress()["percent"], 16.7)

    def test_empty_board_percent_zero(self) -> None:
        """空看板 percent = 0.0（不除零）。"""

        board = TodoBoard.from_plan(_plan([]))
        self.assertEqual(board.progress()["percent"], 0.0)

    def test_pending_counts_strict_pending_only(self) -> None:
        """pending 计数只含严格 pending（in_progress / skipped 不算）。"""

        board = TodoBoard.from_plan(_plan([_step("a"), _step("b"), _step("c")]))
        board.mark(TodoStatus.in_progress, "a")
        board.mark(TodoStatus.skipped, "b")
        progress = board.progress()
        self.assertEqual(progress["pending"], 1)
        self.assertEqual(progress["total"], 3)


if __name__ == "__main__":
    unittest.main()
