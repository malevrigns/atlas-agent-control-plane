"""验收命令的子进程执行器（生产环境 CommandRunner 实现）。

domain 层的 ``AcceptanceGate`` 通过 ``CommandRunner`` Protocol 解耦命令执行；
这里是生产实现：``asyncio.create_subprocess_shell`` 跑命令，超时杀进程，
stdout/stderr 合并截断为摘要。测试注入假 runner，不走这里。
"""

import asyncio
from datetime import UTC, datetime

from app.domain.acceptance.gate import CommandOutcome

# 输出摘要上限：与 domain 层 OUTPUT_DIGEST_LIMIT 对齐，这里先做粗截断。
_RAW_OUTPUT_LIMIT = 8000


class SubprocessCommandRunner:
    """用子进程执行验收命令，返回带退出码语义的 CommandOutcome。"""

    async def run(
        self, command: str, timeout_seconds: int, working_dir: str
    ) -> CommandOutcome:
        started_at = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=working_dir or None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as exc:
            # 命令不存在 / cwd 无效等：归为"未执行"，由门禁判不通过。
            return CommandOutcome(
                exit_code=None,
                output="",
                error=f"failed to spawn command: {exc}",
                duration_ms=0,
            )
        try:
            raw, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            # Windows Proactor 下 kill 后管道析构会报 ResourceWarning，显式等待回收。
            try:
                await process.wait()
            except Exception:  # noqa: BLE001 —— 回收失败不影响结果。
                pass
            return CommandOutcome(
                exit_code=None,
                output="",
                error=f"command timed out after {timeout_seconds}s",
                duration_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            )
        output = raw.decode("utf-8", errors="replace")[:_RAW_OUTPUT_LIMIT]
        return CommandOutcome(
            exit_code=process.returncode,
            output=output,
            error=None,
            duration_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
        )
