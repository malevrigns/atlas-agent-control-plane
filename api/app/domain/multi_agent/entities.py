from dataclasses import dataclass


@dataclass(slots=True)
class MultiAgentRole:
    """多 Agent 协作中的一个角色。

    `key` 是程序识别用的稳定标识，`name` 和 `responsibility`
    用来给前端和接口调用方解释这个角色负责什么。
    """

    key: str
    name: str
    responsibility: str
    capability: str


@dataclass(slots=True)
class MultiAgentSubTask:
    """Manager Agent 分派给某个角色的子任务。"""

    id: str
    assignee: str
    title: str
    instruction: str
    expected_output: str
    status: str
    output: str


@dataclass(slots=True)
class MultiAgentReview:
    """Reviewer Agent 对协作结果的评审。"""

    reviewer: str
    status: str
    comments: list[str]
    improvement: str


@dataclass(slots=True)
class MultiAgentRunResult:
    """一次多 Agent 协作编排结果。

    这个结果会同时用于 HTTP API、AgentTool 输出和前端工具预览。
    """

    kind: str
    task: str
    manager: str
    roles: list[MultiAgentRole]
    subtasks: list[MultiAgentSubTask]
    review: MultiAgentReview
    final_answer: str
