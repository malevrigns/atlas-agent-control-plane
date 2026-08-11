import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.application.agent_summary_service import (
    AgentSummaryRequest,
    AgentSummaryResult,
    AgentSummaryService,
)
from app.core.exceptions import AppException
from app.domain.context_engineering.entities import MemoryContext
from app.domain.sessions.entities import SessionEvent, SessionEventType


def build_tool_event(
    step_id: str,
    tool_name: str,
    output: str,
    arguments: dict | None = None,
    *,
    attempt: int = 2,
    plan_revision: int = 0,
    run_id: str = "run-1",
) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=uuid4(),
        type=SessionEventType.tool_called,
        payload={
            "plan_id": "plan-1",
            "plan_revision": plan_revision,
            "run_id": run_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "output": output,
            "status": "succeeded",
            "attempt": attempt,
        },
        created_at=datetime.now(UTC),
    )


class FakeMessages:
    async def add_assistant_message(self, *, session_id, content):
        return SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="assistant"), content=content)


class FakeEvents:
    async def add(self, *, session_id, event_type, payload):
        return SessionEvent(uuid4(), session_id, event_type, payload, datetime.now(UTC))


class FakeUow:
    def __init__(self) -> None:
        self.session_messages = FakeMessages()
        self.session_events = FakeEvents()


class FakeModel:
    def __init__(self, deltas=None, error: Exception | None = None) -> None:
        self.deltas = deltas or []
        self.error = error

    async def chat_stream(self, *args, **kwargs):
        if self.error:
            raise self.error
        for kind, text in self.deltas:
            yield SimpleNamespace(kind=kind, text=text)


def summary_request(events: list[SessionEvent]) -> AgentSummaryRequest:
    return AgentSummaryRequest(
        session_id=uuid4(),
        plan={"id": "plan-1", "goal": "整理 AI 新闻并生成报告", "steps": []},
        events=tuple(accept_tool_events(events)),
        memory_context=MemoryContext("", [], 0, 0, 0, 0),
    )


def build_reflection_event(
    step_id: str,
    attempt: int,
    action: str = "accept",
    *,
    plan_revision: int = 0,
    run_id: str = "run-1",
) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=uuid4(),
        type=SessionEventType.step_reflected,
        payload={
            "plan_id": "plan-1",
            "plan_revision": plan_revision,
            "run_id": run_id,
            "step_id": step_id,
            "attempt": attempt,
            "action": action,
        },
        created_at=datetime.now(UTC),
    )


def accept_tool_events(events: list[SessionEvent]) -> list[SessionEvent]:
    accepted = []
    for event in events:
        accepted.extend(
            [
                event,
                build_reflection_event(
                    str(event.payload["step_id"]),
                    int(event.payload["attempt"]),
                    plan_revision=int(event.payload["plan_revision"]),
                    run_id=str(event.payload["run_id"]),
                ),
            ]
        )
    return accepted


class FinalAnswerBuilderTest(unittest.IsolatedAsyncioTestCase):
    # ===================== 第1步：最终回答应从工具输出中整理证据 =====================
    async def test_evidence_contains_sources_files_and_artifacts(self) -> None:
        service = AgentSummaryService(FakeUow(), FakeModel())
        plan = {
            "goal": "整理 AI 新闻并生成报告",
            "steps": [
                {"id": "search", "title": "搜索新闻资料"},
                {"id": "file", "title": "读取上传文件"},
                {"id": "shell", "title": "生成报告文件"},
            ],
        }
        search_output = json.dumps(
            {
                "kind": "search_results",
                "query": "AI news",
                "items": [
                    {
                        "title": "OpenAI releases agent update",
                        "url": "https://example.com/openai",
                        "snippet": "Agent update details.",
                    },
                    {
                        "title": "Microsoft announces AI tools",
                        "url": "https://example.com/microsoft",
                        "snippet": "AI tools details.",
                    },
                ],
            },
            ensure_ascii=False,
        )
        events = accept_tool_events([
            build_tool_event("search", "search_web", search_output, {"query": "AI news"}),
            build_tool_event(
                "file",
                "file_read",
                "文件：requirements.md\n第 3 行：需要输出引用来源和最终建议。",
            ),
            build_tool_event(
                "shell",
                "shell_exec",
                "命令：python build_report.py\n退出码：0\n输出文件：/workspace/report.md",
            ),
        ])

        evidence = service.build_evidence(plan, events)

        self.assertIn("OpenAI releases agent update", evidence)
        self.assertIn("https://example.com/openai", evidence)
        self.assertIn("requirements.md", evidence)
        self.assertIn("/workspace/report.md", evidence)
        self.assertIn("状态：succeeded", evidence)
        self.assertIn("尝试：2", evidence)

    async def test_stream_preserves_deltas_and_returns_persisted_result(self) -> None:
        event = build_tool_event("step", "shell_exec", "命令：pwd\n退出码：0")
        service = AgentSummaryService(
            FakeUow(),
            FakeModel([("reasoning", "think"), ("content", "final answer")]),
        )

        items = [item async for item in service.stream(summary_request([event]))]

        self.assertEqual(items[0], ("thinking_delta", "think"))
        self.assertEqual(items[1], ("answer_delta", "final answer"))
        self.assertIsInstance(items[2], AgentSummaryResult)
        self.assertEqual(items[2].final_answer, "final answer")

    async def test_stream_surfaces_model_errors_without_fallback(self) -> None:
        event = build_tool_event("step", "shell_exec", "命令：pwd\n退出码：0")
        service = AgentSummaryService(
            FakeUow(), FakeModel(error=AppException(message="provider failed"))
        )

        with self.assertRaisesRegex(AppException, "provider failed"):
            _ = [item async for item in service.stream(summary_request([event]))]

    async def test_stream_rejects_empty_model_output(self) -> None:
        event = build_tool_event("step", "shell_exec", "命令：pwd\n退出码：0")
        service = AgentSummaryService(FakeUow(), FakeModel([]))

        with self.assertRaisesRegex(AppException, "empty final answer"):
            _ = [item async for item in service.stream(summary_request([event]))]

    async def test_stream_rejects_non_string_delta_text(self) -> None:
        event = build_tool_event("step", "shell_exec", "命令：pwd\n退出码：0")
        service = AgentSummaryService(FakeUow(), FakeModel([("content", None)]))

        with self.assertRaisesRegex(AppException, "text must be a string"):
            _ = [item async for item in service.stream(summary_request([event]))]


if __name__ == "__main__":
    unittest.main()
