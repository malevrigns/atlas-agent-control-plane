"""覆盖度评审（Coverage Review）领域模型。

任务完成的第三个门禁：不只是"测试通过"，还要"该测的都测了"。
在任务进入 summarize 之前，由 LLM 对照任务目标与验收标准，
判断改动文件与已有测试用例是否覆盖了任务要求。

分层约定：本模块是纯 domain 逻辑，不依赖数据库 / LLM 客户端实现。
LLM 调用与降级由应用层（CoverageReviewService）负责；
本模块只负责三件事：
- prompt 构造（build_review_prompt，只给清单不给测试全文，控制 token）；
- LLM 输出解析（parse_review，容错代码围栏，失败抛 ValueError）；
- adequate 判定的硬规则（decide_adequate，防模型互博）。

防互博设计：adequacy **不采信**模型自报的 ``"adequate"`` 字段，
一律按硬规则判定——存在 severity=high 的 gap 即 inadequate，
防止模型一边 gaps 里列出高危缺口、一边自报 "adequate": true。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ===================== 评审方标识与降级常量 =====================

# LLM 正常评审完成时的 reviewer 标识。
REVIEWER_LLM = "llm"
# LLM 不可用 / 输出解析失败时的 reviewer 标识（失败开放，不阻塞主链路）。
REVIEWER_SKIPPED = "skipped"
# 失败开放的统一 reason 文案：覆盖评审是增强项，评审失败视同"跳过"。
LLM_UNAVAILABLE_REASON = "llm unavailable"

# severity 合法取值（模型输出大小写不敏感，非法值归一为 medium——失败开放）。
_VALID_SEVERITIES: dict[str, str] = {"high": "high", "medium": "medium", "low": "low"}
# 提示词中要求模型最多列出的缺口数（按严重程度排序，防止输出爆炸）。
_MAX_GAPS_IN_PROMPT = 10

# ===================== prompt 长度预算（防上下文爆炸） =====================

# 单条输入（验收标准 / 文件路径 / 用例名）截断上限。
_MAX_ITEM_CHARS = 200
# 每个列表最多保留的条数（超出部分以"…及另外 N 项已省略"标注）。
_MAX_LIST_ITEMS = 40
# 任务目标截断上限。
_MAX_GOAL_CHARS = 1000
# gap 字段（area / suggestion）落库前的截断上限，防止单条 gap 撑爆审计事件。
_MAX_GAP_TEXT_CHARS = 300
_TRUNCATION_MARK = "…"

# ===================== 测试用例名抽取 =====================

# 匹配 def test_* 与 async def test_*（含类方法缩进），纯文本正则，不依赖 AST。
_TEST_FUNC_RE = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)


# ===================== 第1步：结果模型 =====================


@dataclass(slots=True)
class CoverageGap:
    """一条覆盖缺口（模型发现的未覆盖领域）。

    area：未覆盖的领域描述（如"超时路径"）；
    severity：high / medium / low；
    suggestion：补充测试的建议。
    """

    area: str
    severity: str
    suggestion: str


@dataclass(slots=True)
class CoverageReviewResult:
    """覆盖度评审结果。

    adequacy 判定规则（写死在 domain，不采信模型自报）：
    - 存在 severity=high 的 gap → adequate=False；
    - 仅 medium / low 的 gap（或无 gap）→ adequate=True，
      但 gaps 原样保留，写入审计事件供人查看。
    """

    adequate: bool
    gaps: list[CoverageGap]
    reviewer: str
    reason: str


# ===================== 第2步：adequacy 硬判定规则 =====================


def decide_adequate(gaps: list[CoverageGap]) -> bool:
    """硬 adequate 判定规则：存在 high gap 即 inadequate，否则 adequate。

    判定规则写死在代码里而不交给模型，防止模型
    "adequate=true + gaps 含 high" 互相矛盾地自洽（反互博）。
    """
    return not any(gap.severity == "high" for gap in gaps)


# ===================== 第3步：prompt 构造（长度可控） =====================


def _truncate(text: object, limit: int) -> str:
    """截断到 limit 字符（超长时保留前 limit-1 字符 + 省略号）。"""
    clean = str(text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + _TRUNCATION_MARK


def _numbered_items(items: list[str]) -> list[str]:
    """编号列表：单条截断 + 条数上限，超出部分以省略行标注。"""
    kept = items[:_MAX_LIST_ITEMS]
    lines = [
        f"{index}. {_truncate(item, _MAX_ITEM_CHARS)}"
        for index, item in enumerate(kept, start=1)
    ]
    omitted = len(items) - len(kept)
    if omitted > 0:
        lines.append(f"…及另外 {omitted} 项已省略")
    return lines


def _bullet_items(items: list[str]) -> list[str]:
    """无序列表：单条截断 + 条数上限，超出部分以省略行标注。"""
    kept = items[:_MAX_LIST_ITEMS]
    lines = [f"- {_truncate(item, _MAX_ITEM_CHARS)}" for item in kept]
    omitted = len(items) - len(kept)
    if omitted > 0:
        lines.append(f"…及另外 {omitted} 项已省略")
    return lines


def build_review_prompt(
    goal: str,
    acceptance_criteria: list[str],
    changed_files: list[str],
    test_files: list[str],
    test_case_names: list[str],
) -> str:
    """构造覆盖度评审 prompt：包含全部要素且总长度可控。

    输入为任务目标、验收标准清单、改动文件清单、测试文件清单与
    测试用例名清单（不含测试全文，控制 token）。
    单条输入截断到 _MAX_ITEM_CHARS，每个列表最多保留 _MAX_LIST_ITEMS 条，
    目标截断到 _MAX_GOAL_CHARS——超长输入下 prompt 总长度有界。
    """
    lines: list[str] = [
        "你是测试覆盖度评审员。请对照下面的任务目标、验收标准、改动文件与测试用例清单，",
        "判断现有测试用例是否完整覆盖了任务要求（包括正常路径、异常分支、边界条件与重要回归点）。",
        "",
        "## 任务目标",
        _truncate(goal, _MAX_GOAL_CHARS) or "（未提供）",
        "",
        "## 验收标准",
        *(_numbered_items(acceptance_criteria) or ["- （未提供）"]),
        "",
        "## 改动文件",
        *(_bullet_items(changed_files) or ["（无改动文件）"]),
        "",
        "## 测试文件",
        *(_bullet_items(test_files) or ["（无测试文件）"]),
        "",
        "## 测试用例名",
        *(_bullet_items(test_case_names) or ["（无测试用例）"]),
        "",
        "## 输出要求",
        "只输出一个 JSON 对象，不要输出任何其他文字，格式：",
        '{"adequate": bool, "gaps": [{"area": "未覆盖领域", '
        '"severity": "high|medium|low", "suggestion": "补充测试建议"}], '
        '"reason": "简要结论说明"}',
        f"gaps 只列明显覆盖缺口（最多 {_MAX_GAPS_IN_PROMPT} 条，按严重程度降序）；",
        "severity 只能取 high / medium / low 三值之一；无缺口时 gaps 为空数组。",
    ]
    return "\n".join(lines)


# ===================== 第4步：LLM 输出解析（容错围栏） =====================


def _strip_code_fences(text: str) -> str:
    """去掉 LLM 回复外围的 markdown 代码块围栏（```json / ``` 包裹）。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped


