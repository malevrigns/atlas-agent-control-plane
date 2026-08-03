from pydantic import BaseModel, Field


class MultiAgentRoleResponse(BaseModel):
    key: str  # 程序内部识别角色的稳定标识，例如 manager。
    name: str  # 展示给用户看的角色名称。
    responsibility: str  # 这个角色在协作流程中负责什么。
    capability: str  # 当前角色擅长处理的任务类型。


class MultiAgentSubTaskResponse(BaseModel):
    id: str  # Manager 拆出的子任务 ID。
    assignee: str  # 负责执行该子任务的 Agent 角色。
    title: str  # 子任务标题。
    instruction: str  # Manager 交给 Worker 的具体指令。
    expected_output: str  # 期望 Worker 产出的结果形态。
    status: str  # pending、completed、failed 等状态。
    output: str  # Worker 执行后的输出。


class MultiAgentReviewResponse(BaseModel):
    reviewer: str  # 执行评审的 Agent 名称。
    status: str  # approved 或 needs_revision。
    comments: list[str]  # Reviewer 给出的检查意见。
    improvement: str  # 面向下一轮协作的改进建议。


class MultiAgentRunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)


class MultiAgentRunResponse(BaseModel):
    kind: str  # 固定为 multi_agent_result，前端用它选择预览卡片。
    task: str  # 本次协作围绕的用户任务。
    manager: str  # 负责拆解和汇总的 Agent。
    roles: list[MultiAgentRoleResponse]
    subtasks: list[MultiAgentSubTaskResponse]
    review: MultiAgentReviewResponse
    final_answer: str


class MultiAgentRoleListResponse(BaseModel):
    items: list[MultiAgentRoleResponse]
