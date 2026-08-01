from app.core.config import Settings, settings
from app.domain.security.entities import SecurityCheck


class SecurityAuditService:
    """生成 API、Sandbox、上传、记忆和外部集成的安全边界清单。

    这个服务不负责“自动修复”安全问题。它的职责是把当前项目最容易被忽略
    的安全边界结构化返回给前端、curl 和教程验证步骤，方便上线前逐项排查。
    """

    def __init__(self, settings: Settings = settings) -> None:
        # ===================== 第1步：保存配置对象，便于测试注入不同环境 =====================
        self.settings = settings

    def list_checks(self) -> list[SecurityCheck]:
        """返回当前项目需要关注的安全检查清单。"""

        # ===================== 第2步：按边界类型聚合检查项 =====================
        checks: list[SecurityCheck] = []
        checks.extend(self._configuration_checks())
        checks.extend(self._upload_checks())
        checks.extend(self._sandbox_checks())
        checks.extend(self._integration_checks())
        checks.extend(self._memory_checks())
        return checks

    def _configuration_checks(self) -> list[SecurityCheck]:
        # ===================== 第3步：检查 CORS 是否在生产环境过于开放 =====================
        cors_is_wildcard = "*" in self.settings.cors_allow_origins
        production = self.settings.api_env.lower() == "production"
        cors_severity = "risk" if production and cors_is_wildcard else "warning"

        checks = [
            SecurityCheck(
                key="cors_origin_policy",
                name="CORS 来源策略",
                category="configuration",
                severity=cors_severity,
                risk="CORS 过于开放会让任意网页调用 API，生产环境尤其危险。",
                recommendation=(
                    "生产环境只保留正式前端域名；本地开发可以保留 localhost。"
                ),
                verify_command="curl http://localhost:8088/api/security/checks",
            )
        ]

        # ===================== 第4步：检查数据库默认密码是否仍然存在 =====================
        database_url = self.settings.database_url
        uses_default_password = ":postgres@" in database_url
        checks.append(
            SecurityCheck(
                key="database_default_password",
                name="数据库默认密码",
                category="configuration",
                severity="risk" if production and uses_default_password else "warning",
                risk="默认数据库密码容易被猜到，不适合生产或公网环境。",
                recommendation=(
                    "在 .env 中替换 PostgreSQL 用户、密码和连接地址，并避免提交真实密钥。"
                ),
                verify_command="docker compose config | sed -n '/DATABASE_URL/p'",
            )
        )
        return checks

    def _upload_checks(self) -> list[SecurityCheck]:
        # ===================== 第5步：检查上传目录和大小限制是否明确 =====================
        return [
            SecurityCheck(
                key="upload_size_limit",
                name="上传大小限制",
                category="uploads",
                severity="info",
                risk="没有大小限制时，恶意上传可能占满磁盘或拖慢文件预览。",
                recommendation=(
                    f"当前 max_upload_size={self.settings.max_upload_size} 字节；"
                    "生产环境应按业务场景设置更严格的限制。"
                ),
                verify_command="curl http://localhost:8088/api/config/app",
            ),
            SecurityCheck(
                key="upload_path_boundary",
                name="上传路径边界",
                category="uploads",
                severity="warning",
                risk="如果直接信任文件名或相对路径，可能出现目录穿越。",
                recommendation=(
                    f"上传根目录为 {self.settings.upload_dir}；保存文件时应生成服务端文件名，"
                    "并确保最终路径仍在上传根目录内。"
                ),
                verify_command="curl http://localhost:8088/api/security/checks",
            ),
        ]

    def _sandbox_checks(self) -> list[SecurityCheck]:
        # ===================== 第6步：检查 Sandbox API、Shell 和浏览器边界 =====================
        timeout_severity = (
            "risk" if self.settings.sandbox_api_timeout_seconds > 60 else "info"
        )
        return [
            SecurityCheck(
                key="sandbox_api_boundary",
                name="Sandbox API 边界",
                category="sandbox",
                severity="warning",
                risk="Sandbox 拥有文件、Shell、浏览器和 VNC 能力，不应直接暴露到公网。",
                recommendation=(
                    "只通过 Nginx 网关和主 API 访问 Sandbox；生产环境要叠加鉴权和网络隔离。"
                ),
                verify_command="curl http://localhost:8088/sandbox-api/status",
            ),
            SecurityCheck(
                key="sandbox_shell_timeout",
                name="Shell 命令超时",
                category="sandbox",
                severity=timeout_severity,
                risk="Shell 工具如果没有超时和输出限制，可能被长时间运行或输出洪泛拖垮。",
                recommendation=(
                    f"当前等待超时为 {self.settings.sandbox_shell_wait_timeout_seconds} 秒；"
                    "后续工具执行应继续限制命令白名单、工作目录和输出长度。"
                ),
                verify_command="curl http://localhost:8088/sandbox-api/shell/sessions",
            ),
        ]

    def _integration_checks(self) -> list[SecurityCheck]:
        # ===================== 第7步：检查外部搜索、MCP 和 A2A 调用的安全边界 =====================
        search_has_key = bool(self.settings.bing_search_api_key.strip())
        return [
            SecurityCheck(
                key="external_search_key",
                name="外部搜索密钥",
                category="integrations",
                severity="info" if search_has_key else "warning",
                risk="外部搜索密钥缺失时搜索工具不可用；密钥泄露时会带来额度和数据风险。",
                recommendation=(
                    "把搜索密钥放在 .env 或密钥管理系统中，不要写入代码和教程示例。"
                ),
                verify_command="curl http://localhost:8088/api/config/llm",
            ),
            SecurityCheck(
                key="mcp_a2a_timeout_and_disable",
                name="MCP/A2A 超时和禁用开关",
                category="integrations",
                severity="warning",
                risk="外部 Agent 或 MCP Server 如果无超时、无禁用开关，可能拖慢主任务。",
                recommendation=(
                    f"当前搜索超时为 {self.settings.search_timeout_seconds} 秒；"
                    "外部工具应统一设置超时、错误事件和启用开关。"
                ),
                verify_command="curl http://localhost:8088/api/config/app",
            ),
        ]

    def _memory_checks(self) -> list[SecurityCheck]:
        # ===================== 第8步：检查长期记忆的敏感信息处理边界 =====================
        return [
            SecurityCheck(
                key="memory_sensitive_filter",
                name="长期记忆敏感信息过滤",
                category="memory",
                severity="warning",
                risk="长期记忆可能保存用户偏好、项目事实和任务经验，也可能误收集密钥或隐私。",
                recommendation=(
                    "写入长期记忆前应过滤 API Key、密码、Token、身份证号等敏感信息。"
                ),
                verify_command="curl http://localhost:8088/api/memories",
            ),
            SecurityCheck(
                key="memory_disable_and_delete",
                name="记忆禁用和删除机制",
                category="memory",
                severity="info",
                risk="用户需要能禁用、删除或过期长期记忆，否则错误记忆会持续影响 Agent。",
                recommendation=(
                    f"当前最多注入 {self.settings.context_memory_limit} 条记忆；"
                    "保留 enabled、delete 和 expires_at 机制。"
                ),
                verify_command="curl http://localhost:8088/api/memories",
            ),
        ]
