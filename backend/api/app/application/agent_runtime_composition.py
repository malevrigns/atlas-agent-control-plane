from dataclasses import dataclass

from app.application.agent_direct_chat_service import AgentDirectChatService
from app.application.agent_execution_machine import AgentExecutionMachine
from app.application.agent_summary_service import AgentSummaryService
from app.application.context_engineering_service import ContextEngineeringService
from app.application.critic_service import CriticService
from app.application.llm_service import LLMService
from app.application.planner_service import PlannerService
from app.application.react_agent_service import ReActAgentService
from app.application.react_step_executor import ReActStepExecutor, SelectedToolCaller
from app.application.session_file_sync_service import SessionFileSyncService
from app.application.session_service import SessionService
from app.application.tool_selection_service import ModelToolSelectionService
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.domain.agent_runtime.router import AgentStateRouter
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry
from app.infrastructure.sandbox.file_client import SandboxFileClient
from app.infrastructure.storage.factory import build_file_storage


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    model: LLMService
    session_service: SessionService
    planner_service: PlannerService
    react_service: ReActAgentService
    direct_chat_service: AgentDirectChatService


def compose_agent_runtime(
    uow: UnitOfWork,
    *,
    llm_service: LLMService | None = None,
    planner_service: PlannerService | None = None,
) -> AgentRuntime:
    model = llm_service or LLMService()
    session_service = SessionService(uow)
    context_service = ContextEngineeringService(uow)
    summary = AgentSummaryService(uow, model)
    selector = ModelToolSelectionService(
        registry=build_builtin_tool_registry(),
        llm_service=model,
        uow=uow,
    )
    executor = ReActStepExecutor(
        uow=uow,
        tool_caller=SelectedToolCaller(selector),
        output_summarizer=summary.summarize_tool_output,
    )
    machine = AgentExecutionMachine(
        executor=executor,
        critic=CriticService(model),
        summarizer=summary,
        event_sink=uow.session_events,
        router=AgentStateRouter(),
    )
    react_service = ReActAgentService(
        uow,
        execution_machine=machine,
        file_sync_service=_build_file_sync(uow),
        context_service=context_service,
    )
    direct_chat = AgentDirectChatService(session_service, model, context_service)
    return AgentRuntime(
        model=model,
        session_service=session_service,
        planner_service=planner_service or PlannerService(uow, llm_service=model),
        react_service=react_service,
        direct_chat_service=direct_chat,
    )


def _build_file_sync(uow: UnitOfWork) -> SessionFileSyncService:
    return SessionFileSyncService(
        uow,
        storage=build_file_storage(),
        sandbox_files=SandboxFileClient(
            base_url=settings.sandbox_api_base_url,
            timeout_seconds=settings.sandbox_api_timeout_seconds,
        ),
        max_file_size=settings.max_file_preview_size,
    )
