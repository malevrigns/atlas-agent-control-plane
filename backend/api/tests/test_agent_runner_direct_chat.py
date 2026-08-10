import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.agent_runner_service import (
    AgentRunnerService,
    needs_agent_pipeline,
)
from app.core.exceptions import AppException
from app.domain.llm.entities import LLMStreamDelta
from app.domain.context_engineering.entities import (
    ContextBudget,
    ContextMessage,
    MemoryContext,
    SessionContextSnapshot,
)
from app.domain.sessions.entities import (
    MessageRole,
    Session,
    SessionEvent,
    SessionEventType,
    SessionMessage,
    SessionStatus,
)


def build_session(status: SessionStatus = SessionStatus.idle) -> Session:
    now = datetime.now(UTC)
    return Session(
        id=uuid4(),
        title="直连问答测试会话",
        status=status,
        unread_count=0,
        created_at=now,
        updated_at=now,
    )


def build_message(
    session_id: UUID,
    content: str,
    role: MessageRole = MessageRole.user,
) -> SessionMessage:
    return SessionMessage(
        id=uuid4(),
        session_id=session_id,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def build_event(
    session_id: UUID,
    event_type: SessionEventType,
    payload: dict,
) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=session_id,
        type=event_type,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def build_snapshot(session_id: UUID, question: str) -> SessionContextSnapshot:
    return SessionContextSnapshot(
        session_id=session_id,
        summary="",
        messages=[
            ContextMessage(
                role="user",
                content=question,
                original_chars=len(question),
                truncated=False,
                created_at=datetime.now(UTC),
            ),
        ],
        event_summaries=[],
        files=[],
        memory_context=MemoryContext(
            query=question,
            items=[],
            candidate_count=0,
            omitted_count=0,
            total_chars=0,
            max_chars=2400,
        ),
        budget=ContextBudget(
            message_limit=8,
            event_limit=20,
            max_message_chars=1200,
            included_messages=1,
            omitted_messages=0,
            included_events=0,
            omitted_events=0,
            total_message_chars=len(question),
            memory_limit=6,
            max_memory_chars=2400,
            included_memories=0,
            omitted_memories=0,
            total_memory_chars=0,
        ),
    )


class FakeSessionEventRepo:
    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        self.events: list[SessionEvent] = []

    async def add(
        self,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        event = build_event(session_id, event_type, payload)
        self.events.append(event)
        return event


class FakeSessionRepo:
    def __init__(self) -> None:
        self.status_updates: list[str] = []
        self.current_status: SessionStatus = SessionStatus.idle

    async def get(self, session_id: UUID) -> Session:
        session = build_session(self.current_status)
        session.id = session_id
        return session

    async def update_status(self, session_id: UUID, status: str) -> None:
        self.status_updates.append(status)
        self.current_status = SessionStatus(status)

    async def touch(self, session_id: UUID) -> None:
        return None


class FakeSessionFileRepo:
    async def list_by_session(self, session_id: UUID) -> list:
        return []


@dataclass(slots=True)
class FakeUow:
    session_events: FakeSessionEventRepo
    sessions: FakeSessionRepo
    session_files: FakeSessionFileRepo = field(default_factory=FakeSessionFileRepo)
    commits: int = 0

    async def commit(self) -> None:
        self.commits += 1


@dataclass(slots=True)
class FakeSessionService:
    session: Session
    uow: FakeUow
    assistant_messages: list[str] = field(default_factory=list)

    async def mark_running(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.running
        return self.session

    async def create_user_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        message = build_message(session_id, content)
        event = build_event(
            session_id,
            SessionEventType.message_created,
            {
                "message_id": str(message.id),
                "role": message.role.value,
                "content": content,
            },
        )
        return message, event

    async def create_assistant_message(
        self,
        session_id: UUID,
        content: str,
    ) -> tuple[SessionMessage, SessionEvent]:
        self.assistant_messages.append(content)
        message = build_message(session_id, content, role=MessageRole.assistant)
        event = build_event(
            session_id,
            SessionEventType.message_created,
            {
                "message_id": str(message.id),
                "role": message.role.value,
                "content": content,
            },
        )
        return message, event

    async def get_session(self, session_id: UUID) -> Session:
        self.session.status = SessionStatus.idle
        return self.session


class FakeContextService:
    def __init__(self, question: str) -> None:
        self.question = question

    async def build_snapshot(self, session_id: UUID, task: str | None = None):
        return build_snapshot(session_id, self.question)


class FakeLLMService:
    """支持逐次配置行为的流式模型替身。

    behaviors 是每次 chat_stream 调用的剧本：AppException 表示这次调用
    直接失败，列表则是要产出的增量序列。默认所有调用共享第一个剧本。
    """

    def __init__(
        self,
        deltas: list[LLMStreamDelta] | None = None,
        error: AppException | None = None,
        behaviors: list | None = None,
        thinking: bool = False,
    ) -> None:
        if behaviors is None:
            behaviors = [error if error is not None else (deltas or [])]
        self.behaviors = behaviors
        self.calls: list[dict] = []
        self.received_messages = None
        self.thinking = thinking

    def thinking_enabled(self) -> bool:
        return self.thinking

    async def chat_stream(self, messages, thinking=None, **kwargs):
        self.received_messages = messages
        self.calls.append({"thinking": thinking})
        behavior = self.behaviors[min(len(self.calls) - 1, len(self.behaviors) - 1)]
        if isinstance(behavior, AppException):
            raise behavior
        for delta in behavior:
            yield delta


def content_deltas(*texts: str) -> list[LLMStreamDelta]:
    return [LLMStreamDelta(kind="content", text=text) for text in texts]


class UnusedPlannerService:
    async def create_plan(self, session_id: UUID, task: str):
        raise AssertionError("普通问答不应触发 Planner")

    async def stream_plan(self, session_id: UUID, task: str):
        raise AssertionError("普通问答不应触发 Planner")
        yield  # pragma: no cover


class UnusedReactService:
    async def stream_latest_plan(self, session_id: UUID):
        raise AssertionError("普通问答不应触发 ReAct")
        yield  # pragma: no cover


class NeedsAgentPipelineTest(unittest.TestCase):
    def test_plain_questions_go_direct(self) -> None:
        for content in (
            "你好",
            "Python 的 GIL 是什么？",
            "帮我解释一下这段报错的含义",
            "什么是控制反转",
            # 编程问答里的“查找/写/验证”不该误触流水线——
            # 这类问题应该像 GPT 一样直接流式回答。
            "帮我写一个二分查找函数，并验证空数组等边界情况",
            "怎么读取列表的最后一个元素",
            "如何保存 Python 字典到变量里",
        ):
            self.assertFalse(needs_agent_pipeline(content), content)

    def test_tool_intents_go_pipeline(self) -> None:
        for content in (
            "搜索最近的 FastAPI 版本变化",
            "打开 https://example.com 并截图",
            "把结果写入文件 report.md",
            "执行 pytest 并总结失败原因",
            "请执行一个测试任务",
            "在沙箱里运行这个脚本",
            "把统计结果保存到 result.txt",
        ):
            self.assertTrue(needs_agent_pipeline(content), content)


class DirectChatStreamTest(unittest.IsolatedAsyncioTestCase):
    def build_runner(self, question: str, llm: FakeLLMService):
        session = build_session()
        uow = FakeUow(
            session_events=FakeSessionEventRepo(session.id),
            sessions=FakeSessionRepo(),
        )
        session_service = FakeSessionService(session=session, uow=uow)
        runner = AgentRunnerService(
            session_service=session_service,  # type: ignore[arg-type]
            planner_service=UnusedPlannerService(),  # type: ignore[arg-type]
            react_service=UnusedReactService(),  # type: ignore[arg-type]
            llm_service=llm,  # type: ignore[arg-type]
            context_service=FakeContextService(question),  # type: ignore[arg-type]
        )
        return runner, session, session_service, uow

    async def test_direct_answer_injects_invoked_skills(self) -> None:
        """/ 显式调用的技能指引必须进入 system 上下文。"""

        question = "什么是幂等接口？"
        llm = FakeLLMService(deltas=content_deltas("幂等接口重复调用结果一致。"))
        runner, session, _session_service, _uow = self.build_runner(question, llm)

        async def fake_skills(skill_ids):
            self.assertEqual([str(item) for item in skill_ids], ["skill-1"])
            return [("回答签名 v1.0.0", "回答末尾必须追加固定署名行。")]

        runner._load_invoked_skills = fake_skills

        async for _item in runner.stream_user_message(
            session_id=session.id,
            content=question,
            skill_ids=["skill-1"],
        ):
            pass

        system_text = llm.received_messages[0].content
        self.assertIn("显式调用了以下技能", system_text)
        self.assertIn("回答签名 v1.0.0", system_text)
        self.assertIn("回答末尾必须追加固定署名行。", system_text)

    async def test_direct_answer_streams_and_persists_assistant_message(self) -> None:
        question = "Python 的 GIL 是什么？"
        llm = FakeLLMService(deltas=content_deltas("GIL 是全局", "解释器锁。"))
        runner, session, session_service, uow = self.build_runner(question, llm)

        items = [
            item
            async for item in runner.stream_user_message(
                session_id=session.id,
                content=question,
            )
        ]

        names = [item.name for item in items]
        self.assertEqual(
            names,
            [
                "session_status",
                "message_created",
                "answer_started",
                "answer_delta",
                "answer_delta",
                "message_created",
                "task_done",
                "session_status",
                "stream_done",
            ],
        )
        # 助手消息完整落库。
        self.assertEqual(session_service.assistant_messages, ["GIL 是全局解释器锁。"])
        # task_done 事件带上完整回答，供事件时间线还原。
        done_events = [
            event
            for event in uow.session_events.events
            if event.type is SessionEventType.task_done
        ]
        self.assertEqual(len(done_events), 1)
        self.assertEqual(done_events[0].payload["final_answer"], "GIL 是全局解释器锁。")
        self.assertEqual(done_events[0].payload["mode"], "chat")
        # 会话最终回到 idle。
        self.assertIn(SessionStatus.idle.value, uow.sessions.status_updates)
        # 发给模型的消息包含 system 提示和用户问题。
        assert llm.received_messages is not None
        self.assertEqual(llm.received_messages[0].role, "system")
        self.assertEqual(llm.received_messages[-1].role, "user")
        self.assertEqual(llm.received_messages[-1].content, question)

    async def test_llm_not_configured_returns_guidance_instead_of_error(self) -> None:
        question = "你好"
        llm = FakeLLMService(
            error=AppException(
                message="LLM api key is not configured: LLM_API_KEY",
                code=500,
                status_code=500,
            )
        )
        runner, session, session_service, uow = self.build_runner(question, llm)

        items = [
            item
            async for item in runner.stream_user_message(
                session_id=session.id,
                content=question,
            )
        ]

        names = [item.name for item in items]
        self.assertNotIn("task_error", names)
        self.assertIn("answer_delta", names)
        self.assertEqual(len(session_service.assistant_messages), 1)
        self.assertIn("LLM_API_KEY", session_service.assistant_messages[0])

    async def test_thinking_deltas_stream_and_land_in_task_done(self) -> None:
        question = "为什么天空是蓝色的？"
        llm = FakeLLMService(
            deltas=[
                LLMStreamDelta(kind="reasoning", text="先想想瑞利散射"),
                LLMStreamDelta(kind="reasoning", text="，波长越短散射越强。"),
                LLMStreamDelta(kind="content", text="因为瑞利散射。"),
            ],
            thinking=True,
        )
        runner, session, session_service, uow = self.build_runner(question, llm)

        items = [
            item
            async for item in runner.stream_user_message(
                session_id=session.id,
                content=question,
            )
        ]

        names = [item.name for item in items]
        self.assertEqual(names.count("thinking_delta"), 2)
        # 思考增量必须在正文增量之前。
        self.assertLess(names.index("thinking_delta"), names.index("answer_delta"))
        done_events = [
            event
            for event in uow.session_events.events
            if event.type is SessionEventType.task_done
        ]
        self.assertEqual(
            done_events[0].payload["reasoning"], "先想想瑞利散射，波长越短散射越强。"
        )
        # task_done 关联了 assistant 消息 id，刷新后客户端可以据此展示推理过程。
        self.assertTrue(done_events[0].payload["message_id"])
        # 思考内容不进入正式回答消息。
        self.assertEqual(session_service.assistant_messages, ["因为瑞利散射。"])

    async def test_provider_rejecting_thinking_falls_back_to_plain_stream(self) -> None:
        question = "你好"
        llm = FakeLLMService(
            behaviors=[
                AppException(message="enable_thinking is not supported", code=502, status_code=502),
                content_deltas("你好，", "有什么可以帮你？"),
            ],
            thinking=True,
        )
        runner, session, session_service, uow = self.build_runner(question, llm)

        items = [
            item
            async for item in runner.stream_user_message(
                session_id=session.id,
                content=question,
            )
        ]

        names = [item.name for item in items]
        self.assertNotIn("task_error", names)
        self.assertEqual(session_service.assistant_messages, ["你好，有什么可以帮你？"])
        # 第一次按配置请求思考，第二次显式关闭后成功。
        self.assertEqual(llm.calls, [{"thinking": None}, {"thinking": False}])


if __name__ == "__main__":
    unittest.main()
