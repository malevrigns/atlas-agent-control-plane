from collections.abc import AsyncIterator
from uuid import UUID

from app.application.agent_execution_machine import (
    AgentExecutionContext,
    AgentExecutionMachine,
)
from app.application.context_engineering_service import ContextEngineeringService
from app.application.session_file_sync_service import SessionFileSyncService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException, build_task_error_payload
from app.domain.sessions.entities import SessionEvent, SessionEventType, SessionStatus


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

    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        return [
            item
            async for item in self.stream_latest_plan(session_id)
            if isinstance(item, SessionEvent)
        ]

    async def stream_latest_plan(
        self, session_id: UUID
    ) -> AsyncIterator[SessionEvent | tuple[str, str]]:
        plan, context = await self._prepare_execution(session_id)
        await self.uow.sessions.update_status(session_id, SessionStatus.running.value)
        await self.uow.commit()
        try:
            async for item in self._execution_machine.stream(
                session_id,
                plan,
                context,
            ):
                if isinstance(item, SessionEvent):
                    await self._commit_event(item)
                yield item
        except Exception as error:
            error_event = await self._persist_error(session_id, plan, error)
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
        )

    async def _commit_event(self, event: SessionEvent) -> None:
        status = None
        if event.type in {SessionEventType.task_done, SessionEventType.step_blocked}:
            status = SessionStatus.idle
        elif event.type in {
            SessionEventType.step_failed,
            SessionEventType.task_error,
        }:
            status = SessionStatus.failed
        if status is not None:
            await self.uow.sessions.update_status(event.session_id, status.value)
        await self.uow.sessions.touch(event.session_id)
        await self.uow.commit()

    async def _persist_error(
        self,
        session_id: UUID,
        plan: dict[str, object],
        error: Exception,
    ) -> SessionEvent:
        plan_id = plan.get("id") or plan.get("plan_id")
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.task_error,
            payload=build_task_error_payload(
                error,
                session_id=session_id,
                plan_id=str(plan_id) if plan_id is not None else None,
            ),
        )
        await self.uow.sessions.update_status(session_id, SessionStatus.failed.value)
        await self.uow.commit()
        return event

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
