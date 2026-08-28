import json
from typing import Protocol

from app.core.exceptions import AppException
from app.domain.agent_runtime.entities import (
    Reflection,
    ReflectionAction,
    RunPlanStep,
    StepObservation,
)
from app.domain.agent_runtime.router import SUCCESS_STATUSES
from app.domain.llm.entities import LLMChatResult, LLMMessage


class CriticModel(Protocol):
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMChatResult: ...


class CriticService:
    def __init__(self, model: CriticModel) -> None:
        self._model = model

    async def evaluate(
        self, step: RunPlanStep, observation: StepObservation
    ) -> Reflection:
        result = await self._model.chat(self._build_messages(step, observation))
        reflection = self._parse_reflection(result.content)
        if (
            reflection.action is ReflectionAction.accept
            and observation.status not in SUCCESS_STATUSES
        ):
            raise AppException(message="cannot accept a non-success observation")
        return reflection

    @staticmethod
    def _build_messages(
        step: RunPlanStep, observation: StepObservation
    ) -> list[LLMMessage]:
        return [
            LLMMessage(
                role="system",
                content=(
                    "Evaluate the executed plan step. Reply with one JSON object containing "
                    'only "action" and "reason". action must be one of: accept, retry, '
                    "replan, fail. reason must explain the decision. "
                    "The step count itself is not a quality standard — what matters is "
                    "whether each step can be independently verified. Do not reject a step "
                    "solely because the number of steps differs from the plan."
                ),
            ),
            LLMMessage(
                role="user",
                content=(
                    f"Step title: {step.title}\n"
                    f"Step description: {step.description}\n"
                    f"Expected output: {step.expected_output}\n"
                    f"Observation status: {observation.status.value}\n"
                    f"Observation output: {observation.output}"
                ),
            ),
        ]

    @staticmethod
    def _parse_reflection(content: str) -> Reflection:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AppException(message="critic response must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise AppException(message="critic response must be a JSON object")
        action = payload.get("action")
        reason = payload.get("reason")
        if not isinstance(action, str):
            raise AppException(message="critic response action must be a string")
        if not isinstance(reason, str) or not reason.strip():
            raise AppException(message="critic response reason must be non-empty")
        try:
            return Reflection(action=ReflectionAction(action), reason=reason)
        except ValueError as exc:
            raise AppException(message=f"unsupported critic action: {action}") from exc
