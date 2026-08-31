from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.agent_runner_service import AgentRunnerService
from app.application.context_engineering_service import ContextEngineeringService
from app.application.file_service import FileService
from app.application.llm_service import LLMService
from app.application.planner_service import PlannerService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.domain.tasks.queue import AgentTaskQueue
from app.infrastructure.database.session import get_db_session


def build_session_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> SessionService:
    return SessionService(UnitOfWork(db_session))


def build_file_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> FileService:
    return FileService(UnitOfWork(db_session))


def build_context_engineering_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> ContextEngineeringService:
    return ContextEngineeringService(UnitOfWork(db_session))


def build_planner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> PlannerService:
    return PlannerService(UnitOfWork(db_session), LLMService())


def build_agent_runner_service(
    db_session: AsyncSession = Depends(get_db_session),
) -> AgentRunnerService:
    return AgentRunnerService.from_uow(UnitOfWork(db_session))


def get_task_queue(request: Request) -> AgentTaskQueue:
    return request.app.state.task_queue
