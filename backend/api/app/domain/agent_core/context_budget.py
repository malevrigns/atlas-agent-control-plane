"""步骤历史上下文预算（Context Budget）——长任务分层遗忘。

背景：长任务（≥10 步）中，`StepExecutionRequest.step_history` 每步追加一条
完整格式条目（`- 步骤N《标题》状态（工具）：输出摘要`），逐层累积后全部进入
后续步骤的模型上下文 → token 爆炸 + 注意力稀释（任务偏离的直接原因）。

本模块提供**确定性**的三段分层压缩（纯函数，无副作用）：

- title-only：最老的步骤只留一行 ``步骤 N: 标题 → 状态``；
- digest：中间步骤压成 ``≤ older_steps_digest_chars`` 字符的截断摘要，
  带省略标记 ``…[digest N chars]``（N 为被省略的原始字符数）；
- full：最近 `recent_steps_full` 步保留全文。

为什么不用 LLM 压缩（刻意不用）：
1. **不可复现**：LLM 摘要带随机性，同一会话重放会产生不同上下文，
   压缩结果无法复现，调试与回归定位困难；
2. **审计困难**：压缩本身产生新的模型输出，审计链上多一环不可验证的
   变换，而截断/分层是纯机械规则，任何人可用同输入验证同输出；
3. **增加延迟与故障面**：每步组装 prompt 前多一次同步 LLM 调用，
   LLM 超时/报错会级联成步骤失败；纯函数压缩永不失败、零延迟。

压缩只发生在「喂给模型」的地方（`ReActStepExecutor` 渲染 agent context 时），
原始 `step_history`（审计与事件 payload）始终保持全文，两条线互不影响。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


# 与 react_step_executor.format_step_history 产出格式对应的解析正则：
#   无工具结果：`- 步骤N《标题》已完成。`
#   有工具结果：`- 步骤N《标题》已完成（工具名）：输出摘要`
_HISTORY_ENTRY_RE = re.compile(r"^\s*-\s*步骤\s*(\d+)\s*《(.*)》(.*)$", re.DOTALL)


def split_history_entry(entry: str) -> tuple[str, str]:
    """从 `format_step_history` 产出的条目里分出 (title, body)。

    条目格式（见 react_step_executor.format_step_history）：
    - 无工具结果：`- 步骤N《标题》已完成。`          → title=标题, body=""
    - 有工具结果：`- 步骤N《标题》已完成（工具）：摘要` → title=标题, body=摘要

    不匹配已知格式的条目返回 ("", 原文)：title 为空表示解析失败，
    调用方应退回 fallback 策略（如使用外部传入的 titles 或截断首行）。
    """
    match = _HISTORY_ENTRY_RE.match(entry)
    if match is None:
        return "", entry
    title = match.group(2).strip()
    rest = match.group(3).strip()
    # 全角冒号「：」是「（工具名）：摘要」的分隔符；无工具形态以「。」结尾、无全角冒号。
    separator = rest.find("：")
    if separator == -1:
        return title, ""
    return title, rest[separator + 1 :].strip()


def _status_of_entry(entry: str) -> str:
    """提取条目中 》与 （/：/。 之间的状态词（已完成 / ⚠️ 失败）。"""
    match = _HISTORY_ENTRY_RE.match(entry)
    if match is None:
        return ""
    rest = match.group(3).strip()
    for stop in ("（", "：", "。"):
        idx = rest.find(stop)
        if idx != -1:
            rest = rest[:idx]
    return rest.strip()


def _digest_line(entry: str, digest_chars: int) -> str:
    """digest 层：截取前 digest_chars 字符 + 省略标记 ``…[digest N chars]``。

    N 是被省略的原始字符数；条目本身不超长时原样保留（不添加多余标记）。
    """
    if len(entry) <= digest_chars:
        return entry
    omitted = len(entry) - digest_chars
    return f"{entry[:digest_chars]}…[digest {omitted} chars]"


def _title_only_line(entry: str, index: int, titles: tuple[str, ...] | None) -> str:
    """title-only 层：最老步骤只留 ``步骤 N: 标题 → 状态`` 一行。

    标题优先从条目本身解析；解析失败时按顺序使用外部传入的 titles；
    再失败则退化为条目首个非空行（截断到 40 字符），保证任何输入都有
    确定性输出。
    """
    title, _body = split_history_entry(entry)
    status = _status_of_entry(entry)
    if not title and titles is not None and index < len(titles):
        title = str(titles[index])
    if not title:
        first_line = next((line.strip() for line in entry.splitlines() if line.strip()), "未知")
        title = first_line[:40] + ("…" if len(first_line) > 40 else "")
    if not status:
        status = "未知"
    return f"步骤 {index + 1}: {title} → {status}"


@dataclass(frozen=True, slots=True)
class ContextBudgetConfig:
    """上下文预算配置（纯值对象，不可变）。

    - max_history_chars：步骤历史进入模型上下文的**总字符硬上限**
      （按换行拼接后的渲染长度估算，见 ContextBudget.estimate_chars）；
    - recent_steps_full：最近多少步保留全文（默认 2）；
    - older_steps_digest_chars：更早步骤压缩成的摘要上限（默认 400）；
    - oldest_steps_title_only：最老的步骤是否只留标题行（默认开启）。
    """

    max_history_chars: int = 24000
    recent_steps_full: int = 2
    older_steps_digest_chars: int = 400
    oldest_steps_title_only: bool = True

    def __post_init__(self) -> None:
        if self.max_history_chars <= 0:
            raise ValueError("max_history_chars must be positive")
        if self.recent_steps_full < 0:
            raise ValueError("recent_steps_full must be non-negative")
        if self.older_steps_digest_chars < 1:
            raise ValueError("older_steps_digest_chars must be positive")

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> ContextBudgetConfig:
        """从 app/core/config.py 的 context_budget_* 配置构造。

        传 settings 便于测试注入；缺省时惰性导入全局 settings
        （与 ToolBudget.from_settings 同一约定）。
        """
        if settings is None:
            from app.core.config import settings as default_settings

            settings = default_settings
        return cls(
            max_history_chars=settings.context_budget_max_history_chars,
            recent_steps_full=settings.context_budget_recent_steps_full,
            older_steps_digest_chars=settings.context_budget_digest_chars,
        )


class ContextBudget:
    """步骤历史分层压缩器（纯函数式，确定性：同输入恒同输出）。

    典型用法（ReActStepExecutor 渲染 agent context 前）::

        budget = ContextBudget.from_settings()
        compressed = budget.compress(request.step_history)
        prompt_history = "\\n".join(compressed)

    压缩只作用于**渲染给模型的副本**：调用方不得用返回值覆盖原始
    step_history，审计事件里的历史必须保持全文。
    """

    def __init__(self, config: ContextBudgetConfig | None = None) -> None:
        self.config = config or ContextBudgetConfig()

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> ContextBudget:
        """从 settings 构建（与 ToolBudget.from_settings 同一约定）。"""
        return cls(ContextBudgetConfig.from_settings(settings))

    # ===================== 分层压缩 =====================
    def compress(
        self,
        step_history: tuple[str, ...],
        titles: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        """按三段分层（title-only / digest / full）压缩步骤历史。

        规则（确定性，与输入顺序、内容之外的任何因素无关）：
        1. full 层：最后 `recent_steps_full` 条原样保留；
        2. title-only 层：当 `oldest_steps_title_only` 开启且 full 之外
           至少还有 2 条时，最老 1 条压成 ``步骤 N: 标题 → 状态`` 一行；
        3. digest 层：其余条目截断到 `older_steps_digest_chars` 字符，
           附省略标记 ``…[digest N chars]``（N=被省略的原始字符数）；
        4. 硬上限兜底：若拼接后仍超 `max_history_chars`，按固定顺序
           逐级收紧——先把更老的 digest 条目降为 title-only，再把 digest
           长度对折，最后把最老的 full 条目降为 digest——直至达标或
           已无可压缩层（极端小预算下最多保留每步一行标题）。

        titles 仅用于条目本身解析不出标题时的 fallback（与历史等长的
        步骤标题元组）；正常格式条目不依赖它。
        """
        history = tuple(str(item) for item in step_history)
        total = len(history)
        if total == 0:
            return ()

        cfg = self.config
        recent = min(max(cfg.recent_steps_full, 0), total)
        # full 层之外 ≥2 条时，最老 1 条走 title-only（三段分层的最小形态）。
        title_only = 1 if (cfg.oldest_steps_title_only and total - recent >= 2) else 0
        digest_chars = max(cfg.older_steps_digest_chars, 1)

        def render(title_only_: int, digest_chars_: int, recent_: int) -> tuple[str, ...]:
            out: list[str] = []
            for index, entry in enumerate(history):
                if index >= total - recent_:
                    out.append(entry)
                elif index < title_only_:
                    out.append(_title_only_line(entry, index, titles))
                else:
                    out.append(_digest_line(entry, digest_chars_))
            return tuple(out)

        result = render(title_only, digest_chars, recent)
        # 硬上限兜底：固定顺序的确定性强迫收敛（title_only 递增 / digest 对折 / recent 递减）。
        while self.estimate_chars(result) > cfg.max_history_chars:
            if title_only < total - recent:
                title_only += 1
            elif digest_chars > 1:
                digest_chars = max(1, digest_chars // 2)
            elif recent > 0:
                recent -= 1
            else:
                break
            result = render(title_only, digest_chars, recent)
        return result

    # ===================== 估算 =====================
    def estimate_chars(self, items: Iterable[str]) -> int:
        """估算 items 按换行拼接后的渲染字符数（与 prompt 组装方式一致）。

        即各条目长度之和 + 相邻条目间的换行分隔符（每条 1 字符）。
        """
        total = 0
        count = 0
        for item in items:
            if count > 0:
                total += 1
            total += len(str(item))
            count += 1
        return total
