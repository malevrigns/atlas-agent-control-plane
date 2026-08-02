from dataclasses import dataclass, field
import json
import os
from os import getenv
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from app.application.a2a_service import A2aService
from app.application.llm_service import LLMService
from app.application.mcp_service import McpService
from app.application.multi_agent_service import MultiAgentService
from app.core.a2a_config import A2aConfig, load_a2a_config
from app.core.config import settings
from app.core.llm_config import load_llm_config
from app.core.mcp_config import McpConfig, load_mcp_config
from app.core.exceptions import AppException
from app.core.module_policy import module_enabled, set_module_enabled


@dataclass(slots=True)
class SettingsModule:
    """设置页中的一个能力模块。"""

    key: str
    name: str
    description: str
    enabled: bool
    default_item: str | None = None
    items: list[dict[str, object]] = field(default_factory=list)
    status: str = "ready"
    status_message: str = ""
    source: str = ""
    verify_command: str = ""


@dataclass(slots=True)
class SettingsIntegration:
    """设置页中由用户新增的一条集成记录。"""

    id: str
    kind: str
    name: str
    description: str
    endpoint: str | None
    enabled: bool


@dataclass(slots=True)
class AppSettingsSnapshot:
    """设置页一次性需要展示的配置快照。"""

    modules: list[SettingsModule]
    integrations: list[SettingsIntegration]


