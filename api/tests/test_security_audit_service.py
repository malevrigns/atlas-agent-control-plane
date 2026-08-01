import unittest
from types import SimpleNamespace

from app.application.security_audit_service import SecurityAuditService


class SecurityAuditServiceTest(unittest.TestCase):
    # ===================== 第1步：安全清单应覆盖 Agent 系统的主要边界 =====================
    def test_checks_cover_security_boundaries(self) -> None:
        settings = SimpleNamespace(
            api_env="development",
            cors_allow_origins=["http://localhost:8088"],
            database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/atlas_agents",
            upload_dir="uploads",
            max_upload_size=10 * 1024 * 1024,
            max_file_preview_size=64 * 1024,
            sandbox_api_base_url="http://sandbox:8100/api",
            sandbox_api_timeout_seconds=30.0,
            sandbox_shell_wait_timeout_seconds=10.0,
            search_timeout_seconds=10.0,
            bing_search_api_key="",
            context_memory_limit=6,
            context_memory_candidate_limit=100,
        )
        service = SecurityAuditService(settings=settings)

        checks = service.list_checks()
        categories = {check.category for check in checks}

        self.assertIn("configuration", categories)
        self.assertIn("uploads", categories)
        self.assertIn("sandbox", categories)
        self.assertIn("integrations", categories)
        self.assertIn("memory", categories)

    # ===================== 第2步：每条安全检查都要说明风险、建议和验证命令 =====================
    def test_every_check_explains_risk_recommendation_and_verification(self) -> None:
        settings = SimpleNamespace(
            api_env="production",
            cors_allow_origins=["*"],
            database_url="postgresql+asyncpg://postgres:postgres@postgres:5432/atlas_agents",
            upload_dir="/tmp/atlas-uploads",
            max_upload_size=10 * 1024 * 1024,
            max_file_preview_size=64 * 1024,
            sandbox_api_base_url="http://sandbox:8100/api",
            sandbox_api_timeout_seconds=30.0,
            sandbox_shell_wait_timeout_seconds=10.0,
            search_timeout_seconds=10.0,
            bing_search_api_key="",
            context_memory_limit=6,
            context_memory_candidate_limit=100,
        )
        service = SecurityAuditService(settings=settings)

        for check in service.list_checks():
            self.assertTrue(check.risk)
            self.assertTrue(check.recommendation)
            self.assertTrue(check.verify_command)
            self.assertIn(check.severity, {"info", "warning", "risk"})

    # ===================== 第3步：生产环境默认密码和通配 CORS 应被标记为高风险 =====================
    def test_production_defaults_are_reported_as_risks(self) -> None:
        settings = SimpleNamespace(
            api_env="production",
            cors_allow_origins=["*"],
            database_url="postgresql+asyncpg://postgres:postgres@postgres:5432/atlas_agents",
            upload_dir="uploads",
            max_upload_size=10 * 1024 * 1024,
            max_file_preview_size=64 * 1024,
            sandbox_api_base_url="http://sandbox:8100/api",
            sandbox_api_timeout_seconds=30.0,
            sandbox_shell_wait_timeout_seconds=10.0,
            search_timeout_seconds=10.0,
            bing_search_api_key="",
            context_memory_limit=6,
            context_memory_candidate_limit=100,
        )
        service = SecurityAuditService(settings=settings)

        risk_keys = {
            check.key for check in service.list_checks() if check.severity == "risk"
        }

        self.assertIn("cors_origin_policy", risk_keys)
        self.assertIn("database_default_password", risk_keys)


if __name__ == "__main__":
    unittest.main()
