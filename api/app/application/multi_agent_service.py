from app.domain.multi_agent.entities import (
    MultiAgentReview,
    MultiAgentRole,
    MultiAgentRunResult,
    MultiAgentSubTask,
)


class MultiAgentService:
    """多 Agent 协作编排服务。

    当前版本先实现确定性的 Manager / Worker / Reviewer 协作闭环。
    后续章节会继续把这里升级为更完整的 Agent Runner 和 Harness。
    """

    # ===================== 第1步：定义协作角色 =====================
    def list_roles(self) -> list[MultiAgentRole]:
        """返回当前系统内置的多 Agent 角色。"""

        # 1. 角色定义放在应用服务中，方便 API、工具和前端复用。
        # 2. 当前版本先固定三类角色，后续设置页会把角色配置抽到可编辑配置中。
        return [
            MultiAgentRole(
                key="manager",
                name="Manager Agent",
                responsibility="理解用户目标，拆解子任务，并决定谁来执行。",
                capability="任务拆解、角色分派、结果汇总。",
            ),
            MultiAgentRole(
                key="worker",
                name="Worker Agent",
                responsibility="执行 Manager 分派的具体子任务。",
                capability="资料整理、方案生成、局部执行。",
            ),
            MultiAgentRole(
                key="reviewer",
                name="Reviewer Agent",
                responsibility="检查 Worker 输出是否满足目标，并给出改进意见。",
                capability="质量评审、风险检查、遗漏补充。",
            ),
        ]

    # ===================== 第2步：运行一次多 Agent 协作 =====================
    def run_collaboration(self, task: str) -> MultiAgentRunResult:
        """围绕一个任务运行 Manager -> Worker -> Reviewer -> 汇总流程。"""

        # 1. 清理任务文本。多 Agent 协作至少需要一个明确目标。
        clean_task = " ".join(task.split())
        if not clean_task:
            clean_task = "整理当前任务的目标、执行步骤和验收标准。"

        # 2. Manager Agent 拆解任务。
        #    当前版本用确定性规则生成子任务，保证本地验证稳定可复现。
        subtasks = self._plan_subtasks(clean_task)

        # 3. Worker Agent 执行子任务。
        #    这里先用字符串模拟 Worker 输出，后续会替换成真实子 Agent 执行。
        completed_subtasks = [
            self._run_worker_task(subtask, clean_task)
            for subtask in subtasks
        ]

        # 4. Reviewer Agent 评审结果。
        #    评审信息会进入前端工具预览，帮助用户看到“不是只执行，还要检查”。
        review = self._review_outputs(completed_subtasks)

        # 5. Manager Agent 汇总最终回答。
        final_answer = self._summarize(clean_task, completed_subtasks, review)

        # 6. 统一返回结果。AgentTool 会把它序列化为 kind=multi_agent_result。
        return MultiAgentRunResult(
            kind="multi_agent_result",
            task=clean_task,
            manager="Manager Agent",
            roles=self.list_roles(),
            subtasks=completed_subtasks,
            review=review,
            final_answer=final_answer,
        )

    # ===================== 第3步：Manager 拆解子任务 =====================
    def _plan_subtasks(self, task: str) -> list[MultiAgentSubTask]:
        """把用户任务拆成几个可分派子任务。"""

        # 1. 第一个 Worker 负责目标和背景，避免后续直接给方案但不知道为什么做。
        # 2. 第二个 Worker 负责执行方案，形成可落地的步骤。
        # 3. 第三个 Worker 负责验收标准，帮助 Reviewer 检查结果。
        return [
            MultiAgentSubTask(
                id="subtask-1",
                assignee="Worker Agent / Researcher",
                title="梳理任务目标和背景",
                instruction=f"围绕“{task}”提取目标、约束和已知信息。",
                expected_output="目标、约束、关键背景。",
                status="pending",
                output="",
            ),
            MultiAgentSubTask(
                id="subtask-2",
                assignee="Worker Agent / Planner",
                title="生成执行方案",
                instruction=f"为“{task}”设计可执行步骤。",
                expected_output="分阶段执行步骤。",
                status="pending",
                output="",
            ),
            MultiAgentSubTask(
                id="subtask-3",
                assignee="Worker Agent / QA",
                title="定义验收标准",
                instruction=f"检查“{task}”完成后应该满足哪些标准。",
                expected_output="验收清单和风险提示。",
                status="pending",
                output="",
            ),
        ]

    # ===================== 第4步：Worker 执行子任务 =====================
    def _run_worker_task(
        self,
        subtask: MultiAgentSubTask,
        task: str,
    ) -> MultiAgentSubTask:
        """模拟 Worker Agent 执行一个子任务。"""

        # 1. 根据子任务类型生成稳定输出。
        #    当前阶段重点是协作编排，不在这里调用真实 LLM。
        if "目标" in subtask.title:
            output = f"目标：围绕“{task}”形成可执行结果；约束：结果需要清晰、可验证、可继续扩展。"
        elif "方案" in subtask.title:
            output = "方案：先拆目标，再执行关键步骤，最后用验收标准检查输出是否完整。"
        else:
            output = "验收：结果应包含目标说明、执行步骤、风险提示和最终总结。"

        # 2. 返回新的 completed 子任务对象。
        #    不直接修改原对象，便于理解“输入任务”和“执行结果”的区别。
        return MultiAgentSubTask(
            id=subtask.id,
            assignee=subtask.assignee,
            title=subtask.title,
            instruction=subtask.instruction,
            expected_output=subtask.expected_output,
            status="completed",
            output=output,
        )

    # ===================== 第5步：Reviewer 评审输出 =====================
    def _review_outputs(self, subtasks: list[MultiAgentSubTask]) -> MultiAgentReview:
        """检查 Worker 输出是否完整。"""

        # 1. 找出没有输出的子任务。
        missing = [subtask.title for subtask in subtasks if not subtask.output.strip()]

        # 2. 根据缺失情况给出评审状态和意见。
        if missing:
            return MultiAgentReview(
                reviewer="Reviewer Agent",
                status="needs_revision",
                comments=[f"以下子任务缺少输出：{', '.join(missing)}"],
                improvement="重新执行缺少输出的子任务后再汇总。",
            )

        # 3. 所有 Worker 都有输出时，给出通过意见。
        return MultiAgentReview(
            reviewer="Reviewer Agent",
            status="approved",
            comments=[
                "子任务输出完整。",
                "执行方案和验收标准可以支撑最终汇总。",
            ],
            improvement="后续可以接入真实 LLM，让 Reviewer 给出更细粒度的质量评分。",
        )

    # ===================== 第6步：Manager 汇总最终答案 =====================
    def _summarize(
        self,
        task: str,
        subtasks: list[MultiAgentSubTask],
        review: MultiAgentReview,
    ) -> str:
        """把 Worker 输出和 Reviewer 评审汇总成最终答案。"""

        # 1. 提取每个 Worker 的输出摘要。
        parts = [f"- {subtask.title}：{subtask.output}" for subtask in subtasks]

        # 2. 组合最终回答。
        #    这里保留 review.status，让前端和用户知道结果是否通过评审。
        return "\n".join(
            [
                f"多 Agent 协作已完成：{task}",
                *parts,
                f"评审状态：{review.status}",
                f"改进建议：{review.improvement}",
            ]
        )
