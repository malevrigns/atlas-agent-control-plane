from app.domain.observability.entities import ObservabilityCheck


class ObservabilityService:
    """提供 Agent 系统调试清单。

    第 47 章先把最常用的排查入口结构化返回给前端和调用方。
    它不直接探测外部系统，避免诊断接口本身因为 Docker、网络或密钥问题变慢。
    """

    def list_checks(self) -> list[ObservabilityCheck]:
        """返回核心子系统的可执行诊断命令。"""

        # ===================== 第1步：API、数据库和会话基础链路 =====================
        base_checks = [
            ObservabilityCheck(
                key="api_status",
                name="API 状态",
                category="core",
                description="确认主 API 服务是否可用。",
                command="curl http://localhost:8088/api/status",
                expected='返回 code=200，data.status 为 "ok"',
            ),
            ObservabilityCheck(
                key="database_status",
                name="数据库状态",
                category="core",
                description="确认 API 是否能连接 PostgreSQL。",
                command="curl http://localhost:8088/api/status/database",
                expected="返回 code=200，数据库状态正常",
            ),
            ObservabilityCheck(
                key="session_list",
                name="会话列表",
                category="session",
                description="确认会话接口和数据库表是否正常。",
                command="curl http://localhost:8088/api/sessions",
                expected="返回 items 数组",
            ),
        ]

        # ===================== 第2步：Agent 执行、上下文、记忆和 Harness =====================
        agent_checks = [
            ObservabilityCheck(
                key="session_context",
                name="会话上下文",
                category="agent",
                description="确认短期消息、事件摘要和长期记忆注入是否可读。",
                command="curl http://localhost:8088/api/sessions/{session_id}/context",
                expected="返回 messages、event_summaries、memory_context 和 budget",
            ),
            ObservabilityCheck(
                key="memory_list",
                name="长期记忆",
                category="agent",
                description="确认长期记忆接口是否可用。",
                command="curl http://localhost:8088/api/memories",
                expected="返回长期记忆 items 数组",
            ),
            ObservabilityCheck(
                key="harness_cases",
                name="Harness 任务集",
                category="agent",
                description="确认固定回归任务集和 Harness 接口是否可用。",
                command="curl http://localhost:8088/api/harness/cases",
                expected="返回 browser、memory、multi_agent 等评测用例",
            ),
        ]

        # ===================== 第3步：工具、沙箱和外部协作链路 =====================
        integration_checks = [
            ObservabilityCheck(
                key="sandbox_status",
                name="Sandbox 状态",
                category="tooling",
                description="确认 Sandbox API 是否可用。",
                command="curl http://localhost:8088/sandbox-api/status",
                expected="返回 Sandbox 服务状态",
            ),
            ObservabilityCheck(
                key="mcp_tools",
                name="MCP 工具",
                category="tooling",
                description="确认 MCP 工具发现接口是否可用。",
                command="curl http://localhost:8088/api/mcp/tools",
                expected="返回 MCP 工具列表",
            ),
            ObservabilityCheck(
                key="a2a_agents",
                name="A2A 远程 Agent",
                category="tooling",
                description="确认 A2A 远程 Agent 配置是否可读。",
                command="curl http://localhost:8088/api/a2a/agents",
                expected="返回远程 Agent 列表",
            ),
            ObservabilityCheck(
                key="multi_agent_roles",
                name="多 Agent 角色",
                category="tooling",
                description="确认多 Agent 角色配置是否可用。",
                command="curl http://localhost:8088/api/multi-agent/roles",
                expected="返回 manager、worker、reviewer 等角色",
            ),
        ]

        return base_checks + agent_checks + integration_checks