def _parse_gap(item: object) -> CoverageGap | None:
    """解析单条 gap；结构非法时跳过（防御性容错，不视为整体解析失败）。

    severity 大小写不敏感；未知 severity 归一为 medium（失败开放：
    不因模型笔误把本来 adequate 的评审变成 inadequate 触发重试）。
    """
    if not isinstance(item, dict):
        return None
    area = str(item.get("area") or "").strip()
    if not area:
        return None
    raw_severity = str(item.get("severity") or "").strip().lower()
    severity = _VALID_SEVERITIES.get(raw_severity, "medium")
    suggestion = str(item.get("suggestion") or "").strip()
    return CoverageGap(
        area=_truncate(area, _MAX_GAP_TEXT_CHARS),
        severity=severity,
        suggestion=_truncate(suggestion, _MAX_GAP_TEXT_CHARS),
    )


def parse_review(content: str) -> CoverageReviewResult:
    """解析 LLM 的覆盖度评审 JSON 输出。

    容错 markdown 代码围栏与前后多余文字（截取第一个 '{' 到最后一个 '}'
    之间的子串再解析）。解析失败抛 ValueError，由应用层捕获并降级
    （失败开放：评审是增强项，失败不得阻塞主链路）。

    模型自报的 "adequate" 字段不采信：adequacy 一律由
    decide_adequate 硬规则判定（存在 high gap → inadequate）。
    """
    cleaned = _strip_code_fences(content or "")
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("coverage review output does not contain a JSON object")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"coverage review output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("coverage review output JSON must be an object")

    raw_gaps = parsed.get("gaps")
    gaps: list[CoverageGap] = []
    if isinstance(raw_gaps, list):
        for item in raw_gaps:
            gap = _parse_gap(item)
            if gap is not None:
                gaps.append(gap)
    reason = str(parsed.get("reason") or "").strip()
    return CoverageReviewResult(
        adequate=decide_adequate(gaps),
        gaps=gaps,
        reviewer=REVIEWER_LLM,
        reason=reason,
    )


# ===================== 第5步：测试用例名收集（纯函数） =====================


def collect_test_case_names(test_files_content: dict[str, str]) -> dict[str, list[str]]:
    """从测试文件内容中抽取测试用例名（纯函数，正则实现，不依赖 AST）。

    抽取 ``def test_*`` 与 ``async def test_*`` 的函数名，
    按文件内首次出现顺序保留并去重；返回 {测试文件路径: [用例名, ...]}。
    """
    names: dict[str, list[str]] = {}
    for path, content in test_files_content.items():
        seen: set[str] = set()
        found: list[str] = []
        for match in _TEST_FUNC_RE.finditer(content or ""):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                found.append(name)
        names[path] = found
    return names
