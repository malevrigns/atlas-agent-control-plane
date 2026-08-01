from pydantic import BaseModel, Field


# ===================== 第1步：定义模式说明响应 =====================
class ThinkingModeResponse(BaseModel):
    mode: str
    name: str
    summary: str
    best_for: str
    risk: str


class ThinkingModeListResponse(BaseModel):
    items: list[ThinkingModeResponse]


# ===================== 第2步：定义对比请求 =====================
class ThinkingCompareRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)


# ===================== 第3步：定义单个模式的演示结果 =====================
class ThinkingModeDemoResponse(BaseModel):
    mode: str
    name: str
    headline: str
    steps: list[str]
    tool_calls: list[str]
    final_answer: str


# ===================== 第4步：定义整体对比响应 =====================
class ThinkingComparisonResponse(BaseModel):
    task: str
    demos: list[ThinkingModeDemoResponse]

