import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.exceptions import AppException
from app.domain.llm.entities import LLMChatRequest, LLMChatResult, LLMStreamDelta, LLMToolCall


# ===================== 第1步：封装 OpenAI 兼容的 HTTP 客户端 =====================
class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    async def chat(self, request: LLMChatRequest) -> LLMChatResult:
        # ===================== 第2步：组装 /chat/completions 请求体 =====================
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._build_message_payloads(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice

        # ===================== 第3步：向模型服务商发送 HTTP 请求 =====================
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise AppException(
                message=f"LLM request failed: {detail}",
                code=502,
                status_code=502,
            ) from exc

        # ===================== 第4步：把服务商错误统一转换为项目异常 =====================
        if response.status_code >= 400:
            raise AppException(
                message=f"LLM provider returned HTTP {response.status_code}",
                code=502,
                status_code=502,
            )

        # ===================== 第5步：解析 OpenAI 兼容响应结构 =====================
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AppException(
                message="LLM provider returned empty choices",
                code=502,
                status_code=502,
            )

        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise AppException(
                message="LLM provider returned empty message content",
                code=502,
                status_code=502,
            )
        tool_calls = self._parse_tool_calls(message.get("tool_calls"))

        return LLMChatResult(
            provider=request.provider,
            model=request.model,
            content=content,
            usage=data.get("usage"),
            tool_calls=tool_calls,
        )

    async def chat_vision(
        self,
        *,
        model: str,
        image_data_url: str,
        prompt: str,
        max_tokens: int,
        timeout_seconds: float | None = None,
    ) -> str:
        """调用视觉模型解析一张图片，返回提取的文本。

        使用 OpenAI 兼容的多模态消息格式：content 为
        [image_url, text] 数组（DashScope qwen-vl 系列同样遵循）。
        """

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "name": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds or self.timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"vision model request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        if response.status_code >= 400:
            raise AppException(
                message=f"vision model returned HTTP {response.status_code}",
                code=502,
                status_code=502,
            )
        data = response.json()
        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not isinstance(content, str) or not content.strip():
            raise AppException(
                message="vision model returned empty content",
                code=502,
                status_code=502,
            )
        return content.strip()

    async def chat_stream(self, request: LLMChatRequest) -> AsyncIterator[LLMStreamDelta]:
        """以流式方式调用 /chat/completions，逐段产出增量。

        OpenAI 兼容协议在 stream=true 时返回 SSE：每行 `data: {json}`，
        正文增量位于 choices[0].delta.content；思考型模型（Qwen/DeepSeek-R1 等）
        会先在 delta.reasoning_content 输出思考过程。`data: [DONE]` 表示结束。
        """

        payload = {
            "model": request.model,
            "messages": self._build_message_payloads(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        if request.extra_body:
            payload.update(request.extra_body)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        raise AppException(
                            message=f"LLM provider returned HTTP {response.status_code}",
                            code=502,
                            status_code=502,
                        )
                    async for line in response.aiter_lines():
                        clean_line = line.strip()
                        if not clean_line.startswith("data:"):
                            continue
                        data_text = clean_line.removeprefix("data:").strip()
                        if data_text == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        reasoning = delta.get("reasoning_content")
                        if isinstance(reasoning, str) and reasoning:
                            yield LLMStreamDelta(kind="reasoning", text=reasoning)
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield LLMStreamDelta(kind="content", text=content)
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"LLM request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

    @staticmethod
    def _build_message_payload(message) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            payload["name"] = message.name
        elif message.role == "tool":
            raise AppException(
                message="tool role message requires name",
                code=400,
                status_code=400,
            )
        else:
            payload["name"] = message.role
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                    },
                }
                for tool_call in message.tool_calls
            ]
        return payload

    @classmethod
    def _build_message_payloads(cls, messages: list) -> list[dict[str, Any]]:
        return [cls._build_message_payload(message) for message in messages]

    @staticmethod
    def _parse_tool_calls(raw: Any) -> list[LLMToolCall]:
        if not isinstance(raw, list):
            return []
        tool_calls: list[LLMToolCall] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            function = item.get("function") or {}
            name = function.get("name")
            arguments_raw = function.get("arguments") or "{}"
            try:
                arguments = json.loads(arguments_raw)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                continue
            tool_calls.append(
                LLMToolCall(id=str(item.get("id") or ""), name=name, arguments=arguments)
            )
        return tool_calls
