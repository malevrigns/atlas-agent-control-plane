from dataclasses import dataclass
from enum import StrEnum


# ===================== 第1步：定义本章要对比的 Agent 思维模式 =====================
class ThinkingMode(StrEnum):
    """Agent 从用户任务到输出结果时，可以采用的几种典型思考方式。"""

    chatbot = "chatbot"
    cot = "cot"
    react = "react"
    decomposition = "decomposition"


# ===================== 第2步：定义单个模式的静态说明 =====================
@dataclass(slots=True)
class ThinkingModeInfo:
    """页面上展示的模式介绍，不依赖某一次具体任务。"""

    mode: ThinkingMode
    name: str
    summary: str
    best_for: str
    risk: str


# ===================== 第3步：定义单个模式针对任务生成的演示结果 =====================
@dataclass(slots=True)
class ThinkingModeDemo:
    """某个思维模式对同一个任务的处理过程。

    这里的 steps 是“可展示的推理摘要”，不是隐藏思维链。真实生产系统中，
    不应该把模型的完整隐藏推理过程直接暴露给用户。
    """

    mode: ThinkingMode
    name: str
    headline: str
    steps: list[str]
    tool_calls: list[str]
    final_answer: str


# ===================== 第4步：定义一次对比演示的整体结果 =====================
@dataclass(slots=True)
class ThinkingComparison:
    """同一个任务在多种模式下的对比结果。"""

    task: str
    demos: list[ThinkingModeDemo]

