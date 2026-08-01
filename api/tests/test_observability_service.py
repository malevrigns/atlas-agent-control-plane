import unittest

from app.application.observability_service import ObservabilityService


class ObservabilityServiceTest(unittest.TestCase):
    # ===================== 第1步：诊断清单应覆盖核心 Agent 子系统 =====================
    def test_checks_cover_core_agent_subsystems(self) -> None:
        service = ObservabilityService()

        checks = service.list_checks()
        keys = {check.key for check in checks}

        self.assertIn("api_status", keys)
        self.assertIn("database_status", keys)
        self.assertIn("sandbox_status", keys)
        self.assertIn("harness_cases", keys)
        self.assertIn("mcp_tools", keys)
        self.assertIn("a2a_agents", keys)

    # ===================== 第2步：每条诊断项都应包含可执行命令和预期结果 =====================
    def test_every_check_has_command_and_expected_result(self) -> None:
        service = ObservabilityService()

        for check in service.list_checks():
            self.assertTrue(check.command)
            self.assertTrue(check.expected)
            self.assertTrue(check.description)


if __name__ == "__main__":
    unittest.main()
