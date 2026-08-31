"""后台任务的领域实体。

这些类型原来住在 ``infrastructure/task_queue.py`` 里，和 Redis 实现绑在
一起。但「一个任务有哪些状态」「重试时父任务是谁」是领域概念，不是
Redis 概念——放在基础设施层会导致 presentation 层为了拿一个状态枚举
而 import 一个具体队列实现。
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class AgentTaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"
    # 兼容早期章节已经返回过的状态值。
    succeeded = "succeeded"
    cancelled = "cancelled"


#: 任务不再会被消费的状态集合。
TERMINAL_STATUSES = frozenset(
    {
        AgentTaskStatus.completed,
        AgentTaskStatus.succeeded,
        AgentTaskStatus.failed,
        AgentTaskStatus.stopped,
        AgentTaskStatus.cancelled,
    }
)

#: 用户主动中止的状态集合：这类消息可以安全 ACK，不需要交给下一个实例。
ABORTED_STATUSES = frozenset({AgentTaskStatus.stopped, AgentTaskStatus.cancelled})


@dataclass(slots=True)
class AgentTask:
    id: str
    session_id: UUID
    type: str
    status: AgentTaskStatus
    error: str | None
    created_at: str
    updated_at: str
    parent_task_id: str | None = None
    retry_count: int = 0

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_aborted(self) -> bool:
        return self.status in ABORTED_STATUSES


@dataclass(slots=True)
class QueuedTaskMessage:
    """一条待消费的队列消息。

    ``id`` 是投递标识（ack 时用），与 ``payload["task_id"]`` 不是一回事：
    同一个任务重试会产生新的任务，而同一个任务也可能被重新投递。
    """

    id: str
    payload: dict
