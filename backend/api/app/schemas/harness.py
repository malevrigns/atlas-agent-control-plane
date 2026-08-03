from datetime import datetime

from pydantic import BaseModel, Field


class HarnessExpectationResponse(BaseModel):
    required_events: list[str]  # 这条用例必须出现的事件类型。
    required_tools: list[str]  # 这条用例必须调用的工具名。
    required_files: list[str]  # 这条用例必须生成的文件名或文件标识。
    forbidden_events: list[str]  # 一旦出现就说明用例失败的事件类型。


class HarnessCaseResponse(BaseModel):
    id: str
    title: str
    task: str
    description: str
    tags: list[str]
    expectation: HarnessExpectationResponse


class HarnessCaseListResponse(BaseModel):
    items: list[HarnessCaseResponse]


class HarnessRunRequest(BaseModel):
    mode: str = Field(default="simulate", pattern="^(simulate|real)$")


class HarnessAssertionResponse(BaseModel):
    name: str  # 断言名称，例如 required_tool:browser_open。
    passed: bool  # true 表示这条断言通过。
    detail: str  # 断言解释，失败时会说明缺少什么。


class HarnessEventResponse(BaseModel):
    id: str
    type: str
    payload: dict
    created_at: str


class HarnessRunResponse(BaseModel):
    id: str
    case_id: str
    mode: str
    status: str
    task: str
    prompt_summary: str
    events: list[HarnessEventResponse]
    assertions: list[HarnessAssertionResponse]
    started_at: datetime
    completed_at: datetime | None


class HarnessReplayResponse(BaseModel):
    run: HarnessRunResponse
    events: list[HarnessEventResponse]
