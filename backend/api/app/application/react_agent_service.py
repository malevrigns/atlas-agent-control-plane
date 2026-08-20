from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.agent_execution_types import plan_revision
from app.application.context_engineering_service import ContextEngineeringService
from app.application.session_file_sync_service import SessionFileSyncService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException, build_task_error_payload
from app.domain.agent_runtime.entities import ReflectionAction
from app.domain.sessions.entities import (
    MessageRole,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)


@dataclass(frozen=True, slots=True)
class ExecutionRunIdentity:
    run_id: UUID
    plan_id: str
    plan_revision: int


class ReActAgentService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        execution_machine: AgentExecutionMachine,
        file_sync_service: SessionFileSyncService,
        context_service: ContextEngineeringService,
    ) -> None:
        self.uow = uow
        self._execution_machine = execution_machine
        self._file_sync_service = file_sync_service
        self._context_service = context_service

    async def execute_latest_plan(
        self, session_id: UUID, *, resume: bool = False
    ) -> list[SessionEvent]:
        return [
            item
            async for item in self.stream_latest_plan(session_id, resume=resume)
            if isinstance(item, SessionEvent)
        ]

    async def stream_latest_plan(
        self, session_id: UUID, *, resume: bool = False
    ) -> AsyncIterator[SessionEvent | tuple[str, str]]:
        plan, context = await self._prepare_execution(session_id)
        identity = ExecutionRunIdentity(
            uuid4(),
            self._plan_id(plan),
            plan_revision(plan),
        )
        start_step_index = 0
        step_history: tuple[str, ...] = ()
        if resume:
            start_step_index, step_history = await self._resume_context(session_id, plan)
        await self.uow.sessions.update_status(session_id, SessionStatus.running.value)
        await self.uow.commit()
        try:
            async for item in self._execution_machine.stream(
                session_id,
                plan,
                context,
                run_id=identity.run_id,
                start_step_index=start_step_index,
                step_history=step_history,
            ):
                if isinstance(item, SessionEvent):
                    identity = self._event_identity(identity, item)
                    await self._commit_event(item)
                yield item
        except Exception as error:
            error_event = await self._persist_error(session_id, error, identity)
            yield error_event

    async def _prepare_execution(
        self, session_id: UUID
    ) -> tuple[dict[str, object], AgentExecutionContext]:
        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )
        events = await self.uow.session_events.list_by_session(session_id)
        plan = dict(self._find_latest_plan_event(events).payload)
        steps = plan.get("steps")
        if not isinstance(steps, (list, tuple)) or not steps:
            raise AppException(
                message="plan has no steps",
                code=400,
                status_code=400,
            )
        snapshot = await self._context_service.build_snapshot(
            session_id,
            task=str(plan.get("goal", "")),
        )
        await self._file_sync_service.sync(session_id)
        return plan, AgentExecutionContext(
            snapshot.memory_context,
            self._context_service.render_for_agent(snapshot),
            workspace_dir=getattr(session, "workspace_dir", ""),
            full_access=getattr(session, "full_access", False),
        )

    async def _resume_context(
        self, session_id: UUID, plan: dict[str, object]
    ) -> tuple[int, tuple[str, ...]]:
        """从事件里定位上次失败 run 已完成的步骤，返回断点与步骤历史。"""

        del plan
        events = await self.uow.session_events.list_by_session(session_id)
        last_run_id: str | None = None
        for event in reversed(events):
            run_id = event.payload.get("run_id")
            if event.type is SessionEventType.task_error and run_id:
                last_run_id = str(run_id)
                break
        if last_run_id is None:
            return 0, ()
        completed = [
            event
            for event in events
            if event.type is SessionEventType.step_completed
            and str(event.payload.get("run_id")) == last_run_id
        ]
        step_history = tuple(
            f"- 步骤{int(event.payload.get('index') or 0)}"
            f"《{event.payload.get('title') or ''}》已完成："
            f"{self._trim_history(str(event.payload.get('summary') or ''), 200)}"
            for event in completed
        )
        return len(completed), step_history

    @staticmethod
    def _trim_history(value: str, limit: int) -> str:
        clean = " ".join(value.split())
        if len(clean) <= limit:
            return clean
        return f"{clean[:limit]}..."

    async def _commit_event(self, event: SessionEvent) -> None:
        status = None
        if event.type in {
            SessionEventType.task_done,
            SessionEventType.step_blocked,
        } or (
            event.type is SessionEventType.message_created
            and event.payload.get("role") == MessageRole.assistant.value
        ):
            status = SessionStatus.idle
        elif event.type in {
            SessionEventType.step_failed,
            SessionEventType.task_error,
        } or (
            event.type is SessionEventType.step_reflected
            and event.payload.get("action") == ReflectionAction.fail.value
        ):
            status = SessionStatus.failed
        if status is not None:
            await self.uow.sessions.update_status(event.session_id, status.value)
        await self.uow.sessions.touch(event.session_id)
        await self.uow.commit()

    async def _persist_error(
        self,
        session_id: UUID,
        error: Exception,
        identity: ExecutionRunIdentity,
    ) -> SessionEvent:
        payload = build_task_error_payload(
            error,
            session_id=session_id,
            plan_id=identity.plan_id,
        )
        payload["run_id"] = str(identity.run_id)
        payload["plan_revision"] = identity.plan_revision
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.task_error,
            payload=payload,
        )
        await self.uow.sessions.update_status(session_id, SessionStatus.failed.value)
        await self.uow.commit()
        return event

    @classmethod
    def _event_identity(
        cls,
        current: ExecutionRunIdentity,
        event: SessionEvent,
    ) -> ExecutionRunIdentity:
        if "run_id" not in event.payload:
            return current
        event_run_id = cls._run_id(event.payload["run_id"])
        if event_run_id != current.run_id:
            raise AppException(message="execution event run_id does not match current run")
        if "plan_revision" not in event.payload:
            raise AppException(message="execution event is missing plan_revision")
        return ExecutionRunIdentity(
            event_run_id,
            cls._plan_id(event.payload),
            plan_revision(event.payload),
        )

    @staticmethod
    def _run_id(value: object) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as error:
            raise AppException(message="execution event run_id is invalid") from error

    @staticmethod
    def _plan_id(payload: dict[str, object]) -> str:
        value = payload.get("plan_id") or payload.get("id")
        if value is None:
            raise AppException(message="execution plan_id is missing")
        return str(value)

    @staticmethod
    def _find_latest_plan_event(events: list[SessionEvent]) -> SessionEvent:
        for event in reversed(events):
            if event.type is SessionEventType.plan_created:
                return event
        raise AppException(
            message="plan not found",
            code=404,
            status_code=404,
        )
