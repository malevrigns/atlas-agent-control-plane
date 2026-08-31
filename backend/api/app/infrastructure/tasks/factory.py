"""AgentTaskQueue 工厂与后端注册表。

和 ``build_file_storage`` / ``build_vector_store`` 保持同一风格，但这里用
注册表而不是内联 if/else：新增一个后端只需要 ``register_queue_backend``，
不必修改本文件。这是「可插拔」的实际含义——扩展点不在核心文件里。

配置了不认识的后端时立即失败，绝不静默退回某个默认实现：静默兜底会让
「我以为在用 Redis，其实一直是单进程队列」这类问题拖到生产才暴露。
"""

from collections.abc import Callable

from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.tasks.queue import AgentTaskQueue

QueueBuilder = Callable[[], AgentTaskQueue]

_BACKENDS: dict[str, QueueBuilder] = {}


def register_queue_backend(name: str, builder: QueueBuilder) -> None:
    """注册一个队列后端实现。"""

    _BACKENDS[name.strip().lower()] = builder


def available_queue_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


def _build_redis_queue() -> AgentTaskQueue:
    from app.infrastructure.tasks.redis_queue import (
        RedisAgentTaskQueue,
        create_redis_client,
    )

    return RedisAgentTaskQueue(create_redis_client())


def _build_local_queue() -> AgentTaskQueue:
    from app.infrastructure.tasks.local_queue import LocalAgentTaskQueue

    return LocalAgentTaskQueue()


register_queue_backend("redis", _build_redis_queue)
register_queue_backend("local", _build_local_queue)


def build_task_queue(backend: str | None = None) -> AgentTaskQueue:
    """按配置创建任务队列。"""

    key = (backend or settings.agent_task_backend).strip().lower()
    builder = _BACKENDS.get(key)
    if builder is None:
        raise AppException(
            message=(
                f"unsupported agent task backend: {key}. "
                f"available: {', '.join(available_queue_backends())}"
            ),
            code=500,
            status_code=500,
        )
    return builder()
