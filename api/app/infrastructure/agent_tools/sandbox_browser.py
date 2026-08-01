import json

from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)
from app.infrastructure.sandbox.browser_client import SandboxBrowserClient


def build_sandbox_browser_client() -> SandboxBrowserClient:
    """根据主 API 配置创建 Sandbox Browser 客户端。"""

    return SandboxBrowserClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )


def register_sandbox_browser_tools(
    registry: ToolRegistry,
    client: SandboxBrowserClient | None = None,
) -> None:
    """把 Sandbox 浏览器能力注册成 Agent 可调用工具。

    这些工具不直接控制本机浏览器，而是转发到 Sandbox Browser API。
    """

    browser_client = client or build_sandbox_browser_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_status",
                description="查看 Sandbox 浏览器会话状态、当前页面和视口信息。",
                required_permissions=("browser:read",),
                parameters=[],
            ),
            handler=lambda: _format_status(browser_client.status()),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_open",
                description="在 Sandbox 浏览器中打开一个网页，并返回页面地址和标题。",
                risk_level=ToolRiskLevel.medium,
                required_permissions=("network:access", "browser:navigate"),
                parameters=[
                    ToolParameter(
                        name="url",
                        type="string",
                        description="要打开的网页地址，例如 https://example.com。",
                    )
                ],
            ),
            handler=lambda url: _format_page(browser_client.navigate(url=url)),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_screenshot",
                description="截取当前浏览器页面，返回图片信息和 base64 数据。",
                required_permissions=("browser:read",),
                parameters=[
                    ToolParameter(
                        name="full_page",
                        type="boolean",
                        description="是否截取完整页面，默认 true。",
                        required=False,
                    )
                ],
            ),
            handler=lambda full_page=True: _format_screenshot(
                browser_client.screenshot(full_page=_to_bool(full_page))
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_close",
                description="关闭 Sandbox 浏览器会话，释放浏览器资源。",
                risk_level=ToolRiskLevel.medium,
                required_permissions=("browser:control",),
                idempotent=False,
                parameters=[],
            ),
            handler=lambda: _format_session(browser_client.close()),
        )
    )


def _format_status(data: dict) -> str:
    return "\n".join(
        [
            f"浏览器启用：{data.get('enabled')}",
            f"会话已启动：{data.get('session_started')}",
            f"当前地址：{data.get('current_url') or '-'}",
            f"页面标题：{data.get('page_title') or '-'}",
            f"视口：{data.get('viewport_width')}x{data.get('viewport_height')}",
        ]
    )


def _format_page(data: dict) -> str:
    return "\n".join(
        [
            f"页面已打开：{data.get('url')}",
            f"页面标题：{data.get('title') or '-'}",
        ]
    )


def _format_screenshot(data: dict) -> str:
    # 截图结果使用 JSON，前端事件面板可以解析后直接显示图片。
    return json.dumps(
        {
            "kind": "browser_screenshot",
            "mime_type": data.get("mime_type"),
            "base64_data": data.get("base64_data"),
            "size": data.get("size"),
        },
        ensure_ascii=False,
    )


def _format_session(data: dict) -> str:
    return f"{data.get('message')} status={data.get('status')}"


def _to_bool(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"false", "0", "no"}
    return bool(value)
