import unittest
from uuid import uuid4

from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import (
    AgentPhase,
    AgentRunState,
    Reflection,
    ReflectionAction,
    StepObservation,
)
from app.domain.agent_runtime.router import AgentStateRouter


def plan_payload() -> dict[str, object]:
    return {
        "goal": "inspect the repository",
        "steps": (
            {"tool_name": "search", "arguments": {"query": "agent"}},
            {"tool_name": "summarize", "arguments": {"format": "brief"}},
        ),
    }


def observation(status: ToolInvocationStatus) -> StepObservation:
    return StepObservation(status=status, output="tool result")


class AgentStateRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = AgentStateRouter()
        self.state = AgentRunState.from_plan(uuid4(), plan_payload())

    def test_accept_advances_to_next_executing_step(self) -> None:
        reflecting = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.succeeded)
        )

        next_step = self.router.after_reflection(
            reflecting,
            Reflection(action=ReflectionAction.accept, reason="evidence matches"),
        )

        self.assertEqual(reflecting.phase, AgentPhase.reflecting)
        self.assertEqual(next_step.step_index, 1)
        self.assertEqual(next_step.phase, AgentPhase.executing)

    def test_last_step_accept_transitions_to_summarizing(self) -> None:
        second_step = AgentRunState.from_plan(uuid4(), plan_payload())
        second_step = self.router.after_reflection(
            self.router.after_execution(second_step, observation(ToolInvocationStatus.succeeded)),
            Reflection(action=ReflectionAction.accept, reason="continue"),
        )
        reflecting = self.router.after_execution(
            second_step, observation(ToolInvocationStatus.succeeded)
        )

        result = self.router.after_reflection(
            reflecting, Reflection(action=ReflectionAction.accept, reason="complete")
        )

        self.assertEqual(result.phase, AgentPhase.summarizing)
        self.assertEqual(result.step_index, 1)

    def test_retry_keeps_step_and_increments_attempt(self) -> None:
        reflecting = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.succeeded)
        )

        result = self.router.after_reflection(
            reflecting, Reflection(action=ReflectionAction.retry, reason="try again")
        )

        self.assertEqual(result.phase, AgentPhase.executing)
        self.assertEqual(result.step_index, 0)
        self.assertEqual(result.attempt, 2)

    def test_replan_transitions_to_replanning(self) -> None:
        reflecting = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.succeeded)
        )

        result = self.router.after_reflection(
            reflecting, Reflection(action=ReflectionAction.replan, reason="new evidence")
        )

        self.assertEqual(result.phase, AgentPhase.replanning)

    def test_final_failure_transitions_to_failed(self) -> None:
        result = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.failed)
        )

        self.assertEqual(result.phase, AgentPhase.failed)

    def test_approval_required_transitions_to_blocked(self) -> None:
        result = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.approval_required)
        )

        self.assertEqual(result.phase, AgentPhase.blocked)

    def test_deduplicated_transitions_to_reflecting(self) -> None:
        result = self.router.after_execution(
            self.state, observation(ToolInvocationStatus.deduplicated)
        )

        self.assertEqual(result.phase, AgentPhase.reflecting)

    def test_pending_and_running_observations_raise_value_error(self) -> None:
        for status in (ToolInvocationStatus.pending, ToolInvocationStatus.running):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    self.router.after_execution(self.state, observation(status))

    def test_summary_marks_state_completed_with_answer(self) -> None:
        result = self.router.after_summary(self.state, "final answer")

        self.assertEqual(result.phase, AgentPhase.completed)
        self.assertEqual(result.final_answer, "final answer")

    def test_state_and_plan_steps_are_immutable(self) -> None:
        self.assertEqual(self.state.phase, AgentPhase.executing)
        self.assertEqual(self.state.step_index, 0)
        self.assertEqual(self.state.attempt, 1)
        self.assertIsInstance(self.state.plan.steps, tuple)
        with self.assertRaises(AttributeError):
            self.state.step_index = 1


if __name__ == "__main__":
    unittest.main()
