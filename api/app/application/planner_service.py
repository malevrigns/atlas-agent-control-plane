import json
from uuid import UUID

from app.application.context_engineering_service import ContextEngineeringService
from app.application.llm_service import LLMService
from app.application.unit_of_work import UnitOfWork
from app.core.exceptions import AppException
from app.domain.agent_core.planner import (
    AgentPlan,
    PlanStep,
    create_agent_plan,
    create_plan_step,
)
from app.domain.llm.entities import LLMMessage
from app.domain.sessions.entities import SessionEvent, SessionEventType


class PlannerService:
    """第 18 章的 PlannerAgent 应用服务。

    它负责把用户任务转换成结构化计划，并把计划保存成 session event。
    """

    def __init__(
        self,
        uow: UnitOfWork,
        llm_service: LLMService | None = None,
    ) -> None:
        # ===================== 第1步：保存依赖 =====================
        self.uow = uow
        self.llm_service = llm_service or LLMService()

    # ===================== 第2步：生成计划并写入会话事件 =====================
    async def create_plan(
        self,
        session_id: UUID,
        task: str,
    ) -> tuple[AgentPlan, SessionEvent]:
        """为会话生成计划，并保存 plan_created 事件。"""

        clean_task = task.strip()
        if not clean_task:
            raise AppException(
                message="task is required",
                code=400,
                status_code=400,
            )

        session = await self.uow.sessions.get(session_id)
        if session is None:
            raise AppException(
                message="session not found",
                code=404,
                status_code=404,
            )

        # 3. 构建统一上下文快照。长期记忆检索会结合任务、会话标题和最近消息。
        context_snapshot = await ContextEngineeringService(self.uow).build_snapshot(
            session_id,
            task=clean_task,
        )
        agent_context = ContextEngineeringService.render_for_agent(context_snapshot)

        # 4. Planner 使用当前任务和压缩上下文生成计划。
        plan = await self._generate_plan(
            task=clean_task,
            agent_context=agent_context,
        )
        event = await self.uow.session_events.add(
            session_id=session_id,
            event_type=SessionEventType.plan_created,
            payload=self._plan_to_payload(
                plan,
                memory_ids=[
                    str(item.id)
                    for item in context_snapshot.memory_context.items
                ],
            ),
        )
        await self.uow.sessions.touch(session_id)
        await self.uow.commit()
        return plan, event

    # ===================== 第3步：优先使用 LLM 生成计划 =====================
    async def _generate_plan(
        self,
        *,
        task: str,
        agent_context: str,
    ) -> AgentPlan:
        """调用 LLM 生成结构化计划；不可用时返回教学 fallback。"""

        try:
            result = await self.llm_service.chat(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "你是一个 PlannerAgent。请把用户任务拆成 3 到 5 个可执行步骤。"
                            "只返回 JSON，不要返回 Markdown。JSON 格式为："
                            '{"title":"计划标题","goal":"目标","steps":['
                            '{"title":"步骤标题","description":"步骤说明","expected_output":"预期输出"}'
                            "]}\n\n"
                            "生成计划时必须遵守下面的压缩上下文；不要把上下文原样复制到计划：\n"
                            f"{agent_context or '暂无额外上下文'}"
                        ),
                    ),
                    LLMMessage(role="user", content=task),
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            return self._parse_llm_plan(task=task, content=result.content)
        except AppException:
            # 没配置 API Key 或 provider 出错时，仍然给出可运行的教学计划。
            # 这样第 18 章不会因为外部服务不可用而无法验证主流程。
            return self._build_fallback_plan(task)

    # ===================== 第4步：解析 LLM 返回的 JSON 计划 =====================
    def _parse_llm_plan(self, task: str, content: str) -> AgentPlan:
        """把模型返回文本解析成 AgentPlan。"""

        try:
            data = json.loads(self._strip_code_fence(content))
        except json.JSONDecodeError:
            return self._build_fallback_plan(task)

        steps = [
            create_plan_step(
                title=str(item.get("title", "")).strip() or "未命名步骤",
                description=str(item.get("description", "")).strip() or "补充步骤说明",
                expected_output=str(item.get("expected_output", "")).strip()
                or "完成该步骤的可检查结果",
            )
            for item in data.get("steps", [])
            if isinstance(item, dict)
        ]
        if not steps:
            return self._build_fallback_plan(task)

        return create_agent_plan(
            title=str(data.get("title", "")).strip() or "任务执行计划",
            goal=str(data.get("goal", "")).strip() or task,
            steps=steps[:5],
            source="llm",
        )

    # ===================== 第5步：处理模型可能返回的代码块包裹 =====================
    def _strip_code_fence(self, content: str) -> str:
        """去掉 ```json ... ``` 这类包裹，提升 JSON 解析成功率。"""

        clean_content = content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return clean_content

    # ===================== 第6步：提供稳定 fallback 计划 =====================
    def _build_fallback_plan(self, task: str) -> AgentPlan:
        """外部模型不可用时，生成稳定的教学计划。"""

        steps: list[PlanStep] = [
            create_plan_step(
                title="明确任务目标",
                description=f"梳理“{task}”的最终交付物、边界和验收标准。",
                expected_output="得到清晰的目标描述和验收清单。",
            ),
            create_plan_step(
                title="拆解执行步骤",
                description="把任务拆成几个可以独立完成和验证的小步骤。",
                expected_output="得到可执行的步骤列表。",
            ),
            create_plan_step(
                title="逐步实现和检查",
                description="按步骤完成任务，并在每一步后检查输出是否符合预期。",
                expected_output="得到可运行、可检查的阶段结果。",
            ),
            create_plan_step(
                title="总结结果和下一步",
                description="整理最终输出、风险点和后续可以继续扩展的方向。",
                expected_output="得到最终总结和后续建议。",
            ),
        ]
        return create_agent_plan(
            title="任务执行计划",
            goal=task,
            steps=steps,
            source="fallback",
        )

    # ===================== 第7步：把 AgentPlan 转成事件 payload =====================
    def _plan_to_payload(
        self,
        plan: AgentPlan,
        *,
        memory_ids: list[str],
    ) -> dict:
        """把计划对象转换成可以存入 JSONB 的字典。"""

        return {
            "id": str(plan.id),
            "plan_id": str(plan.id),
            "title": plan.title,
            "goal": plan.goal,
            "source": plan.source,
            # 记录本次规划实际注入了哪些长期记忆，便于事件回放和排查。
            "memory_ids": memory_ids,
            "memory_count": len(memory_ids),
            "steps": [
                {
                    "id": str(step.id),
                    "title": step.title,
                    "description": step.description,
                    "expected_output": step.expected_output,
                    "status": step.status.value,
                }
                for step in plan.steps
            ],
        }
