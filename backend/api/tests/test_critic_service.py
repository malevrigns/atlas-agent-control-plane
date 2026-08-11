import unittest
from uuid import uuid4

from app.application.critic_service import CriticService
from app.core.exceptions import AppException
from app.domain.agent_core.planner import PlanStepStatus
from app.domain.agent_core.tools import ToolInvocationStatus
from app.domain.agent_runtime.entities import (
    ReflectionAction,
    RunPlanStep,
    StepObservation,
)
from app.domain.llm.entities import LLMChatResult


class FakeCriticModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []

    async def chat(self, messages, **kwargs) -> LLMChatResult:
        self.messages = messages
        return LLMChatResult(provider="test", model="test-model", content=self.content)


def build_step() -> RunPlanStep:
    return RunPlanStep(
        id=uuid4(),
        title="Inspect source",
        description="Inspect the relevant source files.",
        expected_output="A verified implementation detail.",
        status=PlanStepStatus.pending,
    )


class CriticServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_returns_each_protocol_action(self) -> None:
        cases = (
            ("accept", "output matches expected result"),
            ("retry", "tool timed out"),
            ("replan", "current step cannot satisfy the goal"),
            ("fail", "permission denied"),
        )
        observation = StepObservation(
            status=ToolInvocationStatus.succeeded,
            output="source inspection complete",
        )

        for action, reason in cases:
            with self.subTest(action=action):
                service = CriticService(FakeCriticModel(
                    f'{{"action":"{action}","reason":"{reason}"}}'
                ))

                reflection = await service.evaluate(build_step(), observation)

                self.assertEqual(reflection.action, ReflectionAction(action))
                self.assertEqual(reflection.reason, reason)

    async def test_evaluate_includes_step_and_observation_in_model_prompt(self) -> None:
        model = FakeCriticModel(
            '{"action":"accept","reason":"output matches expected result"}'
        )
        service = CriticService(model)

        await service.evaluate(
            build_step(),
            StepObservation(
                status=ToolInvocationStatus.succeeded,
                output="source inspection complete",
            ),
        )

        self.assertEqual(model.messages[0].role, "system")
        self.assertIn("action", model.messages[0].content)
        self.assertIn("reason", model.messages[0].content)
        self.assertIn("Inspect source", model.messages[1].content)
        self.assertIn("succeeded", model.messages[1].content)

    async def test_evaluate_rejects_malformed_json(self) -> None:
        service = CriticService(FakeCriticModel("not json"))

        with self.assertRaises(AppException):
            await service.evaluate(
                build_step(),
                StepObservation(ToolInvocationStatus.succeeded, "result"),
            )

    async def test_evaluate_rejects_unknown_action(self) -> None:
        service = CriticService(
            FakeCriticModel('{"action":"continue","reason":"keep going"}')
        )

        with self.assertRaises(AppException):
            await service.evaluate(
                build_step(),
                StepObservation(ToolInvocationStatus.succeeded, "result"),
            )

    async def test_evaluate_rejects_empty_reason(self) -> None:
        service = CriticService(FakeCriticModel('{"action":"retry","reason":""}'))

        with self.assertRaises(AppException):
            await service.evaluate(
                build_step(),
                StepObservation(ToolInvocationStatus.succeeded, "result"),
            )

    async def test_evaluate_rejects_accept_for_unsuccessful_observations(self) -> None:
        for status in (
            ToolInvocationStatus.failed,
            ToolInvocationStatus.denied,
            ToolInvocationStatus.timed_out,
        ):
            with self.subTest(status=status):
                service = CriticService(
                    FakeCriticModel('{"action":"accept","reason":"looks good"}')
                )

                with self.assertRaises(AppException):
                    await service.evaluate(build_step(), StepObservation(status, "result"))

    async def test_evaluate_accepts_deduplicated_observation(self) -> None:
        service = CriticService(
            FakeCriticModel('{"action":"accept","reason":"cached output matches"}')
        )

        reflection = await service.evaluate(
            build_step(),
            StepObservation(ToolInvocationStatus.deduplicated, "cached result"),
        )

        self.assertEqual(reflection.action, ReflectionAction.accept)


if __name__ == "__main__":
    unittest.main()
