import json
from collections.abc import AsyncIterator, Mapping
from uuid import UUID

from app.application.agent_summary_types import (
    AgentSummaryRequest,
    AgentSummaryResult,
    SummaryModel,
)
from app.application.agent_summary_references import (
    artifact_lines,
    first_line,
    match_line,
    parse_json_object,
    reference_lines,
    trim,
)
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException, ErrorSource
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent, SessionEventType


SUMMARY_MAX_TOKENS = 2500
RAW_OBSERVATION_LIMIT = 900
SEARCH_TITLE_LIMIT = 3
SUMMARY_TEXT_LIMIT = 180
AttemptKey = tuple[str, str, int, str, int]


def _identity_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AppException(
            message=f"event identity field {field} must be a non-empty string",
            source=ErrorSource.agent,
        )
    return value


def _identity_int(
    payload: Mapping[str, object],
    field: str,
    *,
    minimum: int,
) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AppException(
            message=f"event identity field {field} must be an integer >= {minimum}",
            source=ErrorSource.agent,
        )
    return value


class AgentSummaryService:
    def __init__(self, uow: UnitOfWork, model: SummaryModel) -> None:
        self._uow = uow
        self._model = model

    async def stream(
        self, request: AgentSummaryRequest
    ) -> AsyncIterator[tuple[str, str] | AgentSummaryResult]:
        evidence = self.build_evidence(request.plan, request.events)
        if not evidence:
            raise AppException(
                message="final answer evidence is empty",
                source=ErrorSource.agent,
            )
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        async for delta in self._model.chat_stream(
            self._build_messages(request.plan, evidence),
            temperature=0.2,
            max_tokens=SUMMARY_MAX_TOKENS,
        ):
            kind = getattr(delta, "kind", None)
            text = getattr(delta, "text", None)
            if not isinstance(kind, str):
                raise AppException(message="summary delta kind must be a string")
            if not isinstance(text, str):
                raise AppException(message="summary delta text must be a string")
            if kind == "reasoning":
                reasoning_parts.append(text)
                yield ("thinking_delta", text)
            elif kind in {"content", "answer"}:
                answer_parts.append(text)
                yield ("answer_delta", text)
            else:
                raise AppException(message=f"unsupported summary delta kind: {kind}")
        final_answer = "".join(answer_parts).strip()
        if not final_answer:
            raise AppException(
                message="model returned empty final answer",
                source=ErrorSource.llm,
            )
        yield await self._persist_result(
            request.session_id,
            final_answer,
            "".join(reasoning_parts).strip(),
        )

    async def _persist_result(
        self, session_id: UUID, final_answer: str, reasoning: str
    ) -> AgentSummaryResult:
        message = await self._uow.session_messages.add_assistant_message(
            session_id=session_id,
            content=final_answer,
        )
        event = await self._uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.message_created,
            payload={
                "message_id": str(message.id),
                "role": message.role.value,
                "content": message.content,
            },
        )
        return AgentSummaryResult(final_answer, reasoning, event, message.id)

    def build_evidence(
        self,
        plan: Mapping[str, object],
        events: tuple[SessionEvent, ...] | list[SessionEvent],
    ) -> str:
        step_map = self._step_map(plan)
        accepted = self._accepted_tool_events(events)
        blocks = [
            self._evidence_block(event, step_map, index)
            for index, event in accepted
        ]
        return "\n\n".join(blocks)

    def _evidence_block(
        self,
        event: SessionEvent,
        step_map: Mapping[str, Mapping[str, object]],
        index: int,
    ) -> str:
        title = self._event_title(event, step_map, index)
        tool_name = str(event.payload.get("tool_name") or "")
        output = str(event.payload.get("output") or "")
        lines = [
            f"## {title}",
            f"- 工具：{tool_name}",
            f"- 参数：{json.dumps(event.payload.get('arguments') or {}, ensure_ascii=False)}",
            f"- 状态：{event.payload.get('status') or 'unknown'}",
            f"- 尝试：{event.payload.get('attempt') or 1}",
            f"- 摘要：{self.summarize_tool_output(tool_name, output)}",
        ]
        references = reference_lines(title, tool_name, output)
        artifacts = artifact_lines(title, tool_name, output)
        if references:
            lines.extend(["- 引用：", *references])
        if artifacts:
            lines.extend(["- 产物：", *artifacts])
        lines.extend(["- 原始观察摘录：", trim(output, RAW_OBSERVATION_LIMIT)])
        return "\n".join(lines)

    @staticmethod
    def _build_messages(
        plan: Mapping[str, object], evidence: str
    ) -> list[LLMMessage]:
        goal = plan.get("goal") or plan.get("title") or "未命名任务"
        return [
            LLMMessage(
                role="system",
                content=(
                    "你是 AtlasAgent 的任务总结器。根据可观察工具输出写中文 Markdown，"
                    "不要编造未执行动作、隐藏推理或内部事件。固定包含：## 总结、"
                    "## 证据与引用、## 产物、## 下一步建议。没有产物时明确说明。"
                ),
            ),
            LLMMessage(
                role="user",
                content=f"任务目标：{goal}\n\n工具观察材料：\n{evidence}",
            ),
        ]

    @staticmethod
    def _step_map(plan: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        steps = plan.get("steps")
        if not isinstance(steps, (list, tuple)):
            return {}
        return {
            str(step.get("id")): step
            for step in steps
            if isinstance(step, Mapping) and step.get("id")
        }

    @classmethod
    def _accepted_attempts(
        cls,
        events: tuple[SessionEvent, ...] | list[SessionEvent],
    ) -> set[AttemptKey]:
        accepted = set()
        for event in events:
            if event.type is not SessionEventType.step_reflected:
                continue
            if event.payload.get("action") != "accept":
                continue
            accepted.add(cls._attempt_key(event))
        return accepted

    @classmethod
    def _accepted_tool_events(
        cls,
        events: tuple[SessionEvent, ...] | list[SessionEvent],
    ) -> list[tuple[int, SessionEvent]]:
        accepted = cls._accepted_attempts(events)
        matched = []
        for index, event in enumerate(events, start=1):
            if event.type is not SessionEventType.tool_called:
                continue
            if cls._attempt_key(event) in accepted:
                matched.append((index, event))
        return matched

    @staticmethod
    def _attempt_key(event: SessionEvent) -> AttemptKey:
        payload = event.payload
        return (
            _identity_text(payload, "run_id"),
            _identity_text(payload, "plan_id"),
            _identity_int(payload, "plan_revision", minimum=0),
            _identity_text(payload, "step_id"),
            _identity_int(payload, "attempt", minimum=1),
        )

    @staticmethod
    def _event_title(
        event: SessionEvent,
        step_map: Mapping[str, Mapping[str, object]],
        index: int,
    ) -> str:
        step = step_map.get(str(event.payload.get("step_id") or ""), {})
        return str(
            step.get("title")
            or event.payload.get("tool_name")
            or f"步骤 {index}"
        )

    def summarize_tool_output(self, tool_name: str, output: str) -> str:
        parsed = parse_json_object(output)
        if parsed and parsed.get("kind") == "search_results":
            return self._summarize_search_results(parsed)
        if tool_name.startswith("shell_"):
            command = match_line(output, "命令")
            code = match_line(output, "退出码") or "未知"
            return f"已执行命令{f'“{command}”' if command else ''}，退出码 {code}。"
        if tool_name.startswith("browser_"):
            title = match_line(output, "页面标题")
            url = match_line(output, "当前地址")
            return f"浏览器已返回：{title or url or first_line(output)}"
        return trim(first_line(output), SUMMARY_TEXT_LIMIT)

    @staticmethod
    def _summarize_search_results(parsed: Mapping[str, object]) -> str:
        raw_items = parsed.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        titles = [
            str(item.get("title"))
            for item in items[:SEARCH_TITLE_LIMIT]
            if isinstance(item, Mapping) and item.get("title")
        ]
        suffix = f" 代表结果包括：{'、'.join(titles)}。" if titles else ""
        query = parsed.get("query") or "相关关键词"
        return f"已搜索“{query}”，找到 {len(items)} 条候选结果。{suffix}"
