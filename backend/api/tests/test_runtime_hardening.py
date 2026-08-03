import tempfile
import unittest
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.application.app_settings_service import AppSettingsService
from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.core.config import settings
from app.core.mcp_config import McpServerConfig
from app.core.module_policy import set_module_enabled
from app.domain.agent_core.tools import AgentTool, ToolDefinition, ToolRegistry, ToolInvocationStatus


class RuntimeHardeningTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_module_path = settings.module_config_path
        self.original_stdio_enabled = settings.mcp_stdio_enabled
        self.original_stdio_commands = list(settings.mcp_stdio_allowed_commands)
        self.original_http_hosts = list(settings.mcp_http_allowed_hosts)
        self.temporary = tempfile.TemporaryDirectory()
        settings.module_config_path = str(Path(self.temporary.name) / "modules.yaml")

    def tearDown(self) -> None:
        settings.module_config_path = self.original_module_path
        settings.mcp_stdio_enabled = self.original_stdio_enabled
        settings.mcp_stdio_allowed_commands = self.original_stdio_commands
        settings.mcp_http_allowed_hosts = self.original_http_hosts
        self.temporary.cleanup()

    async def test_disabled_module_is_enforced_by_tool_runtime(self) -> None:
        registry = ToolRegistry()
        registry.register(
            AgentTool(
                definition=ToolDefinition(name="mcp_call", description="test", parameters=[]),
                handler=lambda: "ran",
            )
        )
        set_module_enabled("mcp", False)

        result = await ToolRuntime(registry).execute(
            "mcp_call",
            {},
            ToolExecutionContext(),
        )

        self.assertEqual(result.status, ToolInvocationStatus.denied)
        self.assertIn("module is disabled", result.output)

    def test_stdio_and_http_mcp_require_operator_allowlists(self) -> None:
        settings.mcp_stdio_enabled = False
        with self.assertRaises(ValidationError):
            McpServerConfig(enabled=True, transport="stdio", command="python")

        settings.mcp_stdio_enabled = True
        settings.mcp_stdio_allowed_commands = ["/usr/bin/python -m trusted_server"]
        with self.assertRaises(ValidationError):
            McpServerConfig(
                enabled=True,
                transport="stdio",
                command="/tmp/python",
                args=["-m", "trusted_server"],
            )
        allowed_stdio = McpServerConfig(
            enabled=True,
            transport="stdio",
            command="/usr/bin/python",
            args=["-m", "trusted_server"],
        )
        self.assertEqual(allowed_stdio.command, "/usr/bin/python")

        settings.mcp_http_allowed_hosts = []
        with self.assertRaises(ValidationError):
            McpServerConfig(enabled=True, transport="streamable_http", url="http://127.0.0.1/mcp")
        settings.mcp_http_allowed_hosts = ["mcp.example.com"]
        allowed_http = McpServerConfig(
            enabled=True,
            transport="streamable_http",
            url="https://mcp.example.com/mcp",
        )
        self.assertEqual(allowed_http.url, "https://mcp.example.com/mcp")

    def test_llm_provider_saves_only_environment_reference(self) -> None:
        config_path = Path(self.temporary.name) / "llm.yaml"
        config_path.write_text(
            yaml.safe_dump({
                "llm": {"default_provider": "demo", "default_model": "m", "temperature": 0.2, "max_tokens": 100},
                "providers": {"demo": {"base_url": "https://example.com/v1", "api_key_env": "OLD_KEY", "timeout_seconds": 10}},
            }),
            encoding="utf-8",
        )
        original_path = settings.llm_config_path
        settings.llm_config_path = str(config_path)
        service = object.__new__(AppSettingsService)
        service._reload_services = lambda: None
        try:
            service.save_llm_provider("demo", "https://example.com/v1", "NEW_KEY")
        finally:
            settings.llm_config_path = original_path

        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["providers"]["demo"]["api_key_env"], "NEW_KEY")
        self.assertNotIn("api_key", saved["providers"]["demo"])


if __name__ == "__main__":
    unittest.main()
