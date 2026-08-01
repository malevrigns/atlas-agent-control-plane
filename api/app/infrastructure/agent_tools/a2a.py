import json

from app.application.a2a_service import A2aService
from app.domain.a2a.entities import A2aTaskResult
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    ToolRiskLevel,
)


def register_a2a_tools(
    registry: ToolRegistry,
    service: A2aService | None = None,
) -> None:
    """把 A2A 远程 Agent 调用入口注册成 AgentTool。

    第 35 章先注册一个通用 `a2a_call`。它通过 agent_key + message
    调用配置文件中的远程 Agent。后续多 Agent 编排章节会把不同角色
    组织成更完整的协作流程。
    """

    # 1. 创建或复用 A2A 应用服务。
    #    测试时可以传入 fake service，生产默认读取配置文件。
    a2a_service = service or A2aService()

    # 2. 注册一个通用 AgentTool。
    #    ReAct 执行计划时只需要知道工具名和参数 schema，不需要知道 A2A client 细节。
    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="a2a_call",
                description="调用一个已配置 A2A 远程 Agent 完成协作任务。",
                risk_level=ToolRiskLevel.high,
                required_permissions=("integration:a2a",),
                idempotent=False,
                parameters=[
                    ToolParameter(
                        name="agent_key",
                        type="string",
                        description="A2A Agent 配置 key，例如 demo_researcher。",
                        required=False,
                    ),
                    ToolParameter(
                        name="message",
                        type="string",
                        description="要发送给远程 Agent 的任务消息。",
                    ),
                ],
            ),
            # 3. handler 是工具真正执行入口。
            #    AgentTool 会先校验参数，再把 agent_key/message 传给这里。
            handler=lambda agent_key="", message="": _format_a2a_result(
                a2a_service.send_message(
                    agent_key=str(agent_key or "") or None,
                    message=str(message),
                )
            ),
        )
    )


def _format_a2a_result(result: A2aTaskResult) -> str:
    """把 A2A 调用结果格式化成前端工具预览可识别的 JSON。"""

    # 1. 工具 output 目前是字符串，所以先把结构化结果序列化成 JSON。
    # 2. kind 是前端判断展示方式的关键字段；没有它就只能显示普通文本。
    # 3. input/output/steps 都保留下来，方便用户观察远程 Agent 的协作过程。
    return json.dumps(
        {
            "kind": "a2a_task_result",
            "agent_key": result.agent_key,
            "remote_agent": result.remote_agent,
            "task_id": result.task_id,
            "status": result.status,
            "input_message": [
                {"kind": part.kind, "text": part.text}
                for part in result.input_message
            ],
            "output_message": [
                {"kind": part.kind, "text": part.text}
                for part in result.output_message
            ],
            "steps": [
                {
                    "index": step.index,
                    "action": step.action,
                    "detail": step.detail,
                }
                for step in result.steps
            ],
        },
        ensure_ascii=False,
    )
