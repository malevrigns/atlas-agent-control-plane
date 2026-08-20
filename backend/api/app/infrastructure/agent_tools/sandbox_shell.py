from app.application.tool_runtime_support import current_workspace
from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)
from app.infrastructure.sandbox.shell_client import SandboxShellClient


def build_sandbox_shell_client() -> SandboxShellClient:
    """根据主 API 配置创建 Sandbox Shell 客户端。"""

    return SandboxShellClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )


def register_sandbox_shell_tools(
    registry: ToolRegistry,
    client: SandboxShellClient | None = None,
) -> None:
    """把 Sandbox Shell 能力注册成 Agent 可调用工具。"""

    shell_client = client or build_sandbox_shell_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="shell_run",
                description="在 Sandbox 工作目录中执行一条 Shell 命令，并等待输出。",
                risk_level=ToolRiskLevel.high,
                required_permissions=("shell:execute",),
                idempotent=False,
                timeout_seconds=settings.sandbox_api_timeout_seconds,
                parameters=[
                    ToolParameter(
                        name="command",
                        type="string",
                        description="要执行的 Shell 命令。",
                    )
                ],
            ),
            handler=lambda command: _format_shell_result(
                _run_and_wait(shell_client, command)
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="shell_status",
                description="查询一个 Sandbox Shell 会话的当前状态和输出。",
                risk_level=ToolRiskLevel.low,
                required_permissions=("shell:read",),
                parameters=[
                    ToolParameter(
                        name="session_id",
                        type="string",
                        description="Shell 会话 ID。",
                    )
                ],
            ),
            handler=lambda session_id: _format_shell_result(shell_client.get(session_id)),
        )
    )


def _run_and_wait(client: SandboxShellClient, command: str) -> dict:
    workspace, full_access = current_workspace()
    started = client.execute(
        command=command, cwd=".", workspace=workspace, full_access=full_access
    )
    return client.wait(
        session_id=str(started["id"]),
        timeout_seconds=settings.sandbox_shell_wait_timeout_seconds,
    )


def _format_shell_result(data: dict) -> str:
    output = str(data.get("output") or "").strip()
    if not output:
        output = "<no output>"

    suffix = "\n\n输出已截断。" if data.get("output_truncated") else ""
    return "\n".join(
        [
            f"会话：{data.get('id')}",
            f"命令：{data.get('command')}",
            f"目录：{data.get('cwd')}",
            f"状态：{data.get('status')}",
            f"退出码：{data.get('return_code')}",
            "",
            output + suffix,
        ]
    )
