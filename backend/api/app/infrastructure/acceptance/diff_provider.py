"""git diff 子进程实现（生产环境 DiffProvider）。

实现 application.scope_audit_service.DiffProvider 协议：
在 workspace_dir 里跑 `git diff --numstat HEAD` 与 `git diff HEAD --unified=2`，
两段输出拼接返回（numstat 在前，全量 diff 在后）。

Windows 兼容：使用 shell=False 的参数列表形式，不经过 shell 解析；
git 不存在 / 目录无效 / 超时 / 非零退出等任何异常都返回空 diff 并记录日志，
让范围审计降级为"无变更"（fail-open），不阻断任务。
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 单个 git 子进程调用的超时（秒）。
GIT_TIMEOUT_SECONDS = 30.0


class GitDiffProvider:
    """在 workspace_dir 里采集 git 变更（numstat + 全量 diff）。

    构造时可绑定默认工作区；diff() 也可临时传入 workspace_dir
    （状态机按执行上下文传入当前会话的工作区目录）。
    """

    def __init__(self, workspace_dir: str = "") -> None:
        self._workspace_dir = workspace_dir

    async def diff(self, workspace_dir: str = "") -> str:
        """返回 numstat + 全量 diff 拼接文本；workspace 缺失或 git 异常时返回空串。"""
        workdir = workspace_dir or self._workspace_dir
        if not workdir:
            return ""
        numstat = await self._run_git(workdir, ["diff", "--numstat", "HEAD"])
        full = await self._run_git(workdir, ["diff", "HEAD", "--unified=2"])
        parts = [part for part in (numstat, full) if part]
        if not parts:
            return ""
        return "\n".join(parts)

    async def _run_git(self, workdir: str, args: list[str]) -> str:
        """执行一次 git 子进程调用；任何异常都返回空串并记日志。"""
        command = " ".join(args)
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:
            logger.warning("启动 git %s 失败（cwd=%s）: %s", command, workdir, exc)
            return ""
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=GIT_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning("git %s 超时（%ss），返回空 diff: cwd=%s", command, GIT_TIMEOUT_SECONDS, workdir)
            return ""
        if process.returncode != 0:
            logger.warning("git %s 退出码 %s，返回空 diff: cwd=%s", command, process.returncode, workdir)
            return ""
        return stdout.decode("utf-8", errors="replace").rstrip("\n")
