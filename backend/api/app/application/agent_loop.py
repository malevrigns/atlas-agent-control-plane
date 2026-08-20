"""步骤内的多轮工具调用循环（Generic Agent Loop）。

把「一步一工具」升级为「步骤内模型自主多轮调用工具」：
- NativeFunctionCallStrategy：原生 OpenAI function calling（可一轮多工具并行）。
- JsonPromptStrategy：模型输出 JSON 选择工具的兜底。
- StepAgentLoop：统一循环 + 并发执行 + 护栏。

工具结果以消息形式回喂给模型，模型「看结果后再决策」，直到该步骤完成。
"""

import asyncio
import json
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from app.application.llm_service import LLMService
from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException
from app.domain.agent_core.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolInvocationStatus,
    ToolRegistry,
    ToolRiskLevel,
    to_openai_tool_schemas,
)
from app.domain.llm.entities import LLMMessage, LLMToolCall


@dataclass(slots=True)
class ToolCallRequest:
    id: str | None
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class TurnOutcome:
    tool_calls: list[ToolCallRequest]
    content: str


@dataclass(slots=True)
class StepToolCall:
    turn: int
    tool_call_id: str
    result: ToolCallResult


@dataclass(slots=True)
class StepLoopResult:
    tool_calls: list[StepToolCall]
    summary: str


class ToolCallStrategy:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def next_turn(self, messages: list[LLMMessage]) -> TurnOutcome:
        raise NotImplementedError

    def build_assistant_message(self, outcome: TurnOutcome) -> LLMMessage:
        raise NotImplementedError

    def build_tool_result_message(
        self, request: ToolCallRequest, call_id: str, output: str
    ) -> LLMMessage:
        raise NotImplementedError


class NativeFunctionCallStrategy(ToolCallStrategy):
    def __init__(self, llm_service: LLMService, tool_schemas: list[dict[str, Any]]) -> None:
        super().__init__(llm_service)
        self.tool_schemas = tool_schemas

    async def next_turn(self, messages: list[LLMMessage]) -> TurnOutcome:
        result = await self.llm_service.chat(messages, tools=self.tool_schemas)
        tool_calls = [
            ToolCallRequest(id=tool_call.id or None, name=tool_call.name, arguments=tool_call.arguments)
            for tool_call in result.tool_calls
        ]
        return TurnOutcome(tool_calls=tool_calls, content=result.content)

    def build_assistant_message(self, outcome: TurnOutcome) -> LLMMessage:
        return LLMMessage(
            role="assistant",
            content=outcome.content,
            tool_calls=[
                LLMToolCall(
                    id=tool_call.id or f"call_{index}",
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                )
                for index, tool_call in enumerate(outcome.tool_calls)
            ],
        )

    def build_tool_result_message(
        self, request: ToolCallRequest, call_id: str, output: str
    ) -> LLMMessage:
        return LLMMessage(
            role="tool", content=output, name=request.name, tool_call_id=call_id
        )


