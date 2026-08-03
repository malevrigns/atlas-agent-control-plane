from fastapi import APIRouter, Depends

from app.application.llm_service import LLMService
from app.domain.llm.entities import LLMMessage
from app.schemas.common import ApiResponse
from app.schemas.llm import LLMChatRequest, LLMChatResponse

router = APIRouter(prefix="/llm", tags=["llm"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_llm_service() -> LLMService:
    return LLMService()


# ===================== 第2步：接收聊天请求并调用 LLMService =====================
@router.post("/chat", response_model=ApiResponse[LLMChatResponse])
async def chat(
    payload: LLMChatRequest,
    service: LLMService = Depends(build_llm_service),
) -> ApiResponse[LLMChatResponse]:
    result = await service.chat(
        messages=[
            LLMMessage(role=message.role, content=message.content)
            for message in payload.messages
        ],
        provider=payload.provider,
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    # LLMChatResult 使用了 slots=True，没有 __dict__。
    # 这里显式映射字段，也能让响应结构更清楚。
    return ApiResponse(
        data=LLMChatResponse(
            content=result.content,
            model=result.model,
            provider=result.provider,
            usage=result.usage,
        )
    )