class AppSettingsService:
    """聚合 LLM、MCP、A2A 和多 Agent 的设置页数据。

    第 62 章开始，设置页不再只保存进程内状态。
    用户保存 LLM/MCP/A2A 配置时，会写入 runtime-config 目录，
    然后清理配置缓存并重建对应服务，让新配置立即参与后续任务。
    """

    def __init__(
        self,
        llm_service: LLMService | None = None,
        mcp_service: McpService | None = None,
        a2a_service: A2aService | None = None,
        multi_agent_service: MultiAgentService | None = None,
    ) -> None:
        # ===================== 第1步：保存各模块服务 =====================
        # 这些服务负责读取各自已有配置；设置服务只做聚合和运行时开关。
        self.llm_service = llm_service or LLMService()
        self.mcp_service = mcp_service or McpService()
        self.a2a_service = a2a_service or A2aService()
        self.multi_agent_service = multi_agent_service or MultiAgentService()

    # ===================== 第3步：读取完整设置快照 =====================
    def get_snapshot(self) -> AppSettingsSnapshot:
        """返回设置页需要展示的完整快照。"""

        modules = [
            self._build_llm_module(),
            self._build_search_module(),
            self._build_mcp_module(),
            self._build_a2a_module(),
            self._build_multi_agent_module(),
            self._build_sandbox_module(),
        ]
        return AppSettingsSnapshot(
            modules=[self._apply_override(module) for module in modules],
            integrations=self._build_integrations(),
        )

    # ===================== 第4步：更新模块运行时状态 =====================
    def update_module(
        self,
        module_key: str,
        enabled: bool | None = None,
        default_item: str | None = None,
    ) -> SettingsModule:
        """更新某个模块的启用状态或默认项。"""

        # 1. 先确认模块存在，避免调用方传入拼错的 key。
        current_module = self._find_module(module_key)

        # 2. 把开关写入 runtime-config/modules.yaml，Tool Runtime 和 LLM 服务都会读取它。
        if enabled is not None:
            set_module_enabled(module_key, enabled)
        if default_item is not None:
            self._set_default_item(module_key, default_item)

        # 3. 重载配置后返回真实状态，而不是进程内的展示覆盖。
        self._reload_services()
        return self._find_module(module_key)

    # ===================== 第5步：新增和删除页面集成记录 =====================
    def add_integration(
        self,
        kind: str,
        name: str,
        description: str = "",
        endpoint: str | None = None,
    ) -> SettingsIntegration:
        """新增一条设置页集成记录，并按类型写入运行时配置。"""

        # 1. 先把用户提交的配置写入 runtime-config。
        #    这样 API 重启后仍能从配置文件恢复，而不是只存在内存里。
        if kind == "llm":
            saved_name = self.save_llm_provider(
                provider_name=name,
                base_url=endpoint or "",
                api_key_env=description,
            )
        elif kind == "mcp":
            saved_name = self.save_mcp_server(
                server_name=name,
                config_text=description,
                endpoint=endpoint,
            )
        elif kind == "a2a":
            saved_name = self.save_a2a_agent(
                agent_key=name,
                description=description,
                endpoint=endpoint or "",
            )
        else:
            raise AppException(
                message=f"integration type is not configurable: {kind}",
                code=400,
                status_code=400,
            )

        # 2. 从刚刚写入的持久化配置重建响应，避免页面记录与真实名称或状态不一致。
        return next(
            integration
            for integration in self._build_integrations()
            if integration.id == f"{kind}:{saved_name}"
        )

    def delete_integration(self, integration_id: str) -> SettingsIntegration:
        """删除一条设置页集成记录。"""

        integration = next(
            (item for item in self._build_integrations() if item.id == integration_id),
            None,
        )
        if integration is None:
            raise KeyError(integration_id)
        self.delete_config_item(integration.kind, integration.name)
        return integration

    # ===================== 第6步：保存 LLM、MCP、A2A 运行时配置 =====================
    def save_llm_provider(
        self,
        provider_name: str,
        base_url: str,
        api_key_env: str,
        model: str | None = None,
    ) -> str:
        """保存一个 OpenAI-compatible LLM provider。"""

        clean_name = provider_name.strip()
        if not clean_name:
            raise AppException(message="LLM provider name is required", code=400, status_code=400)
        clean_base_url = base_url.strip()
        if not clean_base_url:
            raise AppException(message="LLM base_url is required", code=400, status_code=400)

        raw_config = self._read_config(settings.llm_config_path, "config/llm.yaml")
        llm_defaults = dict(raw_config.get("llm") or {})
        providers = dict(raw_config.get("providers") or {})
        previous_provider = dict(providers.get(clean_name) or {})

        llm_defaults["default_provider"] = clean_name
        if model:
            llm_defaults["default_model"] = model.strip()
        llm_defaults.setdefault("default_model", raw_config.get("llm", {}).get("default_model", "deepseek-chat"))
        llm_defaults.setdefault("temperature", raw_config.get("llm", {}).get("temperature", 0.2))
        llm_defaults.setdefault("max_tokens", raw_config.get("llm", {}).get("max_tokens", 1024))

        providers[clean_name] = {
            "base_url": clean_base_url,
            "api_key_env": api_key_env.strip()
            or previous_provider.get("api_key_env")
            or "LLM_API_KEY",
            "timeout_seconds": previous_provider.get("timeout_seconds") or 60,
        }

        self._write_config(settings.llm_config_path, {"llm": llm_defaults, "providers": providers})
        self._reload_services()
        return clean_name

    def save_mcp_server(
        self,
        server_name: str,
        config_text: str,
        endpoint: str | None = None,
    ) -> str:
        """新增或更新 MCP Server 配置。"""

        raw_config = self._read_config(settings.mcp_config_path, "config/mcp.yaml")
        servers = dict(raw_config.get("servers") or {})
        clean_name = server_name.strip()

        parsed_servers = self._parse_mcp_servers(config_text)
        if parsed_servers:
            servers.update(parsed_servers)
            clean_name = next(iter(parsed_servers))
        else:
            if not clean_name:
                raise AppException(message="MCP server name is required", code=400, status_code=400)
            clean_endpoint = (endpoint or "").strip()
            servers[clean_name] = {
                "enabled": True,
                "transport": "streamable_http" if clean_endpoint else "demo",
                "url": clean_endpoint or None,
                "description": config_text.strip() or "从配置中心新增的 MCP Server。",
                "timeout_seconds": 10,
            }
            if not clean_endpoint:
                servers[clean_name].pop("url", None)

        mcp_defaults = dict(raw_config.get("mcp") or {})
        mcp_defaults.setdefault("enabled", True)
        mcp_defaults["default_server"] = clean_name or mcp_defaults.get("default_server") or "demo"
        payload = {"mcp": mcp_defaults, "servers": servers}
        try:
            McpConfig.model_validate(payload)
        except ValueError as exc:
            raise AppException(
                message=f"MCP configuration violates operator policy: {exc}",
                code=400,
                status_code=400,
            ) from exc
        self._write_config(settings.mcp_config_path, payload)
        self._reload_services()
        return clean_name

    def save_a2a_agent(
        self,
        agent_key: str,
        description: str,
        endpoint: str,
    ) -> str:
        """新增或更新 A2A 远程 Agent 配置。"""

        clean_key = agent_key.strip()
        clean_endpoint = endpoint.strip()
        if not clean_key:
            raise AppException(message="A2A agent key is required", code=400, status_code=400)
        if not clean_endpoint:
            raise AppException(message="A2A agent endpoint is required", code=400, status_code=400)

        raw_config = self._read_config(settings.a2a_config_path, "config/a2a.yaml")
        agents = dict(raw_config.get("agents") or {})
        agents[clean_key] = {
            "enabled": True,
            "transport": "http",
            "name": clean_key,
            "description": description.strip() or "从配置中心新增的远程 Agent。",
            "url": clean_endpoint,
            "version": "0.1.0",
            "timeout_seconds": 15,
            "capabilities": [
                {
                    "name": "remote_task",
                    "description": description.strip() or "远程 Agent 任务能力。",
                    "input_modes": ["text"],
                    "output_modes": ["text"],
                }
            ],
        }

        a2a_defaults = dict(raw_config.get("a2a") or {})
        a2a_defaults.setdefault("enabled", True)
        a2a_defaults["default_agent"] = clean_key
        payload = {"a2a": a2a_defaults, "agents": agents}
        try:
            A2aConfig.model_validate(payload)
        except ValueError as exc:
            raise AppException(
                message=f"A2A configuration violates operator policy: {exc}",
                code=400,
                status_code=400,
            ) from exc
        self._write_config(settings.a2a_config_path, payload)
        self._reload_services()
        return clean_key

    def update_config_item(self, module_key: str, item_name: str, enabled: bool) -> None:
        """启用或禁用 MCP Server / A2A Agent。"""

        if module_key == "mcp":
            raw_config = self._read_config(settings.mcp_config_path, "config/mcp.yaml")
            servers = dict(raw_config.get("servers") or {})
            if item_name not in servers:
                raise KeyError(item_name)
            servers[item_name]["enabled"] = enabled
            payload = {**raw_config, "servers": servers}
            try:
                McpConfig.model_validate(payload)
            except ValueError as exc:
                raise AppException(
                    message=f"MCP configuration violates operator policy: {exc}",
                    code=400,
                    status_code=400,
                ) from exc
            self._write_config(settings.mcp_config_path, payload)
        elif module_key == "a2a":
            raw_config = self._read_config(settings.a2a_config_path, "config/a2a.yaml")
            agents = dict(raw_config.get("agents") or {})
            if item_name not in agents:
                raise KeyError(item_name)
            agents[item_name]["enabled"] = enabled
            payload = {**raw_config, "agents": agents}
            try:
                A2aConfig.model_validate(payload)
            except ValueError as exc:
                raise AppException(
                    message=f"A2A configuration violates operator policy: {exc}",
                    code=400,
                    status_code=400,
                ) from exc
            self._write_config(settings.a2a_config_path, payload)
        else:
            raise KeyError(item_name)
        self._reload_services()

    def delete_config_item(self, module_key: str, item_name: str) -> None:
        """删除 MCP Server / A2A Agent 配置。"""

        if module_key == "llm":
            raw_config = self._read_config(settings.llm_config_path, "config/llm.yaml")
            providers = dict(raw_config.get("providers") or {})
            if item_name not in providers:
                raise KeyError(item_name)
            if len(providers) <= 1:
                raise AppException(
                    message="at least one LLM provider must remain",
                    code=400,
                    status_code=400,
                )
            providers.pop(item_name)
            llm_defaults = dict(raw_config.get("llm") or {})
            if llm_defaults.get("default_provider") == item_name:
                llm_defaults["default_provider"] = next(iter(providers), "")
            self._write_config(settings.llm_config_path, {"llm": llm_defaults, "providers": providers})
        elif module_key == "mcp":
            raw_config = self._read_config(settings.mcp_config_path, "config/mcp.yaml")
            servers = dict(raw_config.get("servers") or {})
            if item_name not in servers:
                raise KeyError(item_name)
            if len(servers) <= 1:
                raise AppException(
                    message="at least one MCP server must remain",
                    code=400,
                    status_code=400,
                )
            servers.pop(item_name)
            mcp_defaults = dict(raw_config.get("mcp") or {})
            if mcp_defaults.get("default_server") == item_name:
                mcp_defaults["default_server"] = next(iter(servers), "")
            self._write_config(settings.mcp_config_path, {"mcp": mcp_defaults, "servers": servers})
        elif module_key == "a2a":
            raw_config = self._read_config(settings.a2a_config_path, "config/a2a.yaml")
            agents = dict(raw_config.get("agents") or {})
            if item_name not in agents:
                raise KeyError(item_name)
            if len(agents) <= 1:
                raise AppException(
                    message="at least one A2A agent must remain",
                    code=400,
                    status_code=400,
                )
            agents.pop(item_name)
            a2a_defaults = dict(raw_config.get("a2a") or {})
            if a2a_defaults.get("default_agent") == item_name:
                a2a_defaults["default_agent"] = next(iter(agents), "")
            self._write_config(settings.a2a_config_path, {"a2a": a2a_defaults, "agents": agents})
        else:
            raise KeyError(item_name)
        self._reload_services()

    # ===================== 第7步：构造各模块设置数据 =====================
    def _build_llm_module(self) -> SettingsModule:
        public_config = self.llm_service.get_public_config()
        default_provider = str(public_config["default_provider"])
        default_configured = any(
            provider["name"] == default_provider and provider["configured"]
            for provider in public_config["providers"]
        )
        return SettingsModule(
            key="llm",
            name="LLM",
            description="模型服务商、默认模型和调用参数。",
            enabled=True,
            default_item=default_provider,
            status="ready" if default_configured else "warning",
            status_message=(
                f"默认模型服务 {default_provider} 已配置密钥。"
                if default_configured
                else f"默认模型服务 {default_provider} 还没有配置 API Key。"
            ),
            source=settings.llm_config_path,
            verify_command="curl http://localhost:8088/api/config/llm",
            items=[
                {
                    "name": provider["name"],
                    "description": provider["base_url"],
                    "enabled": provider["configured"],
                    "metadata": {
                        "api_key_env": provider["api_key_env"],
                        "configured": provider["configured"],
                    },
                }
                for provider in public_config["providers"]
            ],
        )

    def _build_search_module(self) -> SettingsModule:
        api_key_configured = bool(settings.bing_search_api_key)
        return SettingsModule(
            key="search",
            name="Search",
            description="搜索工具配置，包括 Bing API 和页面搜索兜底。",
            enabled=True,
            default_item="bing-api" if api_key_configured else "page-fallback",
            status="ready" if api_key_configured else "warning",
            status_message=(
                "Bing API Key 已配置，搜索工具会优先调用官方 API。"
                if api_key_configured
                else "Bing API Key 未配置，搜索工具会使用页面搜索兜底，稳定性取决于网络。"
            ),
            source=".env",
            verify_command="curl http://localhost:8088/api/config/app",
            items=[
                {
                    "name": "bing-api",
                    "description": settings.bing_search_endpoint,
                    "enabled": api_key_configured,
                    "metadata": {
                        "market": settings.bing_search_market,
                        "api_key_env": "BING_SEARCH_API_KEY",
                        "configured": api_key_configured,
                    },
                },
                {
                    "name": "page-fallback",
                    "description": "不需要密钥的页面搜索兜底，会解析公开搜索结果页。",
                    "enabled": True,
                    "metadata": {
                        "provider": "bing-page / duckduckgo-page",
                        "timeout_seconds": settings.search_timeout_seconds,
                    },
                },
            ],
        )

    def _build_mcp_module(self) -> SettingsModule:
        servers = self.mcp_service.list_servers()
        enabled_count = sum(1 for server in servers if server.enabled)
        return SettingsModule(
            key="mcp",
            name="MCP",
            description="外部工具服务器和工具发现配置。",
            enabled=True,
            default_item=self.mcp_service.manager.config.mcp.default_server,
            status="ready" if enabled_count else "warning",
            status_message=(
                f"已启用 {enabled_count} 个 MCP Server。"
                if enabled_count
                else "还没有启用 MCP Server，MCP 工具不会参与任务执行。"
            ),
            source=settings.mcp_config_path,
            verify_command="curl http://localhost:8088/api/mcp/servers",
            items=[
                {
                    "name": server.name,
                    "description": server.description,
                    "enabled": server.enabled,
                    "metadata": {"transport": server.transport},
                }
                for server in servers
            ],
        )

    def _build_a2a_module(self) -> SettingsModule:
        agents = self.a2a_service.list_agents()
        enabled_count = sum(1 for agent in agents if agent.enabled)
        return SettingsModule(
            key="a2a",
            name="A2A",
            description="远程 Agent 发现、Agent Card 和 message/send 调用配置。",
            enabled=True,
            default_item=self.a2a_service.manager.config.a2a.default_agent,
            status="ready" if enabled_count else "warning",
            status_message=(
                f"已启用 {enabled_count} 个远程 Agent。"
                if enabled_count
                else "还没有启用远程 Agent，A2A 工具不会参与任务执行。"
            ),
            source=settings.a2a_config_path,
            verify_command="curl http://localhost:8088/api/a2a/agents",
            items=[
                {
                    "name": agent.key,
                    "description": agent.description,
                    "enabled": agent.enabled,
                    "metadata": {
                        "transport": agent.transport,
                        "url": agent.url,
                        "version": agent.version,
                    },
                }
                for agent in agents
            ],
        )

    def _build_multi_agent_module(self) -> SettingsModule:
        roles = self.multi_agent_service.list_roles()
        return SettingsModule(
            key="multi_agent",
            name="多 Agent",
            description="Manager、Worker、Reviewer 的协作角色和编排开关。",
            enabled=True,
            default_item="manager",
            status="ready" if roles else "warning",
            status_message=(
                f"已加载 {len(roles)} 个内置协作角色。"
                if roles
                else "还没有可用的多 Agent 协作角色。"
            ),
            source="app.application.multi_agent_service",
            verify_command="curl http://localhost:8088/api/multi-agent/roles",
            items=[
                {
                    "name": role.name,
                    "description": role.responsibility,
                    "enabled": True,
                    "metadata": {
                        "key": role.key,
                        "capability": role.capability,
                    },
                }
                for role in roles
            ],
        )

    def _build_sandbox_module(self) -> SettingsModule:
        browser_enabled = getenv("SANDBOX_BROWSER_ENABLED", "true").lower() == "true"
        vnc_enabled = getenv("SANDBOX_VNC_ENABLED", "true").lower() == "true"
        return SettingsModule(
            key="sandbox",
            name="Sandbox",
            description="文件、Shell、浏览器、截图和 VNC 的隔离执行环境。",
            enabled=True,
            default_item=settings.docker_sandbox_id,
            status="ready",
            status_message="Sandbox 连接信息已配置，运行时状态可通过沙箱接口验证。",
            source=".env / docker-compose.yml",
            verify_command="curl http://localhost:8088/api/sandboxes/current",
            items=[
                {
                    "name": "file",
                    "description": "读取、写入和同步会话附件到 Sandbox 工作目录。",
                    "enabled": True,
                    "metadata": {
                        "base_url": settings.sandbox_api_base_url,
                    },
                },
                {
                    "name": "shell",
                    "description": "在 Sandbox 中执行命令并读取输出。",
                    "enabled": True,
                    "metadata": {
                        "wait_timeout_seconds": settings.sandbox_shell_wait_timeout_seconds,
                    },
                },
                {
                    "name": "browser",
                    "description": "通过 Playwright 控制 Sandbox 浏览器。",
                    "enabled": browser_enabled,
                    "metadata": {
                        "browser_env": "SANDBOX_BROWSER_ENABLED",
                    },
                },
                {
                    "name": "vnc",
                    "description": "通过 noVNC 查看 Sandbox 浏览器远程桌面。",
                    "enabled": vnc_enabled,
                    "metadata": {
                        "status_url": "/sandbox-api/vnc/status",
                    },
                },
            ],
        )

    def _build_integrations(self) -> list[SettingsIntegration]:
        """Rebuild the integration list from durable configuration files."""

        integrations: list[SettingsIntegration] = []
        public_llm = self.llm_service.get_public_config()
        for provider in public_llm["providers"]:
            name = str(provider["name"])
            api_key_env = str(provider["api_key_env"])
            integrations.append(
                SettingsIntegration(
                    id=f"llm:{name}",
                    kind="llm",
                    name=name,
                    description=f"密钥由环境变量 {api_key_env} 提供。",
                    endpoint=str(provider["base_url"]),
                    enabled=bool(provider["configured"]),
                )
            )

        for name, server in self.mcp_service.manager.config.servers.items():
            integrations.append(
                SettingsIntegration(
                    id=f"mcp:{name}",
                    kind="mcp",
                    name=name,
                    description=server.description,
                    endpoint=server.url,
                    enabled=server.enabled,
                )
            )

        for agent in self.a2a_service.list_agents():
            integrations.append(
                SettingsIntegration(
                    id=f"a2a:{agent.key}",
                    kind="a2a",
                    name=agent.key,
                    description=agent.description,
                    endpoint=agent.url,
                    enabled=agent.enabled,
                )
            )
        return integrations

    # ===================== 第7步：内部辅助方法 =====================
    def _find_module(self, module_key: str) -> SettingsModule:
        for module in self.get_snapshot().modules:
            if module.key == module_key:
                return module
        raise KeyError(module_key)

    def _apply_override(self, module: SettingsModule) -> SettingsModule:
        enabled = module_enabled(module.key)
        return SettingsModule(
            key=module.key,
            name=module.name,
            description=module.description,
            enabled=enabled,
            default_item=module.default_item,
            items=module.items,
            status=module.status if enabled else "disabled",
            status_message=module.status_message if enabled else "模块已禁用，运行时会拒绝相关调用。",
            source=module.source,
            verify_command=module.verify_command,
        )

    def _set_default_item(self, module_key: str, item_name: str) -> None:
        if module_key == "llm":
            raw = self._read_config(settings.llm_config_path, "config/llm.yaml")
            items = dict(raw.get("providers") or {})
            section = dict(raw.get("llm") or {})
            key = "default_provider"
            path = settings.llm_config_path
            payload_key = "providers"
        elif module_key == "mcp":
            raw = self._read_config(settings.mcp_config_path, "config/mcp.yaml")
            items = dict(raw.get("servers") or {})
            section = dict(raw.get("mcp") or {})
            key = "default_server"
            path = settings.mcp_config_path
            payload_key = "servers"
        elif module_key == "a2a":
            raw = self._read_config(settings.a2a_config_path, "config/a2a.yaml")
            items = dict(raw.get("agents") or {})
            section = dict(raw.get("a2a") or {})
            key = "default_agent"
            path = settings.a2a_config_path
            payload_key = "agents"
        else:
            raise AppException(
                message=f"module does not support a default item: {module_key}",
                code=400,
                status_code=400,
            )
        if item_name not in items:
            raise AppException(
                message=f"settings item not found: {module_key}.{item_name}",
                code=404,
                status_code=404,
            )
        section[key] = item_name
        self._write_config(path, {module_key if module_key != "llm" else "llm": section, payload_key: items})

    # ===================== 第9步：配置文件读写和服务重载 =====================
    def _read_config(self, runtime_path: str, fallback_path: str) -> dict:
        """读取运行时配置；不存在时读取课程示例配置。"""

        # 1. 优先读取 runtime-config。页面保存后的内容都会写到这里。
        path = Path(runtime_path)

        # 2. 第一次运行时 runtime-config 可能还不存在，此时用课程示例配置兜底。
        if not path.is_file():
            path = Path(fallback_path)
        if not path.is_file() and not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / fallback_path

        # 3. 两个路径都不存在时返回空字典，让调用方可以创建第一份配置。
        if not path.is_file():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _write_config(self, runtime_path: str, payload: dict) -> None:
        """把配置写入 runtime-config，并确保目录存在。"""

        # 1. runtime-config 被 .gitignore 排除，也会在 Docker Compose 中挂载为 volume。
        path = Path(runtime_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 2. 使用 safe_dump，避免写出 Python 专用对象标记。
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.replace(path)

    def _parse_mcp_servers(self, config_text: str) -> dict[str, dict[str, object]]:
        """解析用户粘贴的 MCP JSON 配置。"""

        clean_text = config_text.strip()
        if not clean_text.startswith("{"):
            return {}
        try:
            payload = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            raise AppException(
                message=f"MCP config JSON is invalid: {exc}",
                code=400,
                status_code=400,
            ) from exc

        raw_servers = payload.get("mcpServers") if isinstance(payload, dict) else None
        if not isinstance(raw_servers, dict):
            return {}

        servers: dict[str, dict[str, object]] = {}
        for name, raw_server in raw_servers.items():
            if not isinstance(raw_server, dict):
                continue
            command = str(raw_server.get("command") or "")
            url = str(raw_server.get("url") or raw_server.get("endpoint") or "")
            transport = (
                str(raw_server.get("transport"))
                if raw_server.get("transport")
                else "stdio"
                if command
                else "streamable_http"
                if url
                else "demo"
            )
            server_config: dict[str, object] = {
                "enabled": bool(raw_server.get("enabled", True)),
                "transport": transport,
                "description": str(raw_server.get("description") or ""),
                "timeout_seconds": float(raw_server.get("timeout_seconds") or 10),
            }
            if command:
                server_config["command"] = command
                server_config["args"] = list(raw_server.get("args") or [])
            if url:
                server_config["url"] = url
            servers[str(name)] = server_config
        return servers

    def _reload_services(self) -> None:
        """清理配置缓存，并重建依赖配置的应用服务。"""

        # 1. 三个配置 loader 都使用了 lru_cache，保存文件后必须清掉缓存。
        load_llm_config.cache_clear()
        load_mcp_config.cache_clear()
        load_a2a_config.cache_clear()

        # 2. 重新创建服务，让后续接口和 AgentTool 读取到最新配置。
        self.llm_service = LLMService()
        self.mcp_service = McpService()
        self.a2a_service = A2aService()


# ===================== 第8步：创建进程内共享设置服务 =====================
# 设置页的运行时开关和新增记录需要跨请求保存，所以这里使用模块级实例。
app_settings_service = AppSettingsService()


def get_app_settings_service() -> AppSettingsService:
    return app_settings_service
