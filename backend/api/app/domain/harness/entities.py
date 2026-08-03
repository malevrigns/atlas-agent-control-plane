from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class HarnessExpectation:
    """一条评测用例的断言规则。

    Harness 不直接理解“任务做得好不好”的所有语义，它先检查几个稳定信号：
    任务是否结束、关键工具是否被调用、是否出现禁止事件、是否生成关键产物。
    """

    required_events: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_files: list[str] = field(default_factory=list)
    forbidden_events: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HarnessCase:
    """固定任务集中的一条 Agent 回归任务。"""

    id: str
    title: str
    task: str
    description: str
    tags: list[str]
    expectation: HarnessExpectation


@dataclass(slots=True)
class HarnessAssertion:
    """一次 Harness 运行里的单条断言结果。"""

    name: str
    passed: bool
    detail: str


@dataclass(slots=True)
class HarnessRun:
    """一次 Harness 运行结果。

    第 45 章先把运行结果保存在 API 进程内存中，方便快速理解流程。
    后续如果要做团队共享评测报告，可以再把它落到数据库表中。
    """

    id: str
    case_id: str
    mode: str
    status: str
    task: str
    prompt_summary: str
    events: list[dict]
    assertions: list[HarnessAssertion]
    started_at: datetime
    completed_at: datetime | None
