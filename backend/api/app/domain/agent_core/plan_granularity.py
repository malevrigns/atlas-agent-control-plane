"""规划粒度治理（Plan Granularity）。

把「拆成几步」从写死的常量，变成按任务复杂度自适应的策略：
- light    2-4 步：短任务、无重度信号，避免为拆而拆；
- standard 4-8 步：中等长度或 1-2 个重度信号；
- heavy    10-15 步：长任务（>300 字符）、≥3 个重度信号、或同时提及测试与文件。

设计取舍（反互博 / 宽进严出）：
- 步骤数量是**参考区间而非硬验收**。heavy 的 10 步是"硬下限"，但绝不允许
  模型为凑数拆出没有独立验收意义的垃圾步骤——``quality_hints`` 会在生成
  prompt 里明确提示："拆不出有意义的步骤就合并相近步骤后再输出"。
- ``clamp_steps`` 宽进严出：超出上限才截断并给出警告；低于下限**不强行
  扩充**（强扩只会产生填充步骤、并与 critic 的评审互相拉扯），而是返回
  原列表 + 一条"粒度不足"警告，交给评审环节（T6 critic）判断。
- 所有警告只写入 plan_created 事件 payload 的 ``granularity`` 字段作为
  审计信息，**不阻断执行**。
"""

from __future__ import annotations
from dataclasses import dataclass, field

from app.domain.agent_core.planner import PlanStep

# ===================== 第1步：复杂度信号 =====================

# 重度关键词：出现即代表任务带有"工程化 / 多阶段"特征。
# 命中数由 ``assess`` 统计，≥3 个直接判 heavy。
_HEAVY_KEYWORDS: tuple[str, ...] = (
    "实现",
    "重构",
    "迁移",
    "部署",
    "全链路",
    "端到端",
    "end to end",
    "e2e",
)

# 提及"测试"的关键词。
_TEST_KEYWORDS: tuple[str, ...] = ("测试", "test", "单测", "集成测试")

# 提及"文件"的关键词。
_FILE_KEYWORDS: tuple[str, ...] = ("文件", "路径", "file", "path")

# 多组件关键词：任务里同时点名的组件越多，越可能是跨模块的大任务。
# 命中 ≥2 个视为 mentions_multi_component。
_COMPONENT_KEYWORDS: tuple[str, ...] = (
    "前端",
    "后端",
    "数据库",
    "接口",
    "服务",
    "模块",
    "组件",
    "缓存",
    "队列",
    "api",
)


@dataclass(slots=True)
class ComplexitySignals:
    """从任务文本中提取的复杂度信号，``assess`` 的判定输入。

    - ``keyword_hits``：命中 ``_HEAVY_KEYWORDS`` 的个数；
    - ``task_char_len``：任务正文字符长度；
    - ``mentions_tests``：是否提及测试；
    - ``mentions_files``：是否提及文件/路径；
    - ``mentions_multi_component``：是否并列提及 ≥2 个组件。
    """

    keyword_hits: int = 0
    task_char_len: int = 0
    mentions_tests: bool = False
    mentions_files: bool = False
    mentions_multi_component: bool = False


# ===================== 第2步：粒度策略 =====================

# 各级别的默认步数区间（min, max）。
_STEP_RANGES: dict[str, tuple[int, int]] = {
    "light": (2, 4),
    "standard": (4, 8),
    "heavy": (10, 15),
}

# 各级别附带给模型的质量提示，用于 prompt 生成，防止"为凑数拆垃圾步骤"。
_QUALITY_HINTS: dict[str, tuple[str, ...]] = {
    "light": (
        "任务较轻，不要强行拆分；能 1-2 步完成的就按实际输出，禁止造填充步骤。",
    ),
    "standard": (
        "合并目的相近的相邻步骤，不要把纯机械操作拆成独立步骤。",
        "步骤数量是参考区间而非硬验收：拆不出有独立验收意义的步骤时，宁可少写并合并。",
    ),
    "heavy": (
        "长任务优先拆到 10-15 步，每步 expected_output 必须可独立验证。",
        "如果无法拆出有独立验收意义的步骤，说明任务应降级，请合并相近步骤后再输出，"
        "禁止为凑够步数制造填充步骤。",
    ),
}

