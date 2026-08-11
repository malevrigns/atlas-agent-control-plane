import json
from collections.abc import AsyncIterator, Mapping
from uuid import UUID

from app.application.agent_summary_types import (
    AgentSummaryRequest,
    AgentSummaryResult,
    SummaryModel,
)
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException, ErrorSource
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent, SessionEventType


SUMMARY_MAX_TOKENS = 2500
RAW_OBSERVATION_LIMIT = 900
SEARCH_RESULT_LIMIT = 5
SEARCH_TITLE_LIMIT = 3
REFERENCE_TEXT_LIMIT = 160
SNIPPET_LIMIT = 90
SUMMARY_TEXT_LIMIT = 180
BYTES_PER_KIBIBYTE = 1024


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
        blocks = []
        for index, event in enumerate(events, start=1):
            if event.type is not SessionEventType.tool_called:
                continue
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
            references = self._reference_lines(title, tool_name, output)
            artifacts = self._artifact_lines(title, tool_name, output)
            if references:
                lines.extend(["- 引用：", *references])
            if artifacts:
                lines.extend(["- 产物：", *artifacts])
            lines.extend(["- 原始观察摘录：", self._trim(output, RAW_OBSERVATION_LIMIT)])
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

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

    def _reference_lines(self, title: str, tool_name: str, output: str) -> list[str]:
        parsed = self._parse_json_object(output)
        if parsed and parsed.get("kind") == "search_results":
            items = parsed.get("items")
            if not isinstance(items, list):
                return []
            return self._search_reference_lines(items)
        if tool_name.startswith("file_"):
            lines = [
                line.strip()
                for line in output.splitlines()
                if line.strip()
                and (line.startswith(("文件：", "路径：", "第 ")) or "行" in line)
            ][:4]
            return [
                f"- **{title}**：{self._trim(line, REFERENCE_TEXT_LIMIT)}"
                for line in lines
            ]
        if tool_name.startswith("browser_"):
            return self._browser_reference_lines(title, output)
        return []

    def _search_reference_lines(self, items: list[object]) -> list[str]:
        lines = []
        for item in items[:SEARCH_RESULT_LIMIT]:
            if not isinstance(item, Mapping):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if title and url:
                suffix = (
                    f"：{self._trim(snippet, SNIPPET_LIMIT)}" if snippet else ""
                )
                lines.append(f"- **{title}**（{url}）{suffix}")
        return lines

    def _browser_reference_lines(self, title: str, output: str) -> list[str]:
        page_title = self._match_line(output, "页面标题")
        url = self._match_line(output, "页面已打开") or self._match_line(
            output, "当前地址"
        )
        if not page_title and not url:
            return []
        suffix = f"（{url}）" if url else ""
        return [f"- **{title}**：{page_title or '浏览器页面'}{suffix}"]

    def _artifact_lines(self, title: str, tool_name: str, output: str) -> list[str]:
        parsed = self._parse_json_object(output)
        if parsed and parsed.get("kind") == "browser_screenshot":
            size = int(parsed.get("size") or 0)
            size_text = (
                f"{round(size / BYTES_PER_KIBIBYTE)} KB"
                if size > 0
                else "未知大小"
            )
            return [f"- **{title}**：浏览器截图已生成，大小约 {size_text}。"]
        lines = []
        for label in ("输出文件", "文件路径", "保存路径", "下载地址"):
            value = self._match_line(output, label)
            if value:
                lines.append(f"- **{title}**：{label} `{value}`")
        if lines or not tool_name.startswith("file_write"):
            return lines
        return [
            f"- **{title}**：{self._trim(self._first_line(output), REFERENCE_TEXT_LIMIT)}"
        ]

    def summarize_tool_output(self, tool_name: str, output: str) -> str:
        parsed = self._parse_json_object(output)
        if parsed and parsed.get("kind") == "search_results":
            return self._summarize_search_results(parsed)
        if tool_name.startswith("shell_"):
            command = self._match_line(output, "命令")
            code = self._match_line(output, "退出码") or "未知"
            return f"已执行命令{f'“{command}”' if command else ''}，退出码 {code}。"
        if tool_name.startswith("browser_"):
            title = self._match_line(output, "页面标题")
            url = self._match_line(output, "当前地址")
            return f"浏览器已返回：{title or url or self._first_line(output)}"
        return self._trim(self._first_line(output), SUMMARY_TEXT_LIMIT)

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

    @staticmethod
    def _parse_json_object(value: str) -> dict[str, object] | None:
        try:
            loaded = json.loads(value)
        except (TypeError, ValueError):
            return None
        return loaded if isinstance(loaded, dict) else None

    @staticmethod
    def _match_line(text: str, label: str) -> str:
        prefix = f"{label}："
        for line in text.splitlines():
            if line.startswith(prefix):
                return line.removeprefix(prefix).strip()
        return ""

    @staticmethod
    def _first_line(text: str) -> str:
        for line in text.splitlines():
            if line.strip():
                return line.strip()
        return "工具已返回结果。"

    @staticmethod
    def _trim(value: str, max_length: int) -> str:
        clean = " ".join(value.split())
        return clean if len(clean) <= max_length else f"{clean[:max_length]}..."
