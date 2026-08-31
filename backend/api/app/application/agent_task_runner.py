import asyncio
from contextlib import suppress
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.agent_runner_service import AgentRunnerService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.sessions.entities import SessionEvent, SessionEventType
from app.domain.tasks.entities import AgentTask, QueuedTaskMessage
from app.domain.tasks.queue import AgentTaskQueue


class AgentTaskRunner:
    """从任务队列消费 Agent 任务，并在后台执行。

    第 19 章的执行接口是同步请求：浏览器要等执行结束。
    第 20 章把执行请求拆成两段：
    1. API 只负责把任务放进队列。
    2. Runner 在后台读取任务并执行。

    依赖的是 ``AgentTaskQueue`` 端口，因此同一套调度逻辑既能跑在 Redis
    上，也能跑在单机的进程内队列上。
    """

    def __init__(
        self,
        queue: AgentTaskQueue,
        session_factory: async_sessionmaker,
    ) -> None:
        # ===================== 第1步：保存队列和数据库会话工厂 =====================
        self.queue = queue
        self.session_factory = session_factory
        self._running = False
        self._task: asyncio.Task | None = None
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(settings.agent_task_max_concurrency)

    # ===================== 第2步：启动后台循环 =====================
    def start(self) -> None:
        """在 FastAPI 启动时创建后台任务。"""

        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    # ===================== 第3步：停止后台循环 =====================
    async def stop(self) -> None:
        """在 FastAPI 关闭时停止后台任务。"""

        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        active = list(self._active_tasks.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        self._active_tasks.clear()

    def cancel_task(self, task_id: str) -> bool:
        """Cooperatively cancel the coroutine that owns an executing task."""

        active = self._active_tasks.get(task_id)
        if active is None or active.done():
            return False
        active.cancel()
        return True

    # ===================== 第4步：循环读取任务队列 =====================
    async def _run_loop(self) -> None:
        """不断读取队列中的新任务。"""

        await self.queue.start()
        recovered = await self.queue.reclaim_stale_messages()
        for message in recovered:
            self._start_message(message)

        while self._running:
            try:
                await self._wait_for_capacity()
                for message in await self.queue.reserve_messages(count=1):
                    self._start_message(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 这里不能让单次任务异常杀死整个后台循环。
                # 真实项目会接入结构化日志和告警；本章先保证 Runner 可以继续消费下一条任务。
                await asyncio.sleep(1)

    async def _wait_for_capacity(self) -> None:
        while len(self._active_tasks) >= settings.agent_task_max_concurrency:
            await asyncio.wait(
                list(self._active_tasks.values()),
                return_when=asyncio.FIRST_COMPLETED,
            )

    def _start_message(self, message: QueuedTaskMessage) -> None:
        task_id = str(message.payload.get("task_id") or message.id)
        if task_id in self._active_tasks:
            return
        task = asyncio.create_task(self._process_message(message))
        self._active_tasks[task_id] = task
        task.add_done_callback(lambda _task, key=task_id: self._active_tasks.pop(key, None))

    async def _process_message(self, message: QueuedTaskMessage) -> None:
        async with self._semaphore:
            should_acknowledge = False
            try:
                should_acknowledge = await self._handle_message(message.payload)
            except asyncio.CancelledError:
                # 用户取消会先把队列状态写成 stopped；这种消息可以 ACK。
                # 进程关闭造成的协程取消不 ACK，让 pending 消息由下一实例接管。
                task_id = str(message.payload.get("task_id") or "")
                task = await asyncio.shield(self.queue.get_task(task_id)) if task_id else None
                should_acknowledge = bool(task and task.is_aborted)
                raise
            finally:
                if should_acknowledge:
                    await asyncio.shield(self.queue.acknowledge(message.id))

    # ===================== 第5步：处理单条任务消息 =====================
    async def _handle_message(self, payload: dict) -> bool:
        """根据任务类型分发到具体执行方法。"""

        task_id = str(payload.get("task_id", ""))
        task_type = str(payload.get("type", ""))
        session_id_text = str(payload.get("session_id", ""))
        if not task_id or not session_id_text:
            return True

        task = await self.queue.get_task(task_id)
        if task is None or self._is_stopped_or_cancelled(task):
            return True

        await self.queue.mark_running(task_id)
        try:
            completed = await self._execute_task(
                task_id=task_id,
                task_type=task_type,
                session_id_text=session_id_text,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self.queue.mark_failed(task_id, str(error))
            return True

        if not completed:
            return True
        latest_task = await self.queue.get_task(task_id)
        if latest_task is not None and self._is_stopped_or_cancelled(latest_task):
            return True
        await self.queue.mark_succeeded(task_id)
        return True

    async def _execute_task(
        self,
        *,
        task_id: str,
        task_type: str,
        session_id_text: str,
    ) -> bool:
        if task_type != "execute_plan":
            raise ValueError(f"unsupported task type: {task_type}")

        execution_events = await self._execute_plan(UUID(session_id_text))
        blocked_event = self._find_event(
            execution_events,
            SessionEventType.step_blocked,
        )
        if blocked_event is not None:
            reason = str(blocked_event.payload.get("summary") or "approval required")
            await self.queue.mark_waiting(task_id, reason)
            return False

        error_event = self._find_event(
            execution_events,
            SessionEventType.task_error,
        )
        if error_event is not None:
            message = str(error_event.payload.get("message") or "task failed")
            raise RuntimeError(message)
        return True

    @staticmethod
    def _find_event(
        events: list[SessionEvent],
        event_type: SessionEventType,
    ) -> SessionEvent | None:
        for event in events:
            if event.type is event_type:
                return event
        return None

    @staticmethod
    def _is_stopped_or_cancelled(task: AgentTask) -> bool:
        return task.is_aborted

    # ===================== 第6步：真正调用 ReActAgentService =====================
    async def _execute_plan(self, session_id: UUID):
        """为后台任务创建独立数据库会话，再复用第 19 章执行逻辑。"""

        async with self.session_factory() as db_session:
            service = AgentRunnerService.from_uow(UnitOfWork(db_session))
            return await service.execute_latest_plan(session_id)
