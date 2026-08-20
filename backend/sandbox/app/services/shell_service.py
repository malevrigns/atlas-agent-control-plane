import asyncio
from asyncio.subprocess import PIPE, Process
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import SandboxException
from app.schemas.shell import (
    ShellSessionListResponse,
    ShellSessionResponse,
    ShellTerminateResponse,
    ShellWriteResponse,
)


@dataclass(slots=True)
class ShellSession:
    """保存一个沙箱命令进程的运行状态。"""

    id: str
    command: str
    cwd: str
    process: Process
    status: str = "running"
    return_code: int | None = None
    output_chunks: list[str] = field(default_factory=list)
    output_truncated: bool = False


class SandboxShellService:
    """管理沙箱里的 Shell 进程会话；工作目录限域在挂载根内。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mount_root = Path(settings.workspace_dir).resolve()
        self.mount_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ShellSession] = {}

    def _root(self, workspace: str, full_access: bool) -> Path:
        if full_access:
            return self.mount_root
        clean = workspace.strip().strip("/")
        if not clean:
            return self.mount_root
        target = (self.mount_root / clean).resolve()
        if target != self.mount_root and self.mount_root not in target.parents:
            raise SandboxException(message="workspace escapes mount root")
        target.mkdir(parents=True, exist_ok=True)
        return target

    # ===================== 第1步：启动命令 =====================
    async def execute(
        self,
        command: str,
        cwd: str = ".",
        workspace: str = "",
        full_access: bool = False,
    ) -> ShellSessionResponse:
        root = self._root(workspace, full_access)
        workdir = self._resolve_workdir(cwd, root)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=workdir,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
        )
        session = ShellSession(
            id=str(uuid4()),
            command=command,
            cwd=self._to_relative_path(workdir, root),
            process=process,
        )
        self._sessions[session.id] = session

        asyncio.create_task(self._collect_stream(session, process.stdout, "stdout"))
        asyncio.create_task(self._collect_stream(session, process.stderr, "stderr"))
        asyncio.create_task(self._watch_process(session))

        return self._to_response(session)

    # ===================== 第2步：查询会话 =====================
    def get(self, session_id: str) -> ShellSessionResponse:
        return self._to_response(self._get_session(session_id))

    def list_sessions(self) -> ShellSessionListResponse:
        return ShellSessionListResponse(
            items=[self._to_response(session) for session in self._sessions.values()]
        )

    # ===================== 第3步：等待进程完成 =====================
    async def wait(
        self,
        session_id: str,
        timeout_seconds: float | None = None,
    ) -> ShellSessionResponse:
        session = self._get_session(session_id)
        timeout = timeout_seconds or self.settings.shell_default_timeout_seconds
        try:
            await asyncio.wait_for(session.process.wait(), timeout=timeout)
        except TimeoutError:
            return self._to_response(session)
        return self._to_response(session)

    # ===================== 第4步：写入标准输入 =====================
    async def write(self, session_id: str, value: str) -> ShellWriteResponse:
        session = self._get_session(session_id)
        if session.status != "running" or session.process.stdin is None:
            raise SandboxException(message="shell session is not writable")

        encoded = value.encode("utf-8")
        session.process.stdin.write(encoded)
        await session.process.stdin.drain()
        return ShellWriteResponse(id=session.id, written=len(encoded))

    # ===================== 第5步：终止进程 =====================
    async def terminate(self, session_id: str) -> ShellTerminateResponse:
        session = self._get_session(session_id)
        if session.status == "running":
            session.process.terminate()
            session.status = "terminated"
            try:
                await asyncio.wait_for(session.process.wait(), timeout=2)
            except TimeoutError:
                session.process.kill()
                await session.process.wait()
        return ShellTerminateResponse(id=session.id, terminated=True)

    # ===================== 第6步：后台收集输出和状态 =====================
    async def _collect_stream(
        self,
        session: ShellSession,
        stream: asyncio.StreamReader | None,
        name: str,
    ) -> None:
        if stream is None:
            return

        while True:
            chunk = await stream.readline()
            if not chunk:
                break
            prefix = "" if name == "stdout" else "[stderr] "
            self._append_output(session, prefix + chunk.decode("utf-8", errors="replace"))

    async def _watch_process(self, session: ShellSession) -> None:
        return_code = await session.process.wait()
        session.return_code = return_code
        if session.status == "terminated":
            return
        session.status = "succeeded" if return_code == 0 else "failed"

    def _append_output(self, session: ShellSession, text: str) -> None:
        session.output_chunks.append(text)
        output = "".join(session.output_chunks)
        if len(output.encode("utf-8")) <= self.settings.shell_output_limit:
            return

        session.output_truncated = True
        truncated = output.encode("utf-8")[-self.settings.shell_output_limit :]
        session.output_chunks = [truncated.decode("utf-8", errors="replace")]

    # ===================== 第7步：路径和会话辅助方法 =====================
    @staticmethod
    def _resolve_workdir(cwd: str, root: Path) -> Path:
        clean_cwd = cwd.strip() or "."
        if Path(clean_cwd).is_absolute():
            raise SandboxException(message="absolute cwd is not allowed")

        target = (root / clean_cwd).resolve()
        if target != root and root not in target.parents:
            raise SandboxException(message="cwd escapes workspace")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _get_session(self, session_id: str) -> ShellSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SandboxException(
                message="shell session not found",
                code=404,
                status_code=404,
            )
        return session

    @staticmethod
    def _to_relative_path(path: Path, root: Path) -> str:
        relative = path.resolve().relative_to(root)
        return "." if str(relative) == "." else relative.as_posix()

    def _to_response(self, session: ShellSession) -> ShellSessionResponse:
        return ShellSessionResponse(
            id=session.id,
            command=session.command,
            cwd=session.cwd,
            status=session.status,
            return_code=session.return_code,
            output="".join(session.output_chunks),
            output_truncated=session.output_truncated,
        )