class JsonPromptStrategy(ToolCallStrategy):
    def __init__(self, llm_service: LLMService, tool_definitions: list[ToolDefinition]) -> None:
        super().__init__(llm_service)
        self.tool_prompt = self._render_tool_prompt(tool_definitions)

    async def next_turn(self, messages: list[LLMMessage]) -> TurnOutcome:
        instruction = (
            "你是 Agent 的执行器。请根据可用工具和上下文，决定下一步。"
            "只返回 JSON，不要返回 Markdown，不要在 JSON 外输出任何内容："
            '- 需要调用工具时返回：{"tool_name":"工具名","arguments":{...}}'
            '- 已经完成、直接给出结论时返回：{"final_answer":"给用户的最终回答"}'
            "如果当前只是分析、总结、解释类任务，请直接给出 final_answer，不要调用工具。"
        )
        system_content = f"{instruction}\n\n可用工具：\n{self.tool_prompt}"
        prompt_messages: list[LLMMessage] = [messages[0]] if messages else []
        prompt_messages.append(LLMMessage(role="system", content=system_content))
        prompt_messages.extend(messages[1:])

        result = await self.llm_service.chat(
            prompt_messages, temperature=0.1, max_tokens=2400
        )
        payload = self._parse_json(result.content)
        if not isinstance(payload, dict):
            return TurnOutcome(tool_calls=[], content=result.content)

        final_answer = payload.get("final_answer")
        if final_answer is not None and str(final_answer).strip():
            return TurnOutcome(tool_calls=[], content=str(final_answer))

        tool_name = str(payload.get("tool_name") or "").strip()
        arguments = payload.get("arguments")
        if tool_name and isinstance(arguments, dict):
            return TurnOutcome(
                tool_calls=[ToolCallRequest(id=None, name=tool_name, arguments=arguments)],
                content=result.content,
            )
        return TurnOutcome(tool_calls=[], content=result.content)

    def build_assistant_message(self, outcome: TurnOutcome) -> LLMMessage:
        return LLMMessage(role="assistant", content=outcome.content)

    def build_tool_result_message(
        self, request: ToolCallRequest, call_id: str, output: str
    ) -> LLMMessage:
        return LLMMessage(
            role="system",
            content=f"[工具结果] 工具 {request.name} 返回：\n{output}",
        )

    @staticmethod
    def _render_tool_prompt(tool_definitions: list[ToolDefinition]) -> str:
        lines: list[str] = []
        for tool in tool_definitions:
            parameters = [
                {
                    "name": parameter.name,
                    "type": parameter.type,
                    "required": parameter.required,
                    "description": parameter.description,
                }
                for parameter in tool.parameters
            ]
            lines.append(
                json.dumps(
                    {"name": tool.name, "description": tool.description, "parameters": parameters},
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _parse_json(value: str) -> Any:
        clean = value.strip()
        start = clean.find("{")
        end = clean.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        try:
            return json.loads(clean[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            return None


class StepAgentLoop:
    _PERSONA = (
        "你是 AtlasAgent，一个严谨的中文 AI 助手。"
        "你会拿到一组工具和当前步骤的目标，请自主决定是否调用工具、调用哪些工具，"
        "并基于工具返回结果推进，直到完成本步骤。"
        "分析、推理、总结、撰写这类不需要外部操作的步骤，请直接给出结论，不要调用工具。"
    )

    _TOOL_RULES = (
        "工具使用准则：\n"
        "1. 执行多行代码时，禁止塞进 shell 单行命令（python -c 多行必然语法错误）；"
        "正确做法：先用 file_write 把完整代码写入脚本文件（如 main.py），"
        "再用 shell_run 执行 python3 main.py。严禁执行尚未创建的脚本文件。\n"
        "2. 需要根据网页内容回答、提取信息或总结页面时，用 browser_read；"
        "browser_open 只用于确认页面可达或为截图做准备；"
        "截图用 browser_screenshot；查会话状态用 browser_status。\n"
        "3. 文件读写用 file_read / file_write，路径相对于沙箱工作目录。\n"
        "4. 工具执行失败时，根据错误信息调整后再试，不要机械重复同一个失败调用。\n"
        "5. 每一步最终都要给出面向用户的结论（Markdown），不要只停留在工具调用。"
    )

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        llm_service: LLMService | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        self.registry = registry
        self.llm_service = llm_service or LLMService()
        self.runtime = ToolRuntime(registry, uow=uow)
        self.tool_definitions = registry.list_tools()
        self.tool_schemas = to_openai_tool_schemas(self.tool_definitions)

    async def run_step(
        self,
        *,
        session_id: UUID | None,
        plan: dict,
        step: dict,
        index: int,
        context: str,
        execution_context: ToolExecutionContext,
    ) -> StepLoopResult:
        initial_messages = self._build_initial_messages(
            plan=plan, step=step, index=index, context=context
        )

        if not self.llm_service.is_configured():
            return await self._run_rule_fallback(
                plan=plan,
                step=step,
                index=index,
                context=context,
                execution_context=execution_context,
            )

        for strategy in self._ordered_strategies():
            messages = [
                LLMMessage(
                    role=message.role,
                    content=message.content,
                    tool_calls=message.tool_calls,
                    tool_call_id=message.tool_call_id,
                )
                for message in initial_messages
            ]
            result = await self._run_loop(
                strategy=strategy,
                messages=messages,
                execution_context=execution_context,
            )
            if result is not None:
                return result

        return await self._run_rule_fallback(
            plan=plan,
            step=step,
            index=index,
            context=context,
            execution_context=execution_context,
        )

    async def _run_loop(
        self,
        *,
        strategy: ToolCallStrategy,
        messages: list[LLMMessage],
        execution_context: ToolExecutionContext,
    ) -> StepLoopResult | None:
        executed: list[StepToolCall] = []
        total_tool_calls = 0
        first_turn = True
        repeat_key: str | None = None
        repeat_count = 0

        for turn in range(1, settings.agent_step_max_iterations + 1):
            try:
                outcome = await strategy.next_turn(messages)
            except AppException:
                if first_turn:
                    return None
                raise
            first_turn = False

            if not outcome.tool_calls:
                summary = outcome.content.strip() or self._fallback_summary(executed)
                return StepLoopResult(tool_calls=executed, summary=summary)

            if total_tool_calls + len(outcome.tool_calls) > settings.agent_step_max_tool_calls:
                break

            results = await asyncio.gather(
                *[
                    self._execute_tool(request, execution_context, turn, offset)
                    for offset, request in enumerate(outcome.tool_calls)
                ]
            )

            messages.append(strategy.build_assistant_message(outcome))
            for request, (call_id, result) in zip(outcome.tool_calls, results):
                executed.append(StepToolCall(turn=turn, tool_call_id=call_id, result=result))
                messages.append(
                    strategy.build_tool_result_message(request, call_id, result.output)
                )
                total_tool_calls += 1
                repeat_key, repeat_count = self._track_repeat(
                    repeat_key, repeat_count, request.name, request.arguments
                )
                if repeat_count >= settings.agent_step_repeat_call_limit:
                    messages.append(
                        LLMMessage(
                            role="system",
                            content="检测到重复调用同一工具，请停止调用工具并直接给出该步骤的结论。",
                        )
                    )
                    repeat_count = 0

        return StepLoopResult(tool_calls=executed, summary=self._fallback_summary(executed))

    async def _execute_tool(
        self,
        request: ToolCallRequest,
        base_context: ToolExecutionContext,
        turn: int,
        offset: int,
    ) -> tuple[str, ToolCallResult]:
        call_id = request.id or f"call_{turn}_{offset}"
        context = replace(
            base_context,
            idempotency_key=f"{base_context.idempotency_key or 'step'}:{turn}:{offset}",
        )
        try:
            result = await self.runtime.execute(request.name, request.arguments, context)
        except AppException as error:
            result = ToolCallResult(
                tool_name=request.name,
                arguments=request.arguments,
                output=f"工具执行失败：{error.message}",
                status=ToolInvocationStatus.failed,
                risk_level=ToolRiskLevel.low,
            )
        return call_id, result

    async def _run_rule_fallback(
        self,
        *,
        plan: dict,
        step: dict,
        index: int,
        context: str,
        execution_context: ToolExecutionContext,
    ) -> StepLoopResult:
        from app.application.tool_selection_service import ModelToolSelectionService

        selector = ModelToolSelectionService(
            registry=self.registry,
            llm_service=self.llm_service,
            uow=self.runtime.uow,
        )
        result = await selector.call_tool_for_step(
            plan=plan,
            step=step,
            index=index,
            agent_context=context,
            execution_context=execution_context,
        )
        tool_call = StepToolCall(
            turn=1,
            tool_call_id=result.invocation_id or "rule",
            result=result,
        )
        return StepLoopResult(tool_calls=[tool_call], summary=result.output)

    def _ordered_strategies(self) -> list[ToolCallStrategy]:
        mode = settings.agent_tool_mode
        if mode == "json":
            return [JsonPromptStrategy(self.llm_service, self.tool_definitions)]
        if mode == "native":
            return [NativeFunctionCallStrategy(self.llm_service, self.tool_schemas)]
        return [
            NativeFunctionCallStrategy(self.llm_service, self.tool_schemas),
            JsonPromptStrategy(self.llm_service, self.tool_definitions),
        ]

    def _build_initial_messages(
        self, *, plan: dict, step: dict, index: int, context: str
    ) -> list[LLMMessage]:
        system = f"{self._PERSONA}\n\n{self._TOOL_RULES}"
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=self._build_step_task(plan, step, index, context)),
        ]

    @staticmethod
    def _build_step_task(plan: dict, step: dict, index: int, context: str) -> str:
        goal = str(plan.get("goal") or plan.get("title") or "")
        title = str(step.get("title") or "")
        description = str(step.get("description") or "")
        expected = str(step.get("expected_output") or "")
        parts: list[str] = []
        if goal:
            parts.append(f"任务目标：{goal}")
        parts.append(f"当前是第 {index} 步，需要完成：{title or '（未命名步骤）'}")
        if description:
            parts.append(f"步骤说明：{description}")
        if expected:
            parts.append(f"期望产出：{expected}")
        if context:
            parts.append(f"上下文信息：\n{context}")
        return "\n\n".join(parts)

    @staticmethod
    def _track_repeat(
        current_key: str | None,
        current_count: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[str | None, int]:
        key = json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True, ensure_ascii=False)
        if key == current_key:
            return key, current_count + 1
        return key, 1

    @staticmethod
    def _fallback_summary(executed: list[StepToolCall]) -> str:
        if not executed:
            return "本步骤未执行任何工具。"
        lines = [
            f"- {item.result.tool_name}：{StepAgentLoop._trim(item.result.output, 200)}"
            for item in executed
        ]
        return "本步骤执行了以下操作：\n" + "\n".join(lines)

    @staticmethod
    def _trim(value: str, limit: int) -> str:
        clean = " ".join(value.split())
        if len(clean) <= limit:
            return clean
        return f"{clean[:limit]}..."
