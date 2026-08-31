"""向后兼容的再导出层。

第 20 章之后，任务队列被拆成「领域端口 + 可插拔适配器」：

- 端口与实体：``app.domain.tasks``
- Redis 适配器：``app.infrastructure.tasks.redis_queue``
- 进程内适配器：``app.infrastructure.tasks.local_queue``

教程正文和早期代码里大量出现 ``from app.infrastructure.task_queue import
...``，所以这个模块保留下来做再导出。新代码请直接依赖
``app.domain.tasks.queue.AgentTaskQueue`` 这个端口。
"""

from app.domain.tasks.entities import (
    ABORTED_STATUSES,
    TERMINAL_STATUSES,
    AgentTask,
    AgentTaskStatus,
    QueuedTaskMessage,
)
from app.domain.tasks.queue import AgentTaskQueue
from app.infrastructure.tasks.factory import build_task_queue
from app.infrastructure.tasks.local_queue import LocalAgentTaskQueue
from app.infrastructure.tasks.redis_queue import RedisAgentTaskQueue, create_redis_client

__all__ = [
    "ABORTED_STATUSES",
    "TERMINAL_STATUSES",
    "AgentTask",
    "AgentTaskQueue",
    "AgentTaskStatus",
    "LocalAgentTaskQueue",
    "QueuedTaskMessage",
    "RedisAgentTaskQueue",
    "build_task_queue",
    "create_redis_client",
]
