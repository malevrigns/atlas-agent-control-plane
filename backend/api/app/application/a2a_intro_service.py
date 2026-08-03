from uuid import uuid4

from app.core.exceptions import AppException
from app.domain.a2a.entities import (
    A2aAgentCard,
    A2aCapability,
    A2aMessageDemo,
    A2aMessagePart,
    A2aRole,
    A2aTaskStep,
)


class A2aIntroService:
    """第 34 章的 A2A 入门应用服务。

    A2A 解决的是 Agent 和 Agent 之间如何互相发现、发送任务、返回结果。
    本章先用确定性数据模拟 Agent Card 和 message/send，
    让读者理解协议边界。第 35 章再接入真实远程 Agent 调用。
    """

    # ===================== 第1步：解释 A2A 中的核心角色 =====================
    def list_roles(self) -> list[A2aRole]:
        """返回 Host、Remote Agent、Task 等概念说明。"""

        return [
            A2aRole(
                name="Host Agent",
                responsibility="发起任务的一方，负责选择远程 Agent、发送消息并接收结果。",
                system_mapping="AtlasAgent 主 API 中的 Agent Runner 或 A2A 工具调用方。",
            ),
            A2aRole(
                name="Remote Agent",
                responsibility="被调用的一方，接收任务并返回消息、状态或 artifact。",
                system_mapping="外部可协作 Agent，例如研究 Agent、代码 Agent、文档 Agent。",
            ),
            A2aRole(
                name="Agent Card",
                responsibility="描述远程 Agent 的名称、地址、能力和输入输出模式。",
                system_mapping="第 35 章会读取远程 Agent Card 并注册成可调用工具。",
            ),
            A2aRole(
                name="Task",
                responsibility="一次跨 Agent 协作任务，包含输入消息、执行状态和输出结果。",
                system_mapping="会进入当前会话事件流，让前端能观察远程 Agent 执行过程。",
            ),
        ]

    # ===================== 第2步：返回一个示例 Agent Card =====================
    def get_demo_agent_card(self) -> A2aAgentCard:
        """返回课程内置的示例 Agent Card。"""

        return A2aAgentCard(
            name="ResearchAssistantAgent",
            description="一个模拟的远程研究 Agent，擅长把问题拆成检索要点并返回摘要。",
            url="https://agents.example.com/research",
            version="0.1.0",
            capabilities=[
                A2aCapability(
                    name="research_brief",
                    description="根据用户问题整理研究摘要和后续建议。",
                    example="帮我调研某个技术方案的优缺点。",
                ),
                A2aCapability(
                    name="source_outline",
                    description="把资料来源整理成结构化提纲。",
                    example="把搜索结果整理成可写文章的大纲。",
                ),
            ],
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain", "application/json"],
        )

    # ===================== 第3步：模拟一次 message/send =====================
    def send_demo_message(self, message: str) -> A2aMessageDemo:
        """模拟 Host Agent 向 Remote Agent 发送一条任务消息。"""

        clean_message = message.strip()
        if not clean_message:
            raise AppException(
                message="a2a demo message is required",
                code=400,
                status_code=400,
            )

        card = self.get_demo_agent_card()
        task_id = f"a2a-demo-{uuid4()}"
        steps = [
            A2aTaskStep(
                index=1,
                action="read_agent_card",
                detail="Host 先读取远程 Agent Card，确认它的地址、能力和输入输出模式。",
            ),
            A2aTaskStep(
                index=2,
                action="select_remote_agent",
                detail=f"根据任务内容选择远程 Agent：{card.name}。",
            ),
            A2aTaskStep(
                index=3,
                action="message/send",
                detail="Host 把用户任务包装成 A2A message，并发送给远程 Agent。",
            ),
            A2aTaskStep(
                index=4,
                action="task_completed",
                detail="远程 Agent 返回任务状态和输出消息，Host 将结果写入会话事件。",
            ),
        ]

        output_text = (
            f"{card.name} 已接收任务：{clean_message}。"
            "这是第 34 章的模拟响应；第 35 章会接入真实远程 Agent 调用。"
        )
        return A2aMessageDemo(
            remote_agent=card.name,
            task_id=task_id,
            status="completed",
            input_message=[A2aMessagePart(kind="text", text=clean_message)],
            output_message=[A2aMessagePart(kind="text", text=output_text)],
            steps=steps,
        )

