"""工具调用预算控制（Budget）。

约束单个步骤内模型可使用的工具调用总量，三个维度：
- max_calls_per_step：单步骤工具调用总次数（默认 12）；
- max_calls_per_tool：同一工具的单步骤调用次数（默认 4）；
- max_token_estimate：工具输出累计估算 token 上限。

超预算时不抛异常，而是返回结构化的 budget_exceeded 结果
（JSON 输出 + audit 标记）回喂给模型，让模型自己决定如何收尾。

预算对象的生命周期是「单步骤」：每个 run_step 新建一个实例，
避免跨步骤泄漏额度。
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.domain.agent_core.tools import (
    ToolCallResult,
    ToolInvocationStatus,
    ToolRiskLevel,
)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：约 2 个字符折算 1 个 token（中英文混合的保守值）。"""

    if not text:
        return 0
    return max(1, math.ceil(len(text) / 2))


@dataclass(frozen=True, slots=True)
class BudgetCheckResult:
    """预算检查结果。

    allowed=False 时 reason 取值：
    step_call_limit / tool_call_limit / token_estimate_limit。
    """

    allowed: bool
    reason: str = ""
    detail: str = ""


@dataclass(slots=True)
class ToolBudget:
    """单步骤工具调用预算。

    典型用法（StepAgentLoop 执行入口）::

        budget = ToolBudget.from_settings()
        check = budget.check_call("search_web")
        if not check.allowed:
            result = budget.build_exceeded_result("search_web", check, arguments)
        else:
            result = await runtime.execute(...)
            budget.record_call("search_web", result.output)
    """

    max_calls_per_step: int = 12
    max_calls_per_tool: int = 4
    max_token_estimate: int = 100_000
    _calls_used: int = field(default=0, init=False)
    _calls_by_tool: dict[str, int] = field(default_factory=dict, init=False)
    _token_estimate_used: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.max_calls_per_step <= 0:
            raise ValueError("max_calls_per_step must be positive")
        if self.max_calls_per_tool <= 0:
            raise ValueError("max_calls_per_tool must be positive")
        if self.max_token_estimate <= 0:
            raise ValueError("max_token_estimate must be positive")

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> "ToolBudget":
        """从 app/core/config.py 的 tool_budget_* 配置构造预算。"""

        if settings is None:
            from app.core.config import settings as default_settings

            settings = default_settings
        return cls(
            max_calls_per_step=settings.tool_budget_max_calls_per_step,
            max_calls_per_tool=settings.tool_budget_max_calls_per_tool,
            max_token_estimate=settings.tool_budget_max_token_estimate,
        )

    # ===================== 查询 =====================
    @property
    def calls_used(self) -> int:
        return self._calls_used

    @property
    def token_estimate_used(self) -> int:
        return self._token_estimate_used

    def calls_used_for(self, tool_name: str) -> int:
        return self._calls_by_tool.get(tool_name, 0)

    def remaining_calls(self) -> int:
        return max(0, self.max_calls_per_step - self._calls_used)

    # ===================== 判定与记账 =====================
    def check_call(self, tool_name: str) -> BudgetCheckResult:
        """判断下一次调用是否仍在预算内（不计账，记账用 record_call）。"""

        if self._calls_used >= self.max_calls_per_step:
            return BudgetCheckResult(
                allowed=False,
                reason="step_call_limit",
                detail=f"本步骤工具调用次数已达上限 {self.max_calls_per_step}",
            )
        if self._calls_by_tool.get(tool_name, 0) >= self.max_calls_per_tool:
            return BudgetCheckResult(
                allowed=False,
                reason="tool_call_limit",
                detail=(
                    f"工具 {tool_name} 在本步骤已调用 {self.max_calls_per_tool} 次，达到单工具上限"
                ),
            )
        if self._token_estimate_used >= self.max_token_estimate:
            return BudgetCheckResult(
                allowed=False,
                reason="token_estimate_limit",
                detail=(
                    f"工具输出累计估算 token 已达上限 {self.max_token_estimate}"
                ),
            )
        return BudgetCheckResult(allowed=True)

    def record_call(self, tool_name: str, output: str = "") -> None:
        """记账一次已发生的调用（含失败调用，它们同样消耗模型轮次）。"""

        self._calls_used += 1
        self._calls_by_tool[tool_name] = self._calls_by_tool.get(tool_name, 0) + 1
        self._token_estimate_used += estimate_tokens(output)

    def to_audit(self) -> dict[str, Any]:
        """输出预算快照，可附加到步骤观察或事件审计。"""

        return {
            "calls_used": self._calls_used,
            "max_calls_per_step": self.max_calls_per_step,
            "calls_by_tool": dict(self._calls_by_tool),
            "max_calls_per_tool": self.max_calls_per_tool,
            "token_estimate_used": self._token_estimate_used,
            "max_token_estimate": self.max_token_estimate,
        }

    # ===================== 超预算的结构化结果 =====================
    def build_exceeded_result(
        self,
        tool_name: str,
        check: BudgetCheckResult,
        arguments: Mapping[str, Any],
    ) -> ToolCallResult:
        """构造结构化 budget_exceeded 结果（回喂给模型，不是异常）。

        输出为 JSON，模型可以解析 reason 并据此停止调用工具、直接收尾；
        状态用 failed 表达「本次调用没有执行」，audit 里保留 budget_exceeded 标记。
        """

        payload = {
            "budget_exceeded": True,
            "reason": check.reason,
            "detail": check.detail,
            "suggestion": "请停止调用工具，基于已获得的结果直接给出本步骤的结论。",
        }
        return ToolCallResult(
            tool_name=tool_name,
            arguments=dict(arguments),
            output=json.dumps(payload, ensure_ascii=False),
            status=ToolInvocationStatus.failed,
            risk_level=ToolRiskLevel.low,
            audit={
                "budget_exceeded": check.reason,
                "budget": self.to_audit(),
            },
        )
