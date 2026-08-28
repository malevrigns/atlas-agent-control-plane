"""验收门禁（Acceptance Gate）领域模型。

在任务进入总结（summarize）之前，通过执行一条验收命令做"完成"的客观验证：
只有命令退出码命中 success_exit_codes 才算真正完成。

分层约定：本模块是纯 domain 逻辑，不依赖数据库/子进程实现。
命令的实际执行通过 ``CommandRunner`` Protocol 注入，
生产环境注入子进程 runner，测试注入假 runner。
"""

from dataclasses import dataclass
from typing import Protocol

# 输出摘要的最大长度（字符），超过则截断
OUTPUT_DIGEST_LIMIT = 2000
# 截断时附加的标记（计入 OUTPUT_DIGEST_LIMIT 预算内）
_DIGEST_TRUNCATION_MARK = "...(已截断)"


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """一次验收命令的执行结果。

    exit_code 为 None 表示命令根本没能执行（超时、命令不存在、运行异常等），
    此时 error 字段说明原因。
    """

    exit_code: int | None
    output: str = ""
    error: str | None = None
    duration_ms: int = 0


class CommandRunner(Protocol):
    """命令执行协议：测试可注入假实现，避免真实子进程。"""

    async def run(
        self, command: str, timeout_seconds: int, working_dir: str
    ) -> CommandOutcome: ...


@dataclass(frozen=True, slots=True)
class AcceptanceGateConfig:
    """验收门禁配置（通常来自 plan payload 的 acceptance 字段）。"""

    command: str
    timeout_seconds: int = 600
    success_exit_codes: tuple[int, ...] = (0,)
    working_dir: str = ""


@dataclass(frozen=True, slots=True)
class AcceptanceGateResult:
    """验收门禁的判定结果。

    退出码语义是硬约束：
    - 0（或命中 success_exit_codes）→ passed=True
    - 非 0 → passed=False
    - 命令不存在/超时 → exit_code=None，passed=False，reason 说明原因
    """

    passed: bool
    exit_code: int | None
    command: str
    output_digest: str
    duration_ms: int
    reason: str


class AcceptanceGateProtocol(Protocol):
    """状态机注入用的门禁协议：只暴露 verify。"""

    async def verify(self, config: AcceptanceGateConfig) -> AcceptanceGateResult: ...


class AcceptanceGate:
    """验收门禁：执行验收命令并按退出码判定通过与否。

    纯 domain 逻辑：命令执行委托给注入的 CommandRunner。
    """

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    async def verify(self, config: AcceptanceGateConfig) -> AcceptanceGateResult:
        """执行验收命令并返回判定结果；任何执行异常都归为不通过。"""
        if not config.command.strip():
            return AcceptanceGateResult(
                passed=False,
                exit_code=None,
                command=config.command,
                output_digest="",
                duration_ms=0,
                reason="验收命令为空，无法执行门禁",
            )
        try:
            outcome = await self._runner.run(
                config.command, config.timeout_seconds, config.working_dir
            )
        except Exception as exc:  # runner 自身异常（如命令不存在）→ 无法执行
            return AcceptanceGateResult(
                passed=False,
                exit_code=None,
                command=config.command,
                output_digest="",
                duration_ms=0,
                reason=f"验收命令无法执行：{exc}",
            )
        digest = self._digest(outcome.output)
        if outcome.exit_code is None:
            reason = outcome.error or "验收命令无法执行"
            return AcceptanceGateResult(
                passed=False,
                exit_code=None,
                command=config.command,
                output_digest=digest,
                duration_ms=outcome.duration_ms,
                reason=reason,
            )
        if outcome.exit_code in config.success_exit_codes:
            return AcceptanceGateResult(
                passed=True,
                exit_code=outcome.exit_code,
                command=config.command,
                output_digest=digest,
                duration_ms=outcome.duration_ms,
                reason=f"exit_code={outcome.exit_code} 命中 success_exit_codes",
            )
        return AcceptanceGateResult(
            passed=False,
            exit_code=outcome.exit_code,
            command=config.command,
            output_digest=digest,
            duration_ms=outcome.duration_ms,
            reason=(
                f"exit_code={outcome.exit_code} "
                f"不在 success_exit_codes={list(config.success_exit_codes)} 中"
            ),
        )

    @staticmethod
    def _digest(output: str) -> str:
        """生成输出摘要：总长度不超过 OUTPUT_DIGEST_LIMIT 字符。"""
        text = (output or "").strip()
        if len(text) <= OUTPUT_DIGEST_LIMIT:
            return text
        keep = OUTPUT_DIGEST_LIMIT - len(_DIGEST_TRUNCATION_MARK)
        return text[:keep] + _DIGEST_TRUNCATION_MARK
