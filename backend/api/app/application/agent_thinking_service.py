from app.core.exceptions import AppException
from app.domain.agent_thinking.entities import (
    ThinkingComparison,
    ThinkingMode,
    ThinkingModeDemo,
    ThinkingModeInfo,
)


# ===================== 第1步：准备思维模式的固定说明 =====================
# 这些信息不依赖 LLM，也不依赖数据库，适合放在应用服务中作为教学演示数据。
MODE_INFOS: tuple[ThinkingModeInfo, ...] = (
    ThinkingModeInfo(
        mode=ThinkingMode.chatbot,
        name="普通 ChatBot",
        summary="直接根据用户输入生成回答，适合简单问答和短文本改写。",
        best_for="问题明确、步骤很少、不需要外部工具的任务",
        risk="容易把复杂任务一次性回答完，缺少过程控制和可检查节点。",
    ),
    ThinkingModeInfo(
        mode=ThinkingMode.cot,
        name="CoT 思考摘要",
        summary="先梳理任务要点，再给出答案，适合需要多步分析的问题。",
        best_for="推理、比较、方案设计、需要解释原因的任务",
        risk="如果没有约束，过程可能变长，也可能把不确定内容说得过满。",
    ),
    ThinkingModeInfo(
        mode=ThinkingMode.react,
        name="ReAct",
        summary="在思考和行动之间循环：观察任务、决定动作、拿到结果、继续判断。",
        best_for="需要搜索、读文件、执行命令、调用工具的任务",
        risk="工具调用边界和错误处理必须清楚，否则会造成无效循环。",
    ),
    ThinkingModeInfo(
        mode=ThinkingMode.decomposition,
        name="任务拆解",
        summary="把大任务拆成多个可执行步骤，适合 PlannerAgent 生成计划。",
        best_for="长任务、工程任务、需要多人或多 Agent 协作的任务",
        risk="拆得太粗会不可执行，拆得太细会增加调度和上下文成本。",
    ),
)


class AgentThinkingService:
    """第 16 章的 Agent 思维模型演示服务。

    本章不调用真实 LLM，而是用确定性规则生成演示内容。
    这样可以让你先理解 ChatBot、CoT、ReAct 和任务拆解的区别，
    不会被 API Key、模型随机性或网络问题打断。
    """

    # ===================== 第2步：提供模式列表给前端展示 =====================
    def list_modes(self) -> list[ThinkingModeInfo]:
        """返回全部思维模式说明。"""

        return list(MODE_INFOS)

    # ===================== 第3步：对同一个任务生成多模式对比 =====================
    def compare(self, task: str) -> ThinkingComparison:
        """生成一个可观察的 Agent 思维模式对比结果。"""

        clean_task = task.strip()
        if not clean_task:
            raise AppException(
                message="task is required",
                code=400,
                status_code=400,
            )

        demos = [
            self._build_chatbot_demo(clean_task),
            self._build_cot_demo(clean_task),
            self._build_react_demo(clean_task),
            self._build_decomposition_demo(clean_task),
        ]
        return ThinkingComparison(task=clean_task, demos=demos)

    # ===================== 第4步：普通 ChatBot 演示 =====================
    def _build_chatbot_demo(self, task: str) -> ThinkingModeDemo:
        """普通 ChatBot 的特点是直接回答，不显式规划步骤。"""

        return ThinkingModeDemo(
            mode=ThinkingMode.chatbot,
            name="普通 ChatBot",
            headline="直接给出一个整体回答",
            steps=[
                "读取用户任务",
                "根据已有上下文直接生成回复",
            ],
            tool_calls=[],
            final_answer=f"可以直接围绕“{task}”给出一个简明方案，但过程检查点较少。",
        )

    # ===================== 第5步：CoT 思考摘要演示 =====================
    def _build_cot_demo(self, task: str) -> ThinkingModeDemo:
        """CoT 适合把复杂问题先整理成可解释的分析摘要。"""

        return ThinkingModeDemo(
            mode=ThinkingMode.cot,
            name="CoT 思考摘要",
            headline="先分析任务，再组织答案",
            steps=[
                "确认任务目标和交付物",
                "列出影响方案的关键约束",
                "按优先级组织回答结构",
                "输出结论和下一步建议",
            ],
            tool_calls=[],
            final_answer=f"处理“{task}”时，可以先明确目标、约束和评价标准，再给出分步骤方案。",
        )

    # ===================== 第6步：ReAct 演示 =====================
    def _build_react_demo(self, task: str) -> ThinkingModeDemo:
        """ReAct 强调一边判断一边行动，行动通常对应工具调用。"""

        return ThinkingModeDemo(
            mode=ThinkingMode.react,
            name="ReAct",
            headline="思考和行动交替推进",
            steps=[
                "观察当前任务是否需要外部信息",
                "选择合适工具获取信息或执行动作",
                "读取工具结果并判断是否足够",
                "继续调用工具或生成最终回答",
            ],
            tool_calls=[
                "search(query)",
                "read_file(path)",
                "run_command(command)",
            ],
            final_answer=f"如果“{task}”需要实时资料、文件内容或命令结果，ReAct 会比直接回答更可靠。",
        )

    # ===================== 第7步：任务拆解演示 =====================
    def _build_decomposition_demo(self, task: str) -> ThinkingModeDemo:
        """任务拆解是 PlannerAgent 的前置能力。"""

        return ThinkingModeDemo(
            mode=ThinkingMode.decomposition,
            name="任务拆解",
            headline="把大任务拆成可执行计划",
            steps=[
                "定义最终目标",
                "拆出 3 到 5 个阶段任务",
                "为每个阶段标记输入和输出",
                "交给执行 Agent 按步骤完成",
            ],
            tool_calls=[],
            final_answer=f"可以把“{task}”拆成调研、设计、实现、验证和总结几个阶段逐步推进。",
        )