# 各级别写进 prompt 的一句分级说明。
_COMPLEXITY_NOTES: dict[str, str] = {
    "light": "本任务被评估为轻任务，拆得太细反而引入无意义步骤。",
    "standard": "本任务被评估为中等任务，按可独立验证的粒度拆分。",
    "heavy": "本任务被评估为重量级任务，需要足够细的步骤以控制上下文与偏离风险。",
}


@dataclass(slots=True)
class GranularityPolicy:
    """一次规划的粒度策略：步数区间 + 复杂度级别 + 质量提示。"""

    min_steps: int
    max_steps: int
    complexity: str
    # 附给模型的防凑数提示（随级别变化），生成 prompt 时逐条列出。
    quality_hints: list[str] = field(default_factory=list)

    @staticmethod
    def assess(
        task: str,
        *,
        signals: ComplexitySignals | None = None,
    ) -> "GranularityPolicy":  # 类体内引用自身需引号包裹，避免类定义期 NameError
        """按任务复杂度给出粒度策略。

        分级规则（写死、可解释）：
        1. **heavy**：任务长度 >300 字符，或 ``keyword_hits`` ≥3，
           或同时 ``mentions_tests`` 且 ``mentions_files``。
        2. **light**：任务长度 <80 字符，且**无任何**重度信号
           （keyword_hits==0 且未提及测试/文件/多组件）。
        3. **standard**：其余情况（中等长度，或 1-2 个重度信号）。

        heavy 的 10 步是"硬下限"（长任务必须拆够），但通过
        ``quality_hints`` 禁止模型为凑数拆垃圾步骤：拆不出有独立验收
        意义的步骤时，应合并相近步骤后输出。
        """

        clean_task = task.strip()
        if signals is None:
            signals = ComplexitySignals(
                keyword_hits=sum(1 for kw in _HEAVY_KEYWORDS if kw in clean_task.lower()),
                task_char_len=len(clean_task),
                mentions_tests=any(kw in clean_task.lower() for kw in _TEST_KEYWORDS),
                mentions_files=any(kw in clean_task.lower() for kw in _FILE_KEYWORDS),
                mentions_multi_component=(
                    sum(1 for kw in _COMPONENT_KEYWORDS if kw in clean_task.lower()) >= 2
                ),
            )

        has_heavy_signal = (
            signals.keyword_hits > 0
            or signals.mentions_tests
            or signals.mentions_files
            or signals.mentions_multi_component
        )

        if (
            signals.task_char_len > 300
            or signals.keyword_hits >= 3
            or (signals.mentions_tests and signals.mentions_files)
        ):
            complexity = "heavy"
        elif signals.task_char_len < 80 and not has_heavy_signal:
            complexity = "light"
        else:
            complexity = "standard"

        min_steps, max_steps = _STEP_RANGES[complexity]
        return GranularityPolicy(
            min_steps=min_steps,
            max_steps=max_steps,
            complexity=complexity,
            quality_hints=list(_QUALITY_HINTS[complexity]),
        )


# ===================== 第3步：步骤数治理（宽进严出） =====================

def clamp_steps(
    steps: list[PlanStep],
    policy: GranularityPolicy,
) -> tuple[list[PlanStep], list[str]]:
    """按策略治理步骤数，返回 (步骤列表, 警告列表)。

    宽进严出原则：
    - 超出 ``max_steps``：截断到上限，并返回警告（审计用，不阻断执行）；
    - 低于 ``min_steps``：**不强行扩充**（强扩只会产生填充步骤、与 critic
      互博），返回原列表 + 一条"粒度不足"警告，留给评审环节判断；
    - 区间内：原样返回，无警告。
    """

    warnings: list[str] = []

    if len(steps) > policy.max_steps:
        warnings.append(
            f"规划步骤数 {len(steps)} 超过上限 {policy.max_steps}"
            f"（complexity={policy.complexity}），已截断为前 {policy.max_steps} 步，"
            "请合并步骤后重新规划。"
        )
        return steps[: policy.max_steps], warnings

    if len(steps) < policy.min_steps:
        warnings.append(
            f"规划步骤数 {len(steps)} 低于下限 {policy.min_steps}"
            f"（complexity={policy.complexity}），未强行扩充；"
            "评审时将判断粒度是否不足。"
        )
        return list(steps), warnings

    return list(steps), warnings
