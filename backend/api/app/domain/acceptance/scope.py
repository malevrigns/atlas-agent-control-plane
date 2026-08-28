"""范围审计领域逻辑：校验模型改动是否越出计划声明的文件范围。

纯领域模块：不执行任何 shell 命令，不依赖任何基础设施；
git diff 文本（--numstat + 全量 diff）由应用层注入。
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Mapping

# numstat 单行形态：<additions>\t<deletions>\t<path>
# additions/deletions 为非负整数或 "-"（二进制文件无法统计行数）。
_NUMSTAT_LINE_RE = re.compile(r"^(?P<additions>-|\d+)\t(?P<deletions>-|\d+)\t(?P<path>.+)$")

# 花括号式重命名：prefix{old/seg => new/seg}suffix
_RENAME_BRACE_RE = re.compile(
    r"^(?P<prefix>.*?)(?:\{(?P<old>[^}]*) => (?P<new>[^}]*)\})(?P<suffix>.*)$"
)


@dataclass(slots=True)
class FileChange:
    """单个文件变更（解析自 git diff --numstat）。"""

    path: str
    change_type: str  # added / modified / deleted
    additions: int
    deletions: int

    @property
    def total_lines(self) -> int:
        """变更总行数（新增 + 删除），用于体积异常判定。"""
        return self.additions + self.deletions


@dataclass(slots=True)
class ScopeAuditResult:
    """范围审计结果。

    reviewer 取值："rules"（仅规则层）/ "rules+llm"（规则层 + LLM 复核）/
    "llm"（预留；当前两级审计中规则层必跑，实际只会产出前两者）。
    """

    in_scope: bool
    violations: list[FileChange] = field(default_factory=list)
    checked_files: int = 0
    reviewer: str = "rules"
    reason: str = ""


class ScopePolicy:
    """文件改动范围策略：allowed / forbidden 两组 fnmatch 风格 glob。

    判定规则：
    - forbidden 优先级高于 allowed：命中 forbidden 即违规；
    - 否则，未命中任何 allowed glob 的变更视为违规。

    说明：fnmatch 中 `*` 会跨越目录分隔符，因此 `backend/api/**`
    可匹配其下任意深度的文件。
    """

    def __init__(
        self,
        allowed_globs: list[str],
        forbidden_globs: list[str] | None = None,
    ) -> None:
        self.allowed_globs = list(allowed_globs)
        self.forbidden_globs = list(forbidden_globs or [])

    @classmethod
    def from_plan(cls, plan: Mapping[str, object]) -> "ScopePolicy | None":
        """从 plan payload 的 scope 字段构造策略；无 scope 字段时返回 None（跳过审计）。

        scope 示例：
        {"allowed": ["backend/api/**", "docs/**"],
         "forbidden": ["**/.env*", "docker-compose.yml"],
         "llm_review": true}
        """
        scope = plan.get("scope")
        if not isinstance(scope, Mapping):
            return None
        allowed_raw = scope.get("allowed")
        if not isinstance(allowed_raw, (list, tuple)):
            return None
        allowed = [item for item in allowed_raw if isinstance(item, str) and item]
        if not allowed:
            return None
        forbidden: list[str] = []
        forbidden_raw = scope.get("forbidden")
        if isinstance(forbidden_raw, (list, tuple)):
            forbidden = [item for item in forbidden_raw if isinstance(item, str) and item]
        return cls(allowed, forbidden)

    def check(self, changes: list[FileChange]) -> list[FileChange]:
        """返回违规变更列表（未命中任何 allowed，或命中 forbidden）。"""
        violations: list[FileChange] = []
        for change in changes:
            if self.is_forbidden(change.path):
                violations.append(change)
            elif not self.is_allowed(change.path):
                violations.append(change)
        return violations

    def is_allowed(self, path: str) -> bool:
        """path 是否命中任意 allowed glob。"""
        return any(fnmatch.fnmatchcase(path, glob) for glob in self.allowed_globs)

    def is_forbidden(self, path: str) -> bool:
        """path 是否命中任意 forbidden glob。"""
        return any(fnmatch.fnmatchcase(path, glob) for glob in self.forbidden_globs)


def _resolve_rename(path: str) -> str:
    """解析 numstat 重命名写法，统一取新路径。

    git 的两种重命名输出：
    - `old/path.py => new/path.py`
    - `src/{old.py => new.py}`（公共前缀/后缀保留在花括号外）
    """
    brace = _RENAME_BRACE_RE.match(path)
    if brace is not None:
        return brace["prefix"] + brace["new"] + brace["suffix"]
    if " => " in path:
        return path.rsplit(" => ", 1)[1]
    return path


def _change_type(additions: int, deletions: int) -> str:
    """由新增/删除行数推断变更类型。

    二进制文件（两列均为 `-`）无法区分增删，统一记为 modified（0/0）。
    """
    if additions > 0 and deletions == 0:
        return "added"
    if additions == 0 and deletions > 0:
        return "deleted"
    return "modified"


def _parse_count(raw: str) -> int:
    """解析 numstat 行数列：'-'（二进制）记为 0。"""
    return 0 if raw == "-" else int(raw)


def collect_changes(diff_text: str) -> list[FileChange]:
    """解析 git diff --numstat 输出为 FileChange 列表。

    支持：标准数字行、二进制行（`-\\t-\\t`）、重命名行（`old => new`
    与 `prefix{old => new}suffix`）。遇到 `diff --git` 标记即停止解析，
    因此 numstat 段后拼接全量 diff 也是安全的。
    """
    changes: list[FileChange] = []
    for raw_line in diff_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("diff --git"):
            break
        match = _NUMSTAT_LINE_RE.match(line)
        if match is None:
            continue
        path = _resolve_rename(match["path"])
        additions = _parse_count(match["additions"])
        deletions = _parse_count(match["deletions"])
        changes.append(
            FileChange(
                path=path,
                change_type=_change_type(additions, deletions),
                additions=additions,
                deletions=deletions,
            )
        )
    return changes
