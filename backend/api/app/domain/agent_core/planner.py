from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4


# ===================== 第1步：定义计划步骤状态 =====================
class PlanStepStatus(StrEnum):
    """计划步骤的执行状态。

    第 18 章只生成计划，不执行步骤，所以默认都是 pending。
    """

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


# ===================== 第2步：定义一个计划步骤 =====================
@dataclass(slots=True)
class PlanStep:
    """PlannerAgent 生成的单个任务步骤。"""

    id: UUID
    title: str
    description: str
    expected_output: str
    status: PlanStepStatus = PlanStepStatus.pending


# ===================== 第3步：定义完整计划 =====================
@dataclass(slots=True)
class AgentPlan:
    """PlannerAgent 对用户任务生成的完整计划。"""

    id: UUID
    title: str
    goal: str
    steps: list[PlanStep]
    source: str


# ===================== 第4步：提供便捷创建函数 =====================
def create_agent_plan(
    title: str,
    goal: str,
    steps: list[PlanStep],
    source: str,
) -> AgentPlan:
    """统一创建计划对象，避免应用层手动生成 plan id。"""

    return AgentPlan(
        id=uuid4(),
        title=title,
        goal=goal,
        steps=steps,
        source=source,
    )


def create_plan_step(
    title: str,
    description: str,
    expected_output: str,
) -> PlanStep:
    """统一创建计划步骤，默认状态为 pending。"""

    return PlanStep(
        id=uuid4(),
        title=title,
        description=description,
        expected_output=expected_output,
    )

