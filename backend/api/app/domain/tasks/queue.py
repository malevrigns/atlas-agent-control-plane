"""AgentTaskQueue 端口。

应用层（AgentTaskRunner）和 presentation 层只依赖这个协议，不关心任务
到底放在 Redis Stream 还是进程内的内存结构里。

方法名刻意避开任何 Redis 词汇：没有 ``xreadgroup``、没有 ``consumer
group``。``reserve_messages`` 表达的是「取出若干条并暂时归我所有」，
``acknowledge`` 表达的是「这条我处理完了，别再投给别人」。任何实现只要
能提供这两个语义就能接进来。

实现必须满足的语义契约（由 tests/test_task_queue_contract.py 统一验证）：

1. ``reserve_messages`` 取到的消息在 ``acknowledge`` 之前不会被同一队列
   的另一次 ``reserve_messages`` 重复取出；
2. 未 ACK 且超过滞留时限的消息，必须能被 ``reclaim_stale_messages``
   重新取回——否则消费者崩溃会永久丢任务；
3. ``enqueue_execute_plan`` 之前入队的消息，在消费者启动后仍可被读到
   （即队列不能只投递「在线」消费者）；
4. 终态任务上调用 ``cancel_task`` 是幂等的，不改变已有终态；
5. ``retry_task`` 只对终态任务生效，并产生一个 ``retry_count`` 递增、
   ``parent_task_id`` 指向原任务的新任务。
"""

from typing import Protocol
from uuid import UUID

from app.domain.tasks.entities import AgentTask, QueuedTaskMessage


class AgentTaskQueue(Protocol):
    """后台任务队列协议。"""

    #: 供状态接口与运维面板展示的后端标识。
    backend_name: str

    async def start(self) -> None:
        """准备好消费所需的结构（建 consumer group / 建内存索引）。"""

        raise NotImplementedError

    async def close(self) -> None:
        """释放连接与后台资源。"""

        raise NotImplementedError

    async def enqueue_execute_plan(
        self,
        session_id: UUID,
        *,
        parent_task_id: str | None = None,
        retry_count: int = 0,
    ) -> AgentTask:
        """创建一个执行计划任务并投递，返回任务快照。"""

        raise NotImplementedError

    async def reserve_messages(self, *, count: int = 1) -> list[QueuedTaskMessage]:
        """取出至多 count 条待处理消息，并标记为「已被本消费者取走」。"""

        raise NotImplementedError

    async def reclaim_stale_messages(self, *, count: int = 100) -> list[QueuedTaskMessage]:
        """取回滞留过久（消费者疑似崩溃）的未 ACK 消息。"""

        raise NotImplementedError

    async def acknowledge(self, message_id: str) -> None:
        """确认一条消息已处理完毕。"""

        raise NotImplementedError

    async def get_task(self, task_id: str) -> AgentTask | None:
        raise NotImplementedError

    async def cancel_task(self, task_id: str) -> AgentTask | None:
        """请求停止任务；已是终态时原样返回。"""

        raise NotImplementedError

    async def retry_task(self, task_id: str) -> AgentTask | None:
        """基于终态任务派生一个新任务。"""

        raise NotImplementedError

    async def recover_session_task(self, session_id: UUID) -> AgentTask | None:
        """读取某会话最近一次后台任务。"""

        raise NotImplementedError

    async def mark_running(self, task_id: str) -> AgentTask | None:
        raise NotImplementedError

    async def mark_waiting(self, task_id: str, reason: str | None = None) -> AgentTask | None:
        raise NotImplementedError

    async def mark_succeeded(self, task_id: str) -> AgentTask | None:
        raise NotImplementedError

    async def mark_failed(self, task_id: str, error: str) -> AgentTask | None:
        raise NotImplementedError

    async def health(self) -> dict[str, object]:
        """返回后端健康信息，供状态接口使用。"""

        raise NotImplementedError
