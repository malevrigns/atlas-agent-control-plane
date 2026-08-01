from dataclasses import dataclass
from uuid import UUID

from app.application.planner_service import PlannerService
from app.application.react_agent_service import ReActAgentService
from app.application.session_service import SessionService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import build_task_error_payload
from app.domain.sessions.entities import (
    Session,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)


@dataclass(slots=True)
class AgentRunnerStreamItem:
    """Agent Runner 推给 HTTP/SSE 层的一条可观察输出。

    `name` 对应 SSE event 名称；`payload` 保留领域对象或简单字典。
    路由层负责把领域对象转换成 Pydantic 响应模型，避免应用服务依赖 HTTP 细节。
    """

    name: str
    payload: Session | SessionEvent | dict


class AgentRunnerService:
    """统一编排一次会话任务的主执行链路。

    第 42 章把前面分散在路由里的步骤收敛到这里：
    1. 标记会话运行中。
    2. 写入用户消息和 message_created 事件。
    3. 使用 Planner 生成 plan_created。
    4. 使用 ReAct 按步骤执行并持续产出事件。
    5. 读取最终会话状态并发出 stream_done。
    """

    def __init__(
        self,
        *,
        session_service: SessionService,
        planner_service: PlannerService,
        react_service: ReActAgentService,
    ) -> None:
        # ===================== 第1步：保存 Runner 需要协调的三个应用服务 =====================
        self.session_service = session_service
        self.planner_service = planner_service
        self.react_service = react_service

    @classmethod
    def from_uow(
        cls,
        uow: UnitOfWork,
        *,
        planner_service: PlannerService | None = None,
    ) -> "AgentRunnerService":
        """用同一个 UnitOfWork 构建 Runner，保证执行链路使用同一事务入口。"""

        return cls(
            session_service=SessionService(uow),
            planner_service=planner_service or PlannerService(uow),
            react_service=ReActAgentService(uow),
        )

    # ===================== 第2步：运行一次用户消息驱动的 Agent 任务 =====================
    async def stream_user_message(
        self,
        *,
        session_id: UUID,
        content: str,
    ):
        """把用户消息转换成可流式观察的 Agent 执行过程。"""

        # 1. 会话先进入 running，前端可以立即展示任务开始。
        running_session = await self.session_service.mark_running(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=running_session,
        )

        message = None
        try:
            # 2. 写入用户消息，并把 message_created 推给前端时间线。
            message, message_event = await self.session_service.create_user_message(
                session_id=session_id,
                content=content,
            )
            yield AgentRunnerStreamItem(
                name=message_event.type.value,
                payload=message_event,
            )

            # 3. 生成计划。Planner 内部会读取上下文快照和长期记忆。
            _plan, plan_event = await self.planner_service.create_plan(
                session_id=session_id,
                task=content,
            )
            yield AgentRunnerStreamItem(
                name=plan_event.type.value,
                payload=plan_event,
            )

            # 4. 执行计划。ReAct 内部会持续写 step/tool/task 事件。
            async for event in self.react_service.stream_latest_plan(session_id):
                yield AgentRunnerStreamItem(
                    name=event.type.value,
                    payload=event,
                )
        except Exception as error:
            # 5. Planner 或 ReAct 任一阶段失败，都写入统一 task_error。
            #    这样前端 SSE 不会只看到连接断开，而是能看到错误原因和建议。
            error_event = await self.session_service.uow.session_events.add(
                session_id=session_id,
                event_type=SessionEventType.task_error,
                payload=build_task_error_payload(
                    error,
                    session_id=session_id,
                    plan_id=None,
                    task_id=None,
                ),
            )
            await self.session_service.uow.sessions.update_status(
                session_id=session_id,
                status=SessionStatus.failed.value,
            )
            await self.session_service.uow.commit()
            yield AgentRunnerStreamItem(
                name=error_event.type.value,
                payload=error_event,
            )

        # 6. 推送最终会话状态和 stream_done，前端据此收尾 loading 状态。
        final_session = await self.session_service.get_session(session_id)
        yield AgentRunnerStreamItem(
            name="session_status",
            payload=final_session,
        )
        yield AgentRunnerStreamItem(
            name="stream_done",
            payload={
                "session_id": str(session_id),
                "message_id": str(message.id) if message else None,
                "message": {
                    "id": str(message.id),
                    "session_id": str(message.session_id),
                    "role": message.role.value,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                if message
                else None,
            },
        )

    # ===================== 第3步：运行已有计划，供同步接口和后台任务复用 =====================
    async def execute_latest_plan(self, session_id: UUID) -> list[SessionEvent]:
        """执行会话最近一次计划，保持旧接口兼容。"""

        return await self.react_service.execute_latest_plan(session_id)
