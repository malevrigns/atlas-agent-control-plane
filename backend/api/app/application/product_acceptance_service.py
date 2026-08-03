from app.domain.acceptance.entities import (
    ProductAcceptanceChecklist,
    ProductAcceptanceItem,
    ProductAcceptanceSummary,
)


class ProductAcceptanceService:
    """汇总最终 Agent 产品体验验收清单。

    第 49 章不再新增大型业务模块，而是把前面章节已经实现的对话、计划、
    工具、记忆、多 Agent、Harness 和沙箱能力整理成一组可执行验收项。
    """

    def get_checklist(self) -> ProductAcceptanceChecklist:
        """返回成熟 Agent 产品体验验收清单。"""

        # ===================== 第1步：整理端到端对话与执行体验 =====================
        conversation_items = [
            ProductAcceptanceItem(
                key="natural_conversation",
                title="自然对话入口",
                category="conversation",
                status="needs_manual_check",
                evidence="页面发送一条任务消息后，应自动进入规划和执行流程。",
                verify_steps=[
                    "访问 http://localhost:8088。",
                    "创建或选择一个会话。",
                    "直接输入任务并发送，不需要额外点击生成计划或执行按钮。",
                    "确认对话区出现用户消息和 Agent 运行过程。",
                ],
                related_routes=[
                    "POST /api/sessions",
                    "POST /api/sessions/{session_id}/messages/stream",
                ],
            ),
            ProductAcceptanceItem(
                key="agent_plan_execution",
                title="计划生成和步骤执行",
                category="conversation",
                status="ready",
                evidence="Agent Runner 已统一 SSE、同步执行和后台任务链路，并产生 plan_created、step_started、tool_called 等事件。",
                verify_steps=[
                    "发送一个需要多步骤执行的任务。",
                    "确认时间线出现计划步骤。",
                    "确认步骤状态从 pending/running 变为 completed 或 failed。",
                ],
                related_routes=[
                    "POST /api/sessions/{session_id}/plan",
                    "POST /api/sessions/{session_id}/plan/tasks",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
            ProductAcceptanceItem(
                key="streaming_timeline",
                title="流式执行时间线",
                category="conversation",
                status="needs_manual_check",
                evidence="前端会消费 SSE 事件，并在对话时间线中展示消息、计划、工具和最终结果。",
                verify_steps=[
                    "发送任务后观察页面是否持续更新。",
                    "确认工具调用卡片可以点击并打开详情。",
                    "确认最终结果显示在对话时间线中。",
                ],
                related_routes=[
                    "POST /api/sessions/{session_id}/messages/stream",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
        ]

        # ===================== 第2步：整理工具预览、浏览器和沙箱体验 =====================
        tool_items = [
            ProductAcceptanceItem(
                key="tool_preview_surface",
                title="统一工具预览",
                category="tooling",
                status="needs_manual_check",
                evidence="右侧工具预览已收敛文件、Shell、浏览器、搜索、MCP、A2A 和多 Agent 结果。",
                verify_steps=[
                    "发送包含文件、搜索或浏览器动作的任务。",
                    "点击时间线中的工具调用卡片。",
                    "确认右侧抽屉或弹层展示调用参数和结果。",
                ],
                related_routes=[
                    "GET /api/sessions/{session_id}/events",
                    "GET /api/files/{file_id}/preview",
                    "GET /sandbox-api/browser/page",
                ],
            ),
            ProductAcceptanceItem(
                key="browser_vnc_observation",
                title="浏览器截图和 VNC 观察",
                category="tooling",
                status="needs_manual_check",
                evidence="BrowserTool 可打开页面和截图，VNC 面板可以观察沙箱浏览器实时画面。",
                verify_steps=[
                    "发送一个访问网页并截图的任务。",
                    "确认事件中出现 browser_open 或 browser_screenshot。",
                    "确认右侧远程桌面能看到浏览器画面。",
                ],
                related_routes=[
                    "GET /sandbox-api/browser/status",
                    "POST /sandbox-api/browser/page/navigate",
                    "GET /sandbox-api/vnc/status",
                ],
            ),
            ProductAcceptanceItem(
                key="mcp_a2a_events",
                title="MCP/A2A 进入工具事件流",
                category="tooling",
                status="ready",
                evidence="MCP 和 A2A 工具已经注册为 AgentTool，并通过 tool_called 事件进入统一事件流。",
                verify_steps=[
                    "调用 MCP 工具列表接口确认工具可发现。",
                    "调用 A2A 远程 Agent 列表接口确认远程 Agent 可发现。",
                    "发送需要外部工具协作的任务并观察 tool_called 事件。",
                ],
                related_routes=[
                    "GET /api/mcp/tools",
                    "GET /api/a2a/agents",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
        ]

        # ===================== 第3步：整理记忆、多 Agent、Harness 和异常恢复体验 =====================
        reliability_items = [
            ProductAcceptanceItem(
                key="context_and_memory",
                title="短期上下文和长期记忆",
                category="memory",
                status="ready",
                evidence="会话上下文接口会返回短期消息、事件摘要、文件引用和本次注入的长期记忆。",
                verify_steps=[
                    "创建一条长期记忆。",
                    "发送和记忆相关的新任务。",
                    "打开上下文抽屉确认 memory_context 中出现相关记忆。",
                ],
                related_routes=[
                    "GET /api/memories",
                    "POST /api/memories",
                    "GET /api/sessions/{session_id}/context",
                ],
            ),
            ProductAcceptanceItem(
                key="multi_agent_collaboration",
                title="多 Agent 协作",
                category="collaboration",
                status="ready",
                evidence="多 Agent 服务提供 manager、worker、reviewer 角色，并能生成分派、执行、评审和汇总结果。",
                verify_steps=[
                    "打开设置页查看多 Agent 模块。",
                    "调用多 Agent 角色接口确认角色配置。",
                    "发送适合拆分的任务，观察多 Agent 工具结果。",
                ],
                related_routes=[
                    "GET /api/multi-agent/roles",
                    "POST /api/multi-agent/run",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
            ProductAcceptanceItem(
                key="harness_regression",
                title="Harness 回归任务集",
                category="quality",
                status="ready",
                evidence="Harness 提供固定用例、模拟运行、断言和失败回放，适合重构后做回归检查。",
                verify_steps=[
                    "打开设置页的 Agent Harness 面板。",
                    "运行一条用例。",
                    "确认断言结果和事件回放可以展示。",
                ],
                related_routes=[
                    "GET /api/harness/cases",
                    "POST /api/harness/cases/{case_id}/run",
                    "GET /api/harness/runs/{run_id}/replay",
                ],
            ),
            ProductAcceptanceItem(
                key="failure_recovery",
                title="停止、失败、重试和恢复",
                category="reliability",
                status="ready",
                evidence="后台任务支持 waiting、completed、stopped 状态，失败任务可以重试，会话可以恢复最近任务状态。",
                verify_steps=[
                    "启动一个后台任务。",
                    "执行停止或制造失败。",
                    "调用重试接口并确认新任务关联 parent_task_id。",
                ],
                related_routes=[
                    "POST /api/sessions/tasks/{task_id}/retry",
                    "GET /api/sessions/{session_id}/tasks/latest",
                    "POST /api/sessions/{session_id}/stop",
                ],
            ),
            ProductAcceptanceItem(
                key="structured_error_experience",
                title="结构化错误体验",
                category="reliability",
                status="ready",
                evidence="API 错误响应和 task_error 事件包含错误类型、来源、用户提示、建议和 request_id。",
                verify_steps=[
                    "请求一个不存在的资源，例如 GET /api/sessions/not-a-real-id。",
                    "确认响应中包含 error.type、error.source、error.user_message、error.suggestion 和 request_id。",
                    "制造一次工具失败，确认对话流中显示用户可读错误和下一步建议。",
                ],
                related_routes=[
                    "GET /api/sessions/{session_id}",
                    "POST /api/sessions/{session_id}/messages/stream",
                    "GET /api/sessions/{session_id}/events",
                ],
            ),
            ProductAcceptanceItem(
                key="file_parsing_references",
                title="文件解析、摘要和引用片段",
                category="files",
                status="ready",
                evidence="文件预览接口会返回 file_type、parse_status、summary、references 和裁剪后的 content。",
                verify_steps=[
                    "上传 Markdown、代码、CSV 或 PDF 文件。",
                    "打开文件预览面板，确认出现解析摘要、类型、行数和引用片段。",
                    "调用文件预览接口，确认 references 中包含 label、excerpt 和行号。",
                ],
                related_routes=[
                    "POST /api/files",
                    "GET /api/files/{file_id}/preview",
                    "GET /api/sessions/{session_id}/files",
                ],
            ),
            ProductAcceptanceItem(
                key="final_answer_citations",
                title="最终回答引用体系",
                category="conversation",
                status="ready",
                evidence="task_done.final_answer 会整理总结、执行结果、证据与引用、产物和下一步建议。",
                verify_steps=[
                    "发送搜索总结、上传文件分析或生成文件任务。",
                    "确认最终回答显示 ## 总结、## 证据与引用、## 产物、## 下一步建议。",
                    "确认搜索来源、文件名或产物路径能在最终回答中看到。",
                ],
                related_routes=[
                    "POST /api/sessions/{session_id}/messages/stream",
                    "GET /api/sessions/{session_id}/events",
                    "GET /api/files/{file_id}/preview",
                ],
            ),
            ProductAcceptanceItem(
                key="compose_startup",
                title="Docker Compose 一键启动",
                category="deployment",
                status="needs_manual_check",
                evidence="生产启动脚本、Nginx、API、UI、Sandbox、PostgreSQL 和 Redis 已经进入 Compose 编排。",
                verify_steps=[
                    "执行 BUILD=true ./scripts/start.sh。",
                    "执行 curl http://localhost:8088/api/status。",
                    "访问 http://localhost:8088 完成一次页面任务验证。",
                ],
                related_routes=[
                    "GET /api/status",
                    "GET /api/status/database",
                    "GET /sandbox-api/status",
                ],
            ),
            ProductAcceptanceItem(
                key="documentation_quality",
                title="教程、注释和排查文档",
                category="learning",
                status="needs_manual_check",
                evidence="课程章节、架构文档、依赖说明、诊断清单和安全清单共同支撑二次开发。",
                verify_steps=[
                    "阅读第 49 章运行验证部分。",
                    "按验收清单逐项执行。",
                    "遇到问题时优先使用系统诊断和安全边界面板定位。",
                ],
                related_routes=[
                    "GET /api/observability/checks",
                    "GET /api/security/checks",
                    "GET /api/acceptance/checks",
                ],
            ),
        ]

        # ===================== 第4步：计算前端需要展示的验收汇总 =====================
        items = conversation_items + tool_items + reliability_items
        ready = len([item for item in items if item.status == "ready"])
        needs_manual_check = len(
            [item for item in items if item.status == "needs_manual_check"]
        )
        summary = ProductAcceptanceSummary(
            total=len(items),
            ready=ready,
            needs_manual_check=needs_manual_check,
        )
        return ProductAcceptanceChecklist(summary=summary, items=items)
