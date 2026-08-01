import httpx

from app.core.exceptions import AppException
from app.domain.llm.entities import LLMChatRequest, LLMChatResult


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
        payload = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

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
            raise AppException(
                message=f"LLM request failed: {exc}",
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
        if not isinstance(content, str):
            raise AppException(
                message="LLM provider returned empty message content",
                code=502,
                status_code=502,
            )

        # 这里只取第一条回复，后续如果支持多候选结果，可以在这里扩展。
        return LLMChatResult(
            provider=request.provider,
            model=request.model,
            content=content,
            usage=data.get("usage"),
        )
