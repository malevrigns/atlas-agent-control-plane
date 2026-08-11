import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from uuid import uuid4

from app.application.react_step_executor import (
    ReActStepExecutor,
    SelectedToolCaller,
    StepExecutionRequest,
)
from app.application.tool_runtime import ToolExecutionContext
from app.domain.agent_core.tools import ToolCallResult, ToolInvocationStatus
from tests.test_agent_execution_machine import FakeEventSink, empty_memory_context, plan_payload


class StepAttemptIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_attempt_changes_tool_runtime_idempotency_key(self) -> None:
        contexts = []

        async def call_tool(**kwargs) -> Mapping[str, object]:
            contexts.append(kwargs["execution_context"])
            return {
                "tool_name": "stub",
                "arguments": {},
                "output": "ok",
                "status": ToolInvocationStatus.succeeded.value,
            }

        executor = ReActStepExecutor(
            uow=SimpleNamespace(session_events=FakeEventSink([])),
            tool_caller=call_tool,
        )
        plan = plan_payload(1)
        common = {
            "session_id": uuid4(),
            "run_id": uuid4(),
            "plan_revision": 0,
            "plan": plan,
            "step": plan["steps"][0],
            "step_index": 0,
            "memory_context": empty_memory_context(),
            "agent_context": "",
            "step_history": (),
        }

        await executor.execute(StepExecutionRequest(**common, attempt=1))
        await executor.execute(StepExecutionRequest(**common, attempt=2))

        self.assertNotEqual(contexts[0].idempotency_key, contexts[1].idempotency_key)
        self.assertTrue(contexts[1].idempotency_key.endswith(":attempt:2"))

    async def test_selected_tool_caller_adapts_request_to_selector(self) -> None:
        class Selector:
            def __init__(self) -> None:
                self.kwargs = None

            async def call_tool_for_step(self, **kwargs):
                self.kwargs = kwargs
                return ToolCallResult("stub", {}, "ok")

        selector = Selector()
        caller = SelectedToolCaller(selector)
        plan = plan_payload(1)
        request = StepExecutionRequest(
            session_id=uuid4(),
            run_id=uuid4(),
            plan_revision=0,
            plan=plan,
            step=plan["steps"][0],
            step_index=0,
            attempt=1,
            memory_context=empty_memory_context(),
            agent_context="",
            step_history=(),
        )
        context = ToolExecutionContext(
            project_id="default",
            session_id=request.session_id,
            actor="react_agent",
            allowed_permissions=set(),
            idempotency_key="key",
        )

        result = await caller(
            request=request,
            agent_context="context",
            execution_context=context,
        )

        self.assertEqual(selector.kwargs["index"], 1)
        self.assertEqual(selector.kwargs["execution_context"], context)
        self.assertEqual(result["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
