"""工具依赖声明与执行计划（Dependency Graph）。

工具通过 ToolDefinition 的 provides / requires 声明能力标签
（capability tags，如 "web_content"、"file_path"、"page_opened"）。
一轮内模型可能请求多个工具调用，plan_parallel_batches() 按依赖关系
把它们拓扑排序成若干批次：

- 无依赖（或依赖已被更早批次满足）的调用进入同一批次，可并行执行；
- 有依赖的调用必须排到依赖者之后的批次，批间串行等待；
- 发现循环依赖时抛出 ToolDependencyError（附带环路径）。

纯 domain 层实现：只做图计算，不真正执行工具，
由 StepAgentLoop 在执行入口接线（同批 asyncio.gather，批间 await）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppException, ErrorType


class ToolDependencyError(AppException):
    """工具依赖声明中存在循环依赖。

    cycle 记录环上的工具名路径（首尾同名），便于定位声明问题。
    """

    def __init__(self, cycle: Sequence[str]) -> None:
        self.cycle: tuple[str, ...] = tuple(cycle)
        super().__init__(
            message=f"tool dependency cycle detected: {' -> '.join(self.cycle)}",
            code=500,
            status_code=500,
            error_type=ErrorType.internal,
            details={"cycle": list(self.cycle)},
        )


@dataclass(slots=True)
class ToolCall:
    """一次工具调用（携带能力标签），是执行计划的基本单元。

    name / arguments 与模型的 function call 对应；
    provides / requires 来自工具定义（ToolDefinition）。
    """

    name: str
    arguments: dict[str, Any]
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    call_id: str | None = None


def tool_call_from_definition(
    definition: Any,
    arguments: dict[str, Any],
    *,
    call_id: str | None = None,
) -> ToolCall:
    """从 ToolDefinition 构造 ToolCall，复制其 provides / requires 标签。"""

    return ToolCall(
        name=definition.name,
        arguments=dict(arguments),
        provides=tuple(definition.provides),
        requires=tuple(definition.requires),
        call_id=call_id,
    )


def plan_parallel_batches(calls: list[ToolCall]) -> list[list[ToolCall]]:
    """把一轮工具调用按依赖关系拓扑排序成并行批次。

    规则：
    - 调用 A requires 的标签只要被本批列表之外的工具提供，
      视为外部已满足，不构成排序约束（例如浏览器状态由上一步留下）；
    - 调用 B requires 标签 T，且同一次请求列表中的调用 A provides T，
      则 B 必须排在 A 之后的批次；
    - 每个批次内无相互依赖，调用方可并行执行；
    - 批次内保持输入顺序，便于复现与审计。

    发现循环依赖时抛出 :class:`ToolDependencyError`。
    """

    if not calls:
        return []

    # tag -> 提供该 tag 的调用下标
    providers: dict[str, list[int]] = {}
    for index, call in enumerate(calls):
        for tag in call.provides:
            providers.setdefault(tag, []).append(index)

    # 下标 -> 必须先于它执行的下标集合（只统计列表内的依赖边）
    depends_on: list[set[int]] = [set() for _ in calls]
    for index, call in enumerate(calls):
        for tag in call.requires:
            for provider in providers.get(tag, ()):
                if provider != index:
                    depends_on[index].add(provider)

    remaining = set(range(len(calls)))
    satisfied: set[int] = set()
    batches: list[list[ToolCall]] = []
    while remaining:
        ready = sorted(index for index in remaining if depends_on[index] <= satisfied)
        if not ready:
            cycle = _find_cycle(calls, remaining, depends_on)
            raise ToolDependencyError(cycle)
        batches.append([calls[index] for index in ready])
        satisfied.update(ready)
        remaining.difference_update(ready)
    return batches


def _find_cycle(
    calls: list[ToolCall],
    remaining: set[int],
    depends_on: list[set[int]],
) -> list[str]:
    """在剩余子图中用 DFS 找一条环路径，返回工具名序列（首尾同名）。"""

    white, gray, black = 0, 1, 2
    color = {index: white for index in remaining}
    path: list[int] = []

    def dfs(index: int) -> list[int] | None:
        color[index] = gray
        path.append(index)
        for dependency in sorted(depends_on[index] & remaining):
            if color[dependency] == gray:
                # 找到环：从 dependency 在 path 中的位置截断
                start = path.index(dependency)
                cycle = path[start:] + [dependency]
                return [calls[i].name for i in cycle]
            if color[dependency] == white:
                found = dfs(dependency)
                if found is not None:
                    return found
        path.pop()
        color[index] = black
        return None

    for index in sorted(remaining):
        if color[index] == white:
            found = dfs(index)
            if found is not None:
                return found
    # 理论上不可达（Kahn 已判定存在环），兜底返回剩余节点名。
    return [calls[index].name for index in sorted(remaining)] + [
        calls[sorted(remaining)[0]].name
    ]
