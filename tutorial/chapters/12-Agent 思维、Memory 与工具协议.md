# 第十二章. Agent 思维、Memory 与工具协议

## 12.1 Agent 思维模型立论

### 12.1.1 本节目标
​        第 11 章让项目具备了调用 LLM 的基础能力，但“能调用模型”和“具备 Agent 能力”不是同一件事。普通聊天调用通常只是一问一答，而复杂 Agent 需要理解目标、拆解步骤、选择工具、观察结果，再决定是否继续执行。本节先不急着接真实模型，而是用一个稳定的演示模块，把几种典型思维模式放在同一个页面里对比。
​        本节会区分普通 ChatBot、CoT、ReAct 和任务拆解，并实现一个不依赖 API Key 的 Agent 思维模型演示服务。后端暴露模式说明接口和任务对比接口，前端通过独立 API、store、hook 和组件展示同一个任务在不同模式下的处理差异。这样读者可以先看清概念边界，再进入后续真实 Agent 调用循环。

### 12.1.2 最终效果
​        本节结束后，后端新增两个接口：

```Plain
GET  /api/agent-thinking/modes
POST /api/agent-thinking/compare
```

​        前端首页会新增一个“Agent 思维模型”面板。
​        访问：

```Plain
http://localhost:8088
```

​        可以输入任务：

```Plain
帮我从 0 到 1 实现一个 AI Agent 项目
```

​        点击“生成对比”后，页面会展示四种处理方式：

```Plain
普通 ChatBot
CoT 思考摘要
ReAct
任务拆解
```

​        本节先不调用真实 LLM。第 11 章已经完成了 LLM 客户端，但本节的重点是理解 Agent 的思维结构。如果一上来就把模型调用、提示词、工具调用、流式输出全部混在一起，会很难看清每个概念的边界。

### 12.1.3 本节要解决的问题
​        第 11 章已经可以调用 LLM，但直接调用 LLM 还不是 Agent。
​        普通聊天调用的链路是：

```Plain
用户输入
  |
  v
LLM
  |
  v
模型回答
```

​        Agent 的链路通常更复杂：

```Plain
用户任务
  |
  v
理解目标
  |
  v
拆解步骤
  |
  v
选择工具
  |
  v
执行和观察结果
  |
  v
继续判断或结束
```

​        这就是为什么需要先理解几种基本思维模型。

### 12.1.4 本节技术方案
​        本节新增一个独立模块：

```Plain
backend/api/app/domain/agent_thinking
backend/api/app/application/agent_thinking_service.py
backend/api/app/api/routes/agent_thinking.py
frontend/web/app/lib/agent-thinking-api.ts
frontend/web/app/stores/agent-thinking-store.ts
frontend/web/app/hooks/use-agent-thinking.ts
frontend/web/app/components/agent-thinking-panel.tsx
```

​        后端调用链路：

```Plain
Route
  |
  v
AgentThinkingService
  |
  v
确定性演示数据
```

​        前端调用链路：

```Plain
AgentThinkingPanel
  |
  v
useAgentThinking
  |
  v
useAgentThinkingStore
  |
  v
agent-thinking-api
  |
  v
/api/agent-thinking/*
```

​        本节选择确定性演示，不调用真实 LLM，原因是：
​        这样做有两个好处。首先，它不需要 API Key，也不会受到模型随机性和网络状态影响，每次点击都能得到稳定结果，适合用来理解概念。其次，它把 ChatBot、CoT、ReAct 和任务拆解的差异放在同一张页面里，让后续接入 PlannerAgent 和 ReActAgent 时有一个清楚的参照。

### 12.1.5 新增和修改的文件

```Plain
README.md
backend/api/README.md
backend/api/app/api/router.py
backend/api/app/api/routes/agent_thinking.py
backend/api/app/application/agent_thinking_service.py
backend/api/app/domain/agent_thinking/__init__.py
backend/api/app/domain/agent_thinking/entities.py
backend/api/app/schemas/agent_thinking.py
frontend/web/README.md
frontend/web/app/components/agent-thinking-panel.tsx
frontend/web/app/hooks/use-agent-thinking.ts
frontend/web/app/lib/agent-thinking-api.ts
frontend/web/app/page.tsx
frontend/web/app/stores/agent-thinking-store.ts
frontend/web/app/types.ts
```

### 12.1.6 实施步骤
#### 12.1.6.1 定义 Agent 思维领域实体
​        创建 `backend/api/app/domain/agent_thinking/__init__.py`：

```Python
"""Agent thinking domain objects."""
```

​        创建 `backend/api/app/domain/agent_thinking/entities.py`：

```Python
from dataclasses import dataclass
from enum import StrEnum

# ===================== 第1步：定义本章要对比的 Agent 思维模式 =====================
class ThinkingMode(StrEnum):
    """Agent 从用户任务到输出结果时，可以采用的几种典型思考方式。"""

    chatbot = "chatbot"
    cot = "cot"
    react = "react"
    decomposition = "decomposition"

# ===================== 第2步：定义单个模式的静态说明 =====================
@dataclass(slots=True)
class ThinkingModeInfo:
    """页面上展示的模式介绍，不依赖某一次具体任务。"""

    mode: ThinkingMode
    name: str
    summary: str
    best_for: str
    risk: str

# ===================== 第3步：定义单个模式针对任务生成的演示结果 =====================
@dataclass(slots=True)
class ThinkingModeDemo:
    """某个思维模式对同一个任务的处理过程。

    这里的 steps 是“可展示的推理摘要”，不是隐藏思维链。真实生产系统中，
    不应该把模型的完整隐藏推理过程直接暴露给用户。
    """

    mode: ThinkingMode
    name: str
    headline: str
    steps: list[str]
    tool_calls: list[str]
    final_answer: str

# ===================== 第4步：定义一次对比演示的整体结果 =====================
@dataclass(slots=True)
class ThinkingComparison:
    """同一个任务在多种模式下的对比结果。"""

    task: str
    demos: list[ThinkingModeDemo]
```

.1.6.1.1 代码讲解
​        这个文件属于领域层，负责定义“业务概念”，不负责 HTTP、数据库或页面展示。
​        `ThinkingMode` 是枚举，表示系统当前支持的四种思维模式。使用枚举的好处是避免到处写散落的字符串，例如 `"react"` 或 `"decomposition"`。后续如果要新增 `planner`，只需要先从这里扩展。
​        `ThinkingModeInfo` 用于模式介绍页。它回答的是：

```Plain
这个模式是什么
适合什么任务
有什么风险
```

​        `ThinkingModeDemo` 用于某一次任务演示。它回答的是：

```Plain
同一个任务，在这个模式下会怎么处理
会不会调用工具
最后会给出什么样的结论
```

​        这里特意写了 `steps` 是“可展示的推理摘要”。原因是 Agent 产品可以展示过程摘要、执行步骤、工具调用记录，但不应该默认展示模型隐藏思维链。实际产品里常见做法是展示：

```Plain
计划
步骤
工具输入输出摘要
结论
```

​        而不是把模型自身的全部隐式推理原样显示。

#### 12.1.6.2 编写 AgentThinkingService
​        创建 `backend/api/app/application/agent_thinking_service.py`：

```Python
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
```

.1.6.2.1 代码讲解
​        `MODE_INFOS` 是模式说明。它是固定数据，所以本节不需要建表。
​        `list_modes()` 给前端页面加载右侧模式说明。这个接口不需要请求体。
​        `compare()` 是本节的核心入口。业务流程是：

```Plain
接收 task
  |
  v
去掉首尾空格
  |
  v
如果为空，抛出统一业务异常
  |
  v
分别生成四种模式的 demo
  |
  v
返回 ThinkingComparison
```

​        四个 `_build_*_demo()` 方法分别模拟四种思路：
​        `chatbot` 代表直接回答，适合简单问答；`cot` 代表先整理分析摘要再回答，适合需要解释和比较的任务；`react` 把工具调用纳入决策过程，强调观察、行动和反馈；`decomposition` 则把大任务拆成计划步骤，是后续 PlannerAgent 的基础。
​        这里的 `_build_react_demo()` 已经提前出现了工具名：

```Plain
search(query)
read_file(path)
run_command(command)
```

​        这些工具还没有真正实现。现在只是让你先看到 ReAct 为什么离不开工具协议。本章后文会正式进入 Memory 和工具协议。

#### 12.1.6.3 定义接口 Schema
​        创建 `backend/api/app/schemas/agent_thinking.py`：

```Python
from pydantic import BaseModel, Field

# ===================== 第1步：定义模式说明响应 =====================
class ThinkingModeResponse(BaseModel):
    mode: str
    name: str
    summary: str
    best_for: str
    risk: str

class ThinkingModeListResponse(BaseModel):
    items: list[ThinkingModeResponse]

# ===================== 第2步：定义对比请求 =====================
class ThinkingCompareRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)

# ===================== 第3步：定义单个模式的演示结果 =====================
class ThinkingModeDemoResponse(BaseModel):
    mode: str
    name: str
    headline: str
    steps: list[str]
    tool_calls: list[str]
    final_answer: str

# ===================== 第4步：定义整体对比响应 =====================
class ThinkingComparisonResponse(BaseModel):
    task: str
    demos: list[ThinkingModeDemoResponse]
```

.1.6.3.1 代码讲解
​        Schema 是 API 边界层。领域实体是后端自己用的结构，Schema 是接口返回给前端的结构。
​        `ThinkingCompareRequest` 使用：

```Python
Field(min_length=1, max_length=1000)
```

​        这表示任务不能为空，也不能无限长。这样可以提前挡住明显不合理的请求。
​        `ThinkingComparisonResponse` 里包含：

```Plain
task   当前任务
demos  四种模式的对比结果
```

​        前端不需要理解领域对象，只要按照这个响应结构渲染即可。

#### 12.1.6.4 编写 API 路由
​        创建 `backend/api/app/api/routes/agent_thinking.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.agent_thinking_service import AgentThinkingService
from app.domain.agent_thinking.entities import (
    ThinkingComparison,
    ThinkingModeDemo,
    ThinkingModeInfo,
)
from app.schemas.agent_thinking import (
    ThinkingCompareRequest,
    ThinkingComparisonResponse,
    ThinkingModeDemoResponse,
    ThinkingModeListResponse,
    ThinkingModeResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/agent-thinking", tags=["agent-thinking"])

# ===================== 第1步：创建应用服务依赖 =====================
def build_agent_thinking_service() -> AgentThinkingService:
    """创建 AgentThinkingService。

    当前服务没有数据库连接，也没有外部 HTTP 客户端，所以可以直接实例化。
    后续如果接入真实 Agent 配置，再在这里注入依赖。
    """

    return AgentThinkingService()

# ===================== 第2步：把领域对象转换成接口响应 =====================
def to_mode_response(mode: ThinkingModeInfo) -> ThinkingModeResponse:
    """把领域层的模式说明转换成 API schema。"""

    return ThinkingModeResponse(
        mode=mode.mode.value,
        name=mode.name,
        summary=mode.summary,
        best_for=mode.best_for,
        risk=mode.risk,
    )

def to_demo_response(demo: ThinkingModeDemo) -> ThinkingModeDemoResponse:
    """把单个模式的演示结果转换成前端需要的结构。"""

    return ThinkingModeDemoResponse(
        mode=demo.mode.value,
        name=demo.name,
        headline=demo.headline,
        steps=demo.steps,
        tool_calls=demo.tool_calls,
        final_answer=demo.final_answer,
    )

def to_comparison_response(
    comparison: ThinkingComparison,
) -> ThinkingComparisonResponse:
    """把整体对比结果转换成统一响应 data。"""

    return ThinkingComparisonResponse(
        task=comparison.task,
        demos=[to_demo_response(demo) for demo in comparison.demos],
    )

# ===================== 第3步：提供模式列表接口 =====================
@router.get("/modes", response_model=ApiResponse[ThinkingModeListResponse])
async def list_modes(
    service: AgentThinkingService = Depends(build_agent_thinking_service),
) -> ApiResponse[ThinkingModeListResponse]:
    """返回 ChatBot、CoT、ReAct 和任务拆解的基础说明。"""

    modes = service.list_modes()
    return ApiResponse(
        data=ThinkingModeListResponse(
            items=[to_mode_response(mode) for mode in modes],
        )
    )

# ===================== 第4步：提供任务对比接口 =====================
@router.post("/compare", response_model=ApiResponse[ThinkingComparisonResponse])
async def compare_thinking_modes(
    payload: ThinkingCompareRequest,
    service: AgentThinkingService = Depends(build_agent_thinking_service),
) -> ApiResponse[ThinkingComparisonResponse]:
    """对同一个任务生成多种 Agent 思维模式的可视化对比。"""

    comparison = service.compare(payload.task)
    return ApiResponse(data=to_comparison_response(comparison))
```

.1.6.4.1 代码讲解
​        路由层只做三件事：

```Plain
接收请求
调用应用服务
转换响应
```

​        `build_agent_thinking_service()` 是 FastAPI 依赖函数。虽然现在只是 `return AgentThinkingService()`，但保留这个依赖函数有一个好处：后续如果这个服务需要数据库、LLM 客户端或工具注册表，不需要改路由函数签名。
​        `to_mode_response()`、`to_demo_response()`、`to_comparison_response()` 是转换函数。它们把领域对象转换成 API Schema。
​        为什么不直接返回领域对象？
​        因为领域对象服务于业务，接口对象服务于前端。两者分开以后，后端业务结构可以调整，而不轻易破坏前端接口。

#### 12.1.6.5 注册路由
​        打开 `backend/api/app/api/router.py`：

```Python
from fastapi import APIRouter

from app.api.routes import agent_thinking, config, files, llm, sessions, status

api_router = APIRouter()
api_router.include_router(status.router)
api_router.include_router(sessions.router)
api_router.include_router(files.router)
api_router.include_router(config.router)
api_router.include_router(llm.router)
api_router.include_router(agent_thinking.router)
```

.1.6.5.1 代码讲解
​        新增路由文件后，必须在总路由里注册。
​        如果忘了这一步，文件虽然存在，但接口不会出现在 FastAPI 应用中。访问：

```Plain
/api/agent-thinking/modes
```

​        会返回 404。

#### 12.1.6.6 扩展前端类型
​        打开 `frontend/web/app/types.ts`，新增：

```TypeScript
export type ThinkingModeInfo = {
  mode: string;
  name: string;
  summary: string;
  best_for: string;
  risk: string;
};

export type ThinkingModeListData = {
  items: ThinkingModeInfo[];
};

export type ThinkingModeDemo = {
  mode: string;
  name: string;
  headline: string;
  steps: string[];
  tool_calls: string[];
  final_answer: string;
};

export type ThinkingComparisonData = {
  task: string;
  demos: ThinkingModeDemo[];
};
```

.1.6.6.1 代码讲解
​        前端类型要和后端 Schema 对齐。
​        这里的结构关系是：

```Plain
ThinkingComparisonData
  |
  +-- task
  +-- demos: ThinkingModeDemo[]
```

​        页面渲染时，会对 `demos` 做循环，为每一种模式渲染一张卡片。

#### 12.1.6.7 封装前端 API 请求
​        创建 `frontend/web/app/lib/agent-thinking-api.ts`：

```TypeScript
import { requestApi } from "./api";
import type {
  ThinkingComparisonData,
  ThinkingModeListData,
} from "../types";

// ===================== 第1步：读取思维模式说明 =====================
export function fetchThinkingModes() {
  return requestApi<ThinkingModeListData>("/api/agent-thinking/modes").then(
    (data) => data.items,
  );
}

// ===================== 第2步：提交任务并生成多模式对比 =====================
export function compareThinkingModes(task: string) {
  return requestApi<ThinkingComparisonData>("/api/agent-thinking/compare", {
    method: "POST",
    body: JSON.stringify({ task }),
  });
}
```

.1.6.7.1 代码讲解
​        组件不应该直接写：

```TypeScript
fetch("/api/agent-thinking/compare")
```

​        原因是接口路径、统一响应解析和错误处理都属于 API 层职责。统一放到 `lib/agent-thinking-api.ts` 后，组件只关心“加载模式”和“生成对比”两个动作。

#### 12.1.6.8 创建独立 zustand store
​        创建 `frontend/web/app/stores/agent-thinking-store.ts`：

```TypeScript
import { create } from "zustand";

import {
  compareThinkingModes,
  fetchThinkingModes,
} from "../lib/agent-thinking-api";
import type {
  LoadState,
  ThinkingComparisonData,
  ThinkingModeInfo,
} from "../types";

type AgentThinkingState = {
  comparison: LoadState<ThinkingComparisonData | null>;
  modes: LoadState<ThinkingModeInfo[]>;
  running: boolean;
  task: string;
};

type AgentThinkingActions = {
  loadModes: () => Promise<void>;
  runComparison: () => Promise<void>;
  setTask: (task: string) => void;
};

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "unknown error";
}

// ===================== 第1步：创建独立的 Agent 思维 store =====================
// 不把这部分状态塞进 session-store，是为了让“会话聊天”和“思维模型演示”
// 保持边界清楚。后续第 17 章开始写真实 Agent 时，也更容易迁移。
export const useAgentThinkingStore = create<
  AgentThinkingState & AgentThinkingActions
>((set, get) => ({
  comparison: { type: "ready", data: null },
  modes: { type: "loading" },
  running: false,
  task: "帮我从 0 到 1 实现一个 AI Agent 项目",

  setTask: (task) => set({ task }),

  // ===================== 第2步：页面打开时加载模式说明 =====================
  loadModes: async () => {
    set({ modes: { type: "loading" } });
    try {
      const modes = await fetchThinkingModes();
      set({ modes: { type: "ready", data: modes } });
    } catch (error) {
      set({ modes: { type: "error", message: getErrorMessage(error) } });
    }
  },

  // ===================== 第3步：提交任务并刷新对比结果 =====================
  runComparison: async () => {
    const task = get().task.trim();
    if (!task) {
      set({
        comparison: { type: "error", message: "请输入一个要分析的任务" },
      });
      return;
    }

    set({ comparison: { type: "loading" }, running: true });
    try {
      const comparison = await compareThinkingModes(task);
      set({ comparison: { type: "ready", data: comparison } });
    } catch (error) {
      set({
        comparison: { type: "error", message: getErrorMessage(error) },
      });
    } finally {
      set({ running: false });
    }
  },
}));
```

.1.6.8.1 代码讲解
​        这个 store 不和 `session-store.ts` 混在一起。原因是这两个模块的业务不同：

```Plain
session-store         管会话、消息、文件、事件
agent-thinking-store  管思维模式说明和任务对比
```

​        `LoadState<T>` 继续复用之前的加载状态设计：

```Plain
loading  加载中
ready    已有数据
error    出错
```

​        `runComparison()` 的业务流程是：

```Plain
读取 task
  |
  v
校验空字符串
  |
  v
进入 loading
  |
  v
POST /api/agent-thinking/compare
  |
  v
保存结果或保存错误
  |
  v
结束 running
```

#### 12.1.6.9 创建 hook 管页面生命周期
​        创建 `frontend/web/app/hooks/use-agent-thinking.ts`：

```TypeScript
import { useEffect } from "react";

import { useAgentThinkingStore } from "../stores/agent-thinking-store";

// ===================== 第1步：把页面生命周期从组件中拆出来 =====================
export function useAgentThinking() {
  const store = useAgentThinkingStore();

  useEffect(() => {
    store.loadModes();
  }, []);

  return store;
}
```

.1.6.9.1 代码讲解
​        hook 负责“页面什么时候加载数据”。
​        如果把 `useEffect()` 写在组件里，组件会同时负责：

```Plain
布局
交互
生命周期
数据请求
```

​        职责会变重。拆成 hook 后，组件只负责展示，store 负责状态，API 文件负责请求。

#### 12.1.6.10 创建 AgentThinkingPanel 组件
​        创建 `frontend/web/app/components/agent-thinking-panel.tsx`。
​        完整代码如下。这个文件较长，分成四块理解：

```Plain
AgentThinkingPanel  组合输入框、按钮、模式列表、结果区域
ModeList            展示四种模式说明
ComparisonResult    展示加载中、错误、空状态或结果
DemoCard            展示单个模式的步骤、工具和结论
import {
  Brain,
  GitBranch,
  Loader2,
  MessageSquareText,
  Wrench,
} from "lucide-react";

import type {
  LoadState,
  ThinkingComparisonData,
  ThinkingModeDemo,
  ThinkingModeInfo,
} from "../types";

type AgentThinkingPanelProps = {
  comparison: LoadState<ThinkingComparisonData | null>;
  modes: LoadState<ThinkingModeInfo[]>;
  onRun: () => void;
  onTaskChange: (task: string) => void;
  running: boolean;
  task: string;
};

const modeIcons: Record<string, typeof MessageSquareText> = {
  chatbot: MessageSquareText,
  cot: Brain,
  react: Wrench,
  decomposition: GitBranch,
};

// ===================== 第1步：组合 Agent 思维模型演示面板 =====================
export function AgentThinkingPanel({
  comparison,
  modes,
  onRun,
  onTaskChange,
  running,
  task,
}: AgentThinkingPanelProps) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4 max-lg:flex-col">
        <div>
          <h2 className="text-base font-semibold text-slate-950">
            Agent 思维模型
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
            用同一个任务对比普通 ChatBot、CoT、ReAct 和任务拆解。这里展示的是可解释的过程摘要，
            不是模型隐藏推理内容。
          </p>
        </div>
        <button
          className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={running}
          onClick={onRun}
          type="button"
        >
          {running ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <Brain size={16} />
          )}
          生成对比
        </button>
      </div>

      <div className="mt-4 grid grid-cols-[1fr_220px] gap-4 max-xl:grid-cols-1">
        <textarea
          className="min-h-24 resize-none rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-900 outline-none focus:border-slate-400"
          onChange={(event) => onTaskChange(event.target.value)}
          placeholder="输入一个想让 Agent 完成的任务"
          value={task}
        />
        <ModeList state={modes} />
      </div>

      <div className="mt-5">
        <ComparisonResult state={comparison} />
      </div>
    </section>
  );
}

// ===================== 第2步：展示四种模式的基础说明 =====================
function ModeList({ state }: { state: LoadState<ThinkingModeInfo[]> }) {
  if (state.type === "loading") {
    return <SmallState text="模式加载中" />;
  }
  if (state.type === "error") {
    return <SmallState text={state.message} tone="error" />;
  }

  return (
    <div className="grid gap-2">
      {state.data.map((mode) => {
        const Icon = modeIcons[mode.mode] ?? Brain;
        return (
          <div
            className="rounded-md border border-slate-200 bg-slate-50 p-3"
            key={mode.mode}
          >
            <div className="flex items-center gap-2 text-sm font-medium text-slate-950">
              <Icon size={16} aria-hidden="true" />
              {mode.name}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              {mode.summary}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// ===================== 第3步：展示任务对比结果 =====================
function ComparisonResult({
  state,
}: {
  state: LoadState<ThinkingComparisonData | null>;
}) {
  if (state.type === "loading") {
    return <SmallState text="正在生成对比结果" />;
  }
  if (state.type === "error") {
    return <SmallState text={state.message} tone="error" />;
  }
  if (!state.data) {
    return <SmallState text="点击生成对比后，这里会展示四种处理方式" />;
  }

  return (
    <div>
      <p className="text-sm text-slate-500">当前任务：{state.data.task}</p>
      <div className="mt-4 grid grid-cols-4 gap-4 max-2xl:grid-cols-2 max-lg:grid-cols-1">
        {state.data.demos.map((demo) => (
          <DemoCard demo={demo} key={demo.mode} />
        ))}
      </div>
    </div>
  );
}

// ===================== 第4步：展示单个思维模式的步骤、工具和结论 =====================
function DemoCard({ demo }: { demo: ThinkingModeDemo }) {
  const Icon = modeIcons[demo.mode] ?? Brain;
  return (
    <article className="flex min-h-[360px] flex-col rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
        <Icon size={18} aria-hidden="true" />
        {demo.name}
      </div>
      <p className="mt-2 text-sm text-slate-600">{demo.headline}</p>

      <ol className="mt-4 grid gap-2">
        {demo.steps.map((step, index) => (
          <li className="flex gap-2 text-sm leading-6 text-slate-700" key={step}>
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-500">
              {index + 1}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>

      {demo.tool_calls.length > 0 ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-white p-3">
          <p className="text-xs font-medium text-slate-500">可能调用的工具</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {demo.tool_calls.map((tool) => (
              <code
                className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700"
                key={tool}
              >
                {tool}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      <p className="mt-auto pt-4 text-sm leading-6 text-slate-700">
        {demo.final_answer}
      </p>
    </article>
  );
}

function SmallState({
  text,
  tone = "muted",
}: {
  text: string;
  tone?: "muted" | "error";
}) {
  return (
    <div
      className={
        tone === "error"
          ? "rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
          : "rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500"
      }
    >
      {text}
    </div>
  );
}
```

.1.6.10.1 代码讲解
​        这个组件是受控组件。`textarea` 的值来自 `task`，输入变化时调用 `onTaskChange()`。
​        点击按钮时调用 `onRun()`，组件本身不直接请求接口。这样组件可以保持简单：

```Plain
组件接收状态
组件触发事件
store 处理业务
```

​        按钮在 `running` 时禁用，避免连续点击造成重复请求。
​        `ModeList` 和 `ComparisonResult` 都接收 `LoadState`。这样加载中、错误和成功状态都有明确展示，不会出现页面空白。

#### 12.1.6.11 在首页接入面板
​        打开 `frontend/web/app/page.tsx`，新增导入：

```TypeScript
import { AgentThinkingPanel } from "./components/agent-thinking-panel";
import { useAgentThinking } from "./hooks/use-agent-thinking";
```

​        在 `Home()` 中创建状态：

```TypeScript
const agentThinking = useAgentThinking();
```

​        在状态面板和聊天工作台之间加入：

```TypeScript
<AgentThinkingPanel
  comparison={agentThinking.comparison}
  modes={agentThinking.modes}
  onRun={agentThinking.runComparison}
  onTaskChange={agentThinking.setTask}
  running={agentThinking.running}
  task={agentThinking.task}
/>
```

.1.6.11.1 代码讲解
​        `page.tsx` 仍然只做页面编排。它不直接写接口请求，也不直接写对比逻辑。
​        首页现在的大结构是：

```Plain
状态区域
Agent 思维模型面板
聊天工作台
```

​        这个顺序是有原因的：先让用户理解任务可以用哪些模式处理，再进入下方真实会话区。本章后文开始，Agent 能力会逐渐从演示面板迁移到真实会话流程。

### 12.1.7 关键理解
​        普通 ChatBot 适合简单任务。
​        CoT 适合需要分析和解释的任务，但页面上更建议展示“思考摘要”而不是完整隐藏推理。
​        ReAct 适合需要工具的任务。它的关键不是“想得更久”，而是：

```Plain
想一下
做一个动作
观察动作结果
再决定下一步
```

​        任务拆解适合长任务。它会把一个大目标变成多个可执行步骤，这就是 PlannerAgent 的基础。

### 12.1.8 技术难点与亮点
​        本节的难点是把概念讲清楚，同时不把概念写成散乱文案。聊天回复、思考摘要、工具行动和任务计划不是同一类东西；页面可以展示过程摘要和执行步骤，但不应该把模型隐藏推理当成普通内容暴露出来。即使这一阶段只是概念演示，也要有可运行接口和可观察页面。
​        项目亮点在于它不依赖真实 LLM，也能讲清 Agent 思维差异。新增接口稳定可测，前端使用独立状态管理，没有污染会话 store；页面还能直观看到 ReAct 为什么需要工具协议，以及任务拆解为什么会成为 PlannerAgent 的前置能力。

### 12.1.9 面试考点
​        面试里可以围绕 ChatBot 和 Agent 的区别展开：ChatBot 更像直接回答，Agent 则强调目标、计划、工具和观察。CoT 适合复杂推理，但页面上更应该展示可解释摘要，而不是完整隐藏推理。ReAct 中的 Reason 对应判断和选择，Act 对应工具调用或外部动作；任务拆解则把长任务变成可执行计划。概念演示也写成 API，是为了让后续真实 Agent 能平滑替换演示数据。

### 12.1.10 运行验证
​        下面命令默认在项目根目录执行。

#### 12.1.10.1 检查后端代码

```Bash
cd backend/api
uv run python -m compileall app
```

​        预期没有 Python 编译错误。

#### 12.1.10.2 检查前端类型

```Bash
cd ../../frontend/web
pnpm typecheck
```

​        预期没有 TypeScript 报错。

#### 12.1.10.3 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        如果镜像已经存在，可以执行：

```Bash
docker compose up -d nginx
```

​        如果改动后需要重新构建 API 和 UI：

```Bash
docker compose build --pull=false api ui
docker compose up -d nginx
```

#### 12.1.10.4 验证模式列表接口

```Bash
curl http://localhost:8088/api/agent-thinking/modes
```

​        预期返回里有：

```Plain
普通 ChatBot
CoT 思考摘要
ReAct
任务拆解
```

#### 12.1.10.5 验证任务对比接口

```Bash
curl -X POST http://localhost:8088/api/agent-thinking/compare \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我从 0 到 1 实现一个 AI Agent 项目"}'
```

​        预期返回中：

```Plain
demos 数组长度为 4
react 模式里有 tool_calls
decomposition 模式里有计划步骤
```

#### 12.1.10.6 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        页面中应该能看到“Agent 思维模型”面板。
​        操作步骤：
​        验证时输入一个任务，点击“生成对比”，页面应当出现四张对比卡片。普通 ChatBot 卡片会直接给出整体回答，CoT 卡片会展示分析摘要，ReAct 卡片会出现可能调用的工具，任务拆解卡片会把目标拆成多个阶段。这个结果说明后端演示接口和前端状态流都已经接通。

### 12.1.11 小结
​        本节完成了 Agent 思维模型的第一个可运行演示。后端定义了 ChatBot、CoT、ReAct 和任务拆解四种模式，新增模式说明接口和任务对比接口；前端新增 Agent 思维模型面板，并继续保持 API、store、hook、组件拆分。这个稳定演示说明了为什么 Agent 不只是聊天框，而需要规划、工具和可观察过程。
​        本章后文会进入 Agent 记忆与工具协议，实现 Memory、工具装饰器、工具 schema 和基础 Agent 调用循环。

## 12.2 Agent Memory 与工具协议

> **演进提示**：本节保留了早期教学版的 `ConversationMemory + ToolRegistry` 最小闭环，用于讲清基本概念。完整项目会在第 45、46 章升级为分层 Memory Control Plane 和统一 Tool Runtime；生产代码请以后两章为准。

### 12.2.1 本节目标
​        前文已经把 ChatBot、CoT、ReAct 和任务拆解放在同一个页面里比较过，但那一章仍然停留在“思维模型”的层面。真正进入 Agent 执行之前，还需要补上两个基础能力：一个是 Agent 运行时要看的上下文，也就是 Memory；另一个是 Agent 能够识别、选择和调用的工具协议。
​        本节会把这两部分做成一个最小闭环。后端会定义 `ConversationMemory`、工具 schema、工具注册表和内置教学工具，再通过 `AgentCoreService` 把用户任务、工具选择、工具结果和下一步提示写进同一段 Memory。前端则继续按照 API、store、hook、组件拆分，把工具列表、参数 schema、Memory 时间线和工具调用结果展示出来。这样到了第 13 章时，PlannerAgent 和 ReActAgent 就不是凭空出现，而是接在这一阶段搭好的上下文和工具系统之上。

### 12.2.2 最终效果
​        本节结束后，后端新增两个接口：

```Plain
GET  /api/agent-core/tools
POST /api/agent-core/demo
```

​        前端首页会新增“Agent 记忆与工具协议”面板。
​        你可以输入任务：

```Plain
帮我拆解一个 Agent 工具调用流程
```

​        选择工具：

```Plain
draft_plan
```

​        点击“运行演示”后，页面会展示当前可用工具、选中工具的参数 schema、一次 Agent 调用形成的 Memory 时间线、工具执行后的输出，以及后续如何把这些 Memory 消息交给 LLM 继续生成回答。读者在页面上看到的不是单次接口返回，而是一条可观察的 Agent 运行轨迹。
​        本节仍然不实现完整 PlannerAgent 和 ReActAgent。它先把 Memory 和工具协议搭起来。第 13 章会让 PlannerAgent 生成计划，第 13 章会让 ReActAgent 根据计划逐步执行。

### 12.2.3 本节要解决的问题
​        前文已经解释了 ChatBot、CoT、ReAct 和任务拆解的区别。
​        但是要真正实现 ReActAgent，必须先解决两个基础问题：

```Plain
Agent 如何记住上下文？
Agent 如何知道有哪些工具可以调用？
```

​        普通聊天只需要消息列表：

```Plain
user -> assistant
```

​        Agent 需要的上下文更丰富：

```Plain
user      用户任务
assistant Agent 决定调用哪个工具
tool      工具执行结果
assistant Agent 根据工具结果继续回答
```

​        所以本节先做一个最小闭环：

```Plain
用户输入任务
  |
  v
写入 Memory
  |
  v
选择工具
  |
  v
执行工具
  |
  v
把工具结果写回 Memory
  |
  v
返回给前端展示
```

### 12.2.4 本节技术方案
​        后端新增模块：

```Plain
backend/api/app/domain/agent_core/memory.py
backend/api/app/domain/agent_core/tools.py
backend/api/app/infrastructure/agent_tools/builtin.py
backend/api/app/application/agent_core_service.py
backend/api/app/api/routes/agent_core.py
```

​        前端新增模块：

```Plain
frontend/web/app/lib/agent-core-api.ts
frontend/web/app/stores/agent-core-store.ts
frontend/web/app/hooks/use-agent-core.ts
frontend/web/app/components/agent-core-panel.tsx
```

​        调用链路如下：

```Plain
AgentCorePanel
  |
  v
useAgentCore
  |
  v
useAgentCoreStore
  |
  v
agent-core-api
  |
  v
/api/agent-core/demo
  |
  v
AgentCoreService
  |
  +-- ConversationMemory
  +-- ToolRegistry
  +-- AgentTool.call()
```

​        本节只使用内置确定性工具，不调用真实外部工具。这样做是为了先把协议讲清楚：工具需要先被描述给模型或前端，调用前要根据 schema 检查参数，调用后要把结果重新写回 Memory，最后再由前端把这个过程展示出来。等这个闭环稳定后，再把搜索、文件、Shell 或浏览器工具接进来，复杂度才不会一下子失控。

### 12.2.5 新增和修改的文件

```Plain
README.md
backend/api/README.md
backend/api/app/api/router.py
backend/api/app/api/routes/agent_core.py
backend/api/app/application/agent_core_service.py
backend/api/app/domain/agent_core/__init__.py
backend/api/app/domain/agent_core/memory.py
backend/api/app/domain/agent_core/tools.py
backend/api/app/infrastructure/agent_tools/__init__.py
backend/api/app/infrastructure/agent_tools/builtin.py
backend/api/app/schemas/agent_core.py
docs/course/chapters/17-agent-memory-tools.md
docs/course/outline.md
frontend/web/README.md
frontend/web/app/components/agent-core-panel.tsx
frontend/web/app/hooks/use-agent-core.ts
frontend/web/app/lib/agent-core-api.ts
frontend/web/app/page.tsx
frontend/web/app/stores/agent-core-store.ts
frontend/web/app/types.ts
```

### 12.2.6 实施步骤
#### 12.2.6.1 定义 Agent Memory
​        创建 `backend/api/app/domain/agent_core/__init__.py`：

```Python
"""Agent memory and tool protocol domain objects."""
```

​        创建 `backend/api/app/domain/agent_core/memory.py`：

```Python
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

# ===================== 第1步：定义 Memory 中允许出现的消息角色 =====================
class MemoryRole(StrEnum):
    """Agent Memory 中的消息角色。

    user 表示用户输入，assistant 表示 Agent 输出，tool 表示工具执行结果。
    """

    user = "user"
    assistant = "assistant"
    tool = "tool"

# ===================== 第2步：定义 Memory 中的一条消息 =====================
@dataclass(slots=True)
class MemoryMessage:
    """Agent 运行时放入上下文的一条消息。"""

    id: UUID
    role: MemoryRole
    content: str
    created_at: datetime
    name: str | None = None

# ===================== 第3步：定义一个轻量 Memory 容器 =====================
@dataclass(slots=True)
class ConversationMemory:
    """保存一次 Agent 演示过程中的上下文消息。"""

    messages: list[MemoryMessage] = field(default_factory=list)

    def add_user_message(self, content: str) -> MemoryMessage:
        """把用户任务放入 Memory。"""

        return self._append(role=MemoryRole.user, content=content)

    def add_assistant_message(self, content: str) -> MemoryMessage:
        """把 Agent 的文字回复放入 Memory。"""

        return self._append(role=MemoryRole.assistant, content=content)

    def add_tool_message(self, tool_name: str, content: str) -> MemoryMessage:
        """把工具执行结果放入 Memory。

        name 字段保存工具名，方便后续模型知道这条消息来自哪个工具。
        """

        return self._append(role=MemoryRole.tool, content=content, name=tool_name)

    def list_messages(self) -> list[MemoryMessage]:
        """返回当前 Memory 的全部消息。"""

        return list(self.messages)

    def _append(
        self,
        role: MemoryRole,
        content: str,
        name: str | None = None,
    ) -> MemoryMessage:
        """统一创建消息，避免每个 add_* 方法重复写 id 和时间。"""

        message = MemoryMessage(
            id=uuid4(),
            role=role,
            content=content,
            created_at=datetime.now(UTC),
            name=name,
        )
        self.messages.append(message)
        return message
```

.2.6.1.1 代码讲解
​        Memory 是 Agent 的上下文容器。
​        普通聊天场景里，消息通常只有：

```Plain
user
assistant
```

​        Agent 场景里还需要：

```Plain
tool
```

​        原因是工具执行结果也会成为后续模型判断的依据。例如：

```Plain
用户：帮我总结这个文件
助手：我先读取文件
工具 read_file：文件内容如下...
助手：根据文件内容生成总结
```

​        `MemoryMessage.name` 用来保存工具名。对于 `tool` 角色来说，`name="read_file"` 或 `name="draft_plan"` 可以告诉后续模型：这条内容来自哪个工具。
​        `ConversationMemory._append()` 是一个私有辅助方法。它把创建消息时反复出现的字段集中到一个地方处理，包括消息 `id`、角色 `role`、正文 `content`、创建时间 `created_at`，以及工具消息可能携带的 `name`。这样 `add_user_message()`、`add_assistant_message()`、`add_tool_message()` 只表达“要追加哪类消息”，不用在每个方法里重复生成 UUID 和时间戳。

#### 12.2.6.2 定义工具协议
​        创建 `backend/api/app/domain/agent_core/tools.py`：

```Python
from collections.abc import Callable
from dataclasses import dataclass
from inspect import signature
from typing import Any, get_type_hints

from app.core.exceptions import AppException

# ===================== 第1步：定义工具参数的描述结构 =====================
@dataclass(slots=True)
class ToolParameter:
    """工具参数 schema。

    name 是参数名，type 是参数类型，description 用来给模型或前端解释参数含义。
    """

    name: str
    type: str
    description: str
    required: bool = True

# ===================== 第2步：定义工具描述结构 =====================
@dataclass(slots=True)
class ToolDefinition:
    """一个可以被 Agent 调用的工具。"""

    name: str
    description: str
    parameters: list[ToolParameter]

# ===================== 第3步：定义工具执行结果 =====================
@dataclass(slots=True)
class ToolCallResult:
    """工具调用后的统一结果。"""

    tool_name: str
    arguments: dict[str, Any]
    output: str

# ===================== 第4步：封装真实 Python 函数和工具 schema =====================
@dataclass(slots=True)
class AgentTool:
    """工具对象。

    definition 给前端和模型看，handler 是后端真正执行的 Python 函数。
    """

    definition: ToolDefinition
    handler: Callable[..., str]

    def call(self, arguments: dict[str, Any]) -> ToolCallResult:
        """执行工具函数，并包装成统一结果。"""

        checked_arguments = self._validate_arguments(arguments)
        output = self.handler(**checked_arguments)
        return ToolCallResult(
            tool_name=self.definition.name,
            arguments=checked_arguments,
            output=output,
        )

    def _validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """根据工具参数 schema 做最小校验。

        本章先检查必填参数是否存在。更严格的类型校验会在后续工具章节逐步增强。
        """

        checked: dict[str, Any] = {}
        for parameter in self.definition.parameters:
            value = arguments.get(parameter.name)
            if parameter.required and value in (None, ""):
                raise AppException(
                    message=f"tool argument is required: {parameter.name}",
                    code=400,
                    status_code=400,
                )
            checked[parameter.name] = value
        return checked

# ===================== 第5步：提供一个工具注册表 =====================
class ToolRegistry:
    """保存所有可用工具，并按名称查找工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        """注册工具。工具名不能重复。"""

        if tool.definition.name in self._tools:
            raise AppException(
                message=f"tool already exists: {tool.definition.name}",
                code=500,
                status_code=500,
            )
        self._tools[tool.definition.name] = tool

    def list_tools(self) -> list[ToolDefinition]:
        """返回全部工具 schema。"""

        return [tool.definition for tool in self._tools.values()]

    def get(self, name: str) -> AgentTool:
        """按名称获取工具，不存在时返回清晰错误。"""

        tool = self._tools.get(name)
        if tool is None:
            raise AppException(
                message=f"tool not found: {name}",
                code=404,
                status_code=404,
            )
        return tool

# ===================== 第6步：用装饰器把普通函数变成 AgentTool =====================
def agent_tool(
    name: str,
    description: str,
    parameter_descriptions: dict[str, str],
) -> Callable[[Callable[..., str]], AgentTool]:
    """工具装饰器。

    使用方式：

    @agent_tool(...)
    def summarize_text(text: str) -> str:
        ...

    装饰器会读取函数签名，生成 ToolDefinition。
    """

    def decorator(func: Callable[..., str]) -> AgentTool:
        parameters = _build_parameters(func, parameter_descriptions)
        return AgentTool(
            definition=ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
            ),
            handler=func,
        )

    return decorator

def _build_parameters(
    func: Callable[..., str],
    parameter_descriptions: dict[str, str],
) -> list[ToolParameter]:
    """从函数签名中提取工具参数。"""

    func_signature = signature(func)
    type_hints = get_type_hints(func)
    parameters: list[ToolParameter] = []
    for parameter_name, parameter in func_signature.parameters.items():
        annotation = type_hints.get(parameter_name, str)
        parameters.append(
            ToolParameter(
                name=parameter_name,
                type=_to_schema_type(annotation),
                description=parameter_descriptions.get(parameter_name, ""),
                required=parameter.default is parameter.empty,
            )
        )
    return parameters

def _to_schema_type(annotation: Any) -> str:
    """把 Python 类型转换成前端更容易展示的 schema 类型。"""

    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    return "string"
```

.2.6.2.1 代码讲解
​        工具协议分成四层：

```Plain
ToolParameter   描述一个参数
ToolDefinition  描述一个工具
AgentTool       把工具描述和 Python 函数绑定起来
ToolRegistry    保存多个工具
```

​        `ToolDefinition` 是给模型或前端看的。
​        例如一个工具可以描述为：

```Plain
name: draft_plan
description: 为一个任务生成 3 个粗粒度执行步骤
parameters:
  - name: task
    type: string
```

​        模型看到这段 schema 后，才知道可以调用什么工具、需要传什么参数。
​        `AgentTool.call()` 是工具真正执行的入口。它先做参数校验，再执行 handler，最后把结果包装成 `ToolCallResult`。
​        `agent_tool()` 是装饰器。它让普通函数可以写成：

```Python
@agent_tool(...)
def draft_plan(task: str) -> str:
    ...
```

​        这样函数本身只关注业务逻辑，工具名称、描述、参数描述都由装饰器生成。

#### 12.2.6.3 编写内置工具
​        创建 `backend/api/app/infrastructure/agent_tools/__init__.py`：

```Python
"""Built-in agent tools."""
```

​        创建 `backend/api/app/infrastructure/agent_tools/builtin.py`：

```Python
from app.domain.agent_core.tools import ToolRegistry, agent_tool

# ===================== 第1步：定义一个文本摘要工具 =====================
@agent_tool(
    name="summarize_text",
    description="把一段较长文本压缩成更短的摘要。",
    parameter_descriptions={
        "text": "需要压缩和概括的原始文本。",
    },
)
def summarize_text(text: str) -> str:
    """返回一个简单摘要。

    本章先使用确定性字符串处理，后续可以替换成真实 LLM 摘要。
    """

    clean_text = " ".join(text.split())
    if len(clean_text) <= 80:
        return f"摘要：{clean_text}"
    return f"摘要：{clean_text[:80]}..."

# ===================== 第2步：定义一个关键词提取工具 =====================
@agent_tool(
    name="extract_keywords",
    description="从任务文本中提取几个关键词，帮助 Agent 判断任务重点。",
    parameter_descriptions={
        "text": "需要提取关键词的文本。",
    },
)
def extract_keywords(text: str) -> str:
    """按长度和去重规则提取关键词。"""

    words = [
        word.strip("，。,.!?！？、")
        for word in text.split()
        if len(word.strip("，。,.!?！？、")) >= 2
    ]
    unique_words = list(dict.fromkeys(words))
    if not unique_words:
        return "关键词：暂无"
    return "关键词：" + "、".join(unique_words[:5])

# ===================== 第3步：定义一个计划草稿工具 =====================
@agent_tool(
    name="draft_plan",
    description="为一个任务生成 3 个粗粒度执行步骤。",
    parameter_descriptions={
        "task": "需要拆解的用户任务。",
    },
)
def draft_plan(task: str) -> str:
    """生成固定格式的计划草稿。"""

    return "\n".join(
        [
            f"1. 明确目标：确认“{task}”的最终交付物。",
            "2. 拆解步骤：列出需要完成的关键阶段。",
            "3. 验证结果：检查输出是否满足目标和约束。",
        ]
    )

# ===================== 第4步：创建内置工具注册表 =====================
def build_builtin_tool_registry() -> ToolRegistry:
    """注册并返回本章可用的内置工具。"""

    registry = ToolRegistry()
    registry.register(summarize_text)
    registry.register(extract_keywords)
    registry.register(draft_plan)
    return registry
```

.2.6.3.1 代码讲解
​        这里定义了三个教学工具。`summarize_text` 用来演示最简单的“文本输入到文本输出”，`extract_keywords` 用来模拟 Agent 从任务中抓重点，`draft_plan` 则把任务改写成三个粗粒度步骤。它们的能力都很克制，但三者足以覆盖工具 schema、参数构造、工具执行和结果回写 Memory 的完整路径。
​        这些工具现在都不调用外部 API，原因是本节重点是工具协议，而不是工具能力本身。真实工具会牵涉网络、文件系统、权限、超时和错误处理，如果在这里提前引入，读者反而不容易看清工具协议这一层到底负责什么。
​        `build_builtin_tool_registry()` 负责把工具注册到 `ToolRegistry`。后续新增搜索工具、文件工具、Shell 工具时，也会进入类似的注册流程。

#### 12.2.6.4 编写 AgentCoreService
​        创建 `backend/api/app/application/agent_core_service.py`：

```Python
from app.core.exceptions import AppException
from app.domain.agent_core.memory import ConversationMemory, MemoryMessage
from app.domain.agent_core.tools import ToolCallResult, ToolDefinition, ToolRegistry
from app.infrastructure.agent_tools.builtin import build_builtin_tool_registry

class AgentCoreService:
    """第 17 章的最小 Agent 核心服务。

    本章先把 Memory、工具 schema、工具调用结果串起来。
    它还不是完整 Agent，但已经具备后续 PlannerAgent 和 ReActAgent 需要的基础积木。
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        # ===================== 第1步：准备工具注册表 =====================
        # 如果外部没有传入 registry，就使用本章内置的几个教学工具。
        self.registry = registry or build_builtin_tool_registry()

    # ===================== 第2步：返回工具 schema 给前端或模型查看 =====================
    def list_tools(self) -> list[ToolDefinition]:
        """列出当前 Agent 可以调用的工具。"""

        return self.registry.list_tools()

    # ===================== 第3步：运行一次最小 Agent 演示 =====================
    def run_demo(
        self,
        task: str,
        tool_name: str | None = None,
    ) -> tuple[list[MemoryMessage], ToolDefinition, ToolCallResult, str]:
        """把用户任务、工具调用和工具结果写入 Memory。"""

        clean_task = task.strip()
        if not clean_task:
            raise AppException(
                message="task is required",
                code=400,
                status_code=400,
            )

        memory = ConversationMemory()
        memory.add_user_message(clean_task)

        selected_tool_name = tool_name or self._choose_tool(clean_task)
        selected_tool = self.registry.get(selected_tool_name)
        arguments = self._build_arguments(selected_tool.definition, clean_task)

        memory.add_assistant_message(
            f"我会调用 {selected_tool.definition.name} 工具处理这个任务。"
        )
        tool_result = selected_tool.call(arguments)
        memory.add_tool_message(
            tool_name=tool_result.tool_name,
            content=tool_result.output,
        )

        next_step = (
            "下一步可以把这些 Memory 消息交给 LLM，让模型基于工具结果继续生成回答。"
        )
        memory.add_assistant_message(next_step)

        return (
            memory.list_messages(),
            selected_tool.definition,
            tool_result,
            next_step,
        )

    # ===================== 第4步：根据任务内容选择默认工具 =====================
    def _choose_tool(self, task: str) -> str:
        """用简单规则模拟 Agent 的工具选择。"""

        if "计划" in task or "步骤" in task or "拆解" in task:
            return "draft_plan"
        if "关键词" in task or "重点" in task:
            return "extract_keywords"
        return "summarize_text"

    # ===================== 第5步：把用户任务转换成工具参数 =====================
    def _build_arguments(
        self,
        definition: ToolDefinition,
        task: str,
    ) -> dict[str, str]:
        """根据工具 schema 生成本次调用参数。"""

        arguments: dict[str, str] = {}
        for parameter in definition.parameters:
            if parameter.name == "task":
                arguments[parameter.name] = task
            else:
                arguments[parameter.name] = task
        return arguments
```

.2.6.4.1 代码讲解
​        `run_demo()` 是本节后端最重要的业务流程：

```Plain
清理 task
  |
  v
创建 ConversationMemory
  |
  v
写入 user 消息
  |
  v
选择工具
  |
  v
根据工具 schema 构造参数
  |
  v
写入 assistant 决策消息
  |
  v
执行工具
  |
  v
写入 tool 消息
  |
  v
写入 assistant 下一步消息
```

​        这已经是 ReAct 的最小形状：

```Plain
观察任务 -> 决定工具 -> 执行工具 -> 观察结果 -> 继续回答
```

​        本节的 `_choose_tool()` 只是简单规则。第 13 章会让 LLM 根据上下文选择工具。

#### 12.2.6.5 定义接口 Schema
​        创建 `backend/api/app/schemas/agent_core.py`：

```Python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ===================== 第1步：定义工具 schema 响应 =====================
class ToolParameterResponse(BaseModel):
    name: str
    type: str
    description: str
    required: bool

class ToolDefinitionResponse(BaseModel):
    name: str
    description: str
    parameters: list[ToolParameterResponse]

class ToolListResponse(BaseModel):
    items: list[ToolDefinitionResponse]

# ===================== 第2步：定义 Memory 消息响应 =====================
class MemoryMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    name: str | None = None

# ===================== 第3步：定义工具调用结果响应 =====================
class ToolCallResultResponse(BaseModel):
    tool_name: str
    arguments: dict
    output: str

# ===================== 第4步：定义最小 Agent 演示请求和响应 =====================
class AgentCoreDemoRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)
    tool_name: str | None = None

class AgentCoreDemoResponse(BaseModel):
    messages: list[MemoryMessageResponse]
    selected_tool: ToolDefinitionResponse
    tool_result: ToolCallResultResponse
    next_step: str
```

.2.6.5.1 代码讲解
​        Schema 是接口契约。
​        前端最关心这三个结构：

```Plain
tools       当前有哪些工具
messages    Memory 时间线
tool_result 工具执行结果
```

​        `AgentCoreDemoRequest.tool_name` 允许为空。为空时后端会根据任务内容自动选择工具；有值时使用前端选中的工具。

#### 12.2.6.6 编写 API 路由
​        创建 `backend/api/app/api/routes/agent_core.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.agent_core_service import AgentCoreService
from app.domain.agent_core.memory import MemoryMessage
from app.domain.agent_core.tools import ToolCallResult, ToolDefinition, ToolParameter
from app.schemas.agent_core import (
    AgentCoreDemoRequest,
    AgentCoreDemoResponse,
    MemoryMessageResponse,
    ToolCallResultResponse,
    ToolDefinitionResponse,
    ToolListResponse,
    ToolParameterResponse,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/agent-core", tags=["agent-core"])

# ===================== 第1步：创建应用服务依赖 =====================
def build_agent_core_service() -> AgentCoreService:
    """创建 AgentCoreService。

    当前服务只依赖内置工具注册表，不需要数据库连接。
    """

    return AgentCoreService()

# ===================== 第2步：把领域对象转换成接口响应 =====================
def to_parameter_response(parameter: ToolParameter) -> ToolParameterResponse:
    return ToolParameterResponse(
        name=parameter.name,
        type=parameter.type,
        description=parameter.description,
        required=parameter.required,
    )

def to_tool_response(definition: ToolDefinition) -> ToolDefinitionResponse:
    return ToolDefinitionResponse(
        name=definition.name,
        description=definition.description,
        parameters=[
            to_parameter_response(parameter)
            for parameter in definition.parameters
        ],
    )

def to_memory_message_response(message: MemoryMessage) -> MemoryMessageResponse:
    return MemoryMessageResponse(
        id=message.id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
        name=message.name,
    )

def to_tool_result_response(result: ToolCallResult) -> ToolCallResultResponse:
    return ToolCallResultResponse(
        tool_name=result.tool_name,
        arguments=result.arguments,
        output=result.output,
    )

# ===================== 第3步：提供工具列表接口 =====================
@router.get("/tools", response_model=ApiResponse[ToolListResponse])
async def list_tools(
    service: AgentCoreService = Depends(build_agent_core_service),
) -> ApiResponse[ToolListResponse]:
    """返回当前 Agent 可以调用的工具 schema。"""

    return ApiResponse(
        data=ToolListResponse(
            items=[to_tool_response(tool) for tool in service.list_tools()],
        )
    )

# ===================== 第4步：提供最小 Agent 演示接口 =====================
@router.post("/demo", response_model=ApiResponse[AgentCoreDemoResponse])
async def run_demo(
    payload: AgentCoreDemoRequest,
    service: AgentCoreService = Depends(build_agent_core_service),
) -> ApiResponse[AgentCoreDemoResponse]:
    """运行一次 Memory + 工具调用演示。"""

    messages, selected_tool, tool_result, next_step = service.run_demo(
        task=payload.task,
        tool_name=payload.tool_name,
    )
    return ApiResponse(
        data=AgentCoreDemoResponse(
            messages=[
                to_memory_message_response(message)
                for message in messages
            ],
            selected_tool=to_tool_response(selected_tool),
            tool_result=to_tool_result_response(tool_result),
            next_step=next_step,
        )
    )
```

.2.6.6.1 代码讲解
​        路由层继续保持薄：

```Plain
接收请求
调用 service
把领域对象转成 response schema
返回 ApiResponse
```

​        这里有很多 `to_*_response()` 函数，它们看起来有点啰嗦，但很重要。
​        原因是领域层和接口层要隔离。领域层以后可能把 `ToolDefinition` 改得更适合模型，接口层仍然可以保持前端需要的结构。

#### 12.2.6.7 注册路由
​        打开 `backend/api/app/api/router.py`：

```Python
from fastapi import APIRouter

from app.api.routes import (
    agent_core,
    agent_thinking,
    config,
    files,
    llm,
    sessions,
    status,
)

api_router = APIRouter()
api_router.include_router(status.router)
api_router.include_router(sessions.router)
api_router.include_router(files.router)
api_router.include_router(config.router)
api_router.include_router(llm.router)
api_router.include_router(agent_thinking.router)
api_router.include_router(agent_core.router)
```

.2.6.7.1 代码讲解
​        新增路由文件后必须注册到总路由。
​        否则 `agent_core.py` 文件存在，但接口不会被 FastAPI 加载，访问时会得到 404。

#### 12.2.6.8 扩展前端类型
​        打开 `frontend/web/app/types.ts`，新增：

```TypeScript
export type ToolParameter = {
  name: string;
  type: string;
  description: string;
  required: boolean;
};

export type ToolDefinition = {
  name: string;
  description: string;
  parameters: ToolParameter[];
};

export type ToolListData = {
  items: ToolDefinition[];
};

export type MemoryMessage = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_at: string;
  name: string | null;
};

export type ToolCallResult = {
  tool_name: string;
  arguments: Record<string, unknown>;
  output: string;
};

export type AgentCoreDemoData = {
  messages: MemoryMessage[];
  selected_tool: ToolDefinition;
  tool_result: ToolCallResult;
  next_step: string;
};
```

.2.6.8.1 代码讲解
​        这些类型和后端 `agent_core.py` schema 对齐。
​        页面最终展示的三个核心数据是：

```Plain
ToolDefinition[]      工具 schema
MemoryMessage[]       Memory 时间线
ToolCallResult        工具执行结果
```

​        `MemoryMessage.role` 使用联合类型：

```TypeScript
"user" | "assistant" | "tool"
```

​        这样前端写错角色时，TypeScript 会及时报错。

#### 12.2.6.9 封装前端 API
​        创建 `frontend/web/app/lib/agent-core-api.ts`：

```TypeScript
import { requestApi } from "./api";
import type { AgentCoreDemoData, ToolListData } from "../types";

// ===================== 第1步：读取 Agent 可用工具列表 =====================
export function fetchAgentTools() {
  return requestApi<ToolListData>("/api/agent-core/tools").then(
    (data) => data.items,
  );
}

// ===================== 第2步：运行一次 Memory + 工具调用演示 =====================
export function runAgentCoreDemo(task: string, toolName: string | null) {
  return requestApi<AgentCoreDemoData>("/api/agent-core/demo", {
    method: "POST",
    body: JSON.stringify({
      task,
      tool_name: toolName,
    }),
  });
}
```

.2.6.9.1 代码讲解
​        组件不直接写接口路径。
​        `fetchAgentTools()` 只负责读取工具列表。
​        `runAgentCoreDemo()` 只负责提交任务和工具名。
​        这样组件不需要知道后端返回外层是 `ApiResponse`，也不需要重复写 `fetch()`。

#### 12.2.6.10 创建前端 store
​        创建 `frontend/web/app/stores/agent-core-store.ts`：

```TypeScript
import { create } from "zustand";

import { fetchAgentTools, runAgentCoreDemo } from "../lib/agent-core-api";
import type { AgentCoreDemoData, LoadState, ToolDefinition } from "../types";

type AgentCoreState = {
  demo: LoadState<AgentCoreDemoData | null>;
  running: boolean;
  selectedToolName: string | null;
  task: string;
  tools: LoadState<ToolDefinition[]>;
};

type AgentCoreActions = {
  loadTools: () => Promise<void>;
  runDemo: () => Promise<void>;
  setSelectedToolName: (toolName: string | null) => void;
  setTask: (task: string) => void;
};

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "unknown error";
}

// ===================== 第1步：创建独立的 Agent 核心 store =====================
export const useAgentCoreStore = create<AgentCoreState & AgentCoreActions>(
  (set, get) => ({
    demo: { type: "ready", data: null },
    running: false,
    selectedToolName: null,
    task: "帮我拆解一个 Agent 工具调用流程",
    tools: { type: "loading" },

    setSelectedToolName: (toolName) => set({ selectedToolName: toolName }),
    setTask: (task) => set({ task }),

    // ===================== 第2步：加载工具 schema =====================
    loadTools: async () => {
      set({ tools: { type: "loading" } });
      try {
        const tools = await fetchAgentTools();
        set((state) => ({
          selectedToolName: state.selectedToolName ?? tools[0]?.name ?? null,
          tools: { type: "ready", data: tools },
        }));
      } catch (error) {
        set({ tools: { type: "error", message: getErrorMessage(error) } });
      }
    },

    // ===================== 第3步：运行最小 Agent 核心演示 =====================
    runDemo: async () => {
      const task = get().task.trim();
      if (!task) {
        set({ demo: { type: "error", message: "请输入一个任务" } });
        return;
      }

      set({ demo: { type: "loading" }, running: true });
      try {
        const demo = await runAgentCoreDemo(task, get().selectedToolName);
        set({ demo: { type: "ready", data: demo } });
      } catch (error) {
        set({ demo: { type: "error", message: getErrorMessage(error) } });
      } finally {
        set({ running: false });
      }
    },
  }),
);
```

.2.6.10.1 代码讲解
​        这个 store 独立于 `session-store` 和 `agent-thinking-store`。
​        原因是本节的状态是工具协议演示：

```Plain
工具列表
选中的工具
演示任务
运行结果
```

​        它不应该混进会话聊天状态里。
​        `loadTools()` 在页面打开时加载工具 schema，并默认选中第一个工具。
​        `runDemo()` 的流程是：

```Plain
读取 task
  |
  v
校验非空
  |
  v
进入 loading
  |
  v
调用 /api/agent-core/demo
  |
  v
保存 Memory 和工具结果
```

#### 12.2.6.11 创建 hook
​        创建 `frontend/web/app/hooks/use-agent-core.ts`：

```TypeScript
import { useEffect } from "react";

import { useAgentCoreStore } from "../stores/agent-core-store";

// ===================== 第1步：加载 Agent 工具协议演示所需数据 =====================
export function useAgentCore() {
  const store = useAgentCoreStore();

  useEffect(() => {
    store.loadTools();
  }, []);

  return store;
}
```

.2.6.11.1 代码讲解
​        hook 负责页面生命周期。
​        组件挂载时，`useEffect()` 会调用 `loadTools()`，这样页面一打开就能看到工具列表。

#### 12.2.6.12 创建 AgentCorePanel 组件
​        创建 `frontend/web/app/components/agent-core-panel.tsx`。
​        这个文件包含：

```Plain
AgentCorePanel   面板主体
ToolSelector     工具选择器
ToolSchemaList   工具 schema 列表
DemoResult       演示结果区域
MemoryTimeline   Memory 时间线
SmallState       加载、错误、空状态
```

​        完整代码如下：

```TypeScript
import { Bot, Braces, Hammer, Loader2, MessageCircle } from "lucide-react";

import type {
  AgentCoreDemoData,
  LoadState,
  MemoryMessage,
  ToolDefinition,
} from "../types";

type AgentCorePanelProps = {
  demo: LoadState<AgentCoreDemoData | null>;
  onRun: () => void;
  onTaskChange: (task: string) => void;
  onToolChange: (toolName: string | null) => void;
  running: boolean;
  selectedToolName: string | null;
  task: string;
  tools: LoadState<ToolDefinition[]>;
};

// ===================== 第1步：组合 Memory 与工具协议演示面板 =====================
export function AgentCorePanel({
  demo,
  onRun,
  onTaskChange,
  onToolChange,
  running,
  selectedToolName,
  task,
  tools,
}: AgentCorePanelProps) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4 max-lg:flex-col">
        <div>
          <h2 className="text-base font-semibold text-slate-950">
            Agent 记忆与工具协议
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
            运行一次最小 Agent 调用，观察用户任务、工具选择、工具结果如何进入 Memory。
          </p>
        </div>
        <button
          className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={running}
          onClick={onRun}
          type="button"
        >
          {running ? (
            <Loader2 className="animate-spin" size={16} />
          ) : (
            <Bot size={16} />
          )}
          运行演示
        </button>
      </div>

      <div className="mt-4 grid grid-cols-[1fr_280px] gap-4 max-xl:grid-cols-1">
        <div className="space-y-3">
          <textarea
            className="min-h-24 w-full resize-none rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-900 outline-none focus:border-slate-400"
            onChange={(event) => onTaskChange(event.target.value)}
            placeholder="输入一个要交给 Agent 处理的任务"
            value={task}
          />
          <ToolSelector
            onToolChange={onToolChange}
            selectedToolName={selectedToolName}
            state={tools}
          />
        </div>

        <ToolSchemaList state={tools} />
      </div>

      <div className="mt-5">
        <DemoResult state={demo} />
      </div>
    </section>
  );
}

// ===================== 第2步：选择本次演示要调用的工具 =====================
function ToolSelector({
  onToolChange,
  selectedToolName,
  state,
}: {
  onToolChange: (toolName: string | null) => void;
  selectedToolName: string | null;
  state: LoadState<ToolDefinition[]>;
}) {
  if (state.type !== "ready") {
    return null;
  }

  return (
    <label className="block text-sm text-slate-600">
      <span className="mb-2 block font-medium text-slate-700">选择工具</span>
      <select
        className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
        onChange={(event) => onToolChange(event.target.value || null)}
        value={selectedToolName ?? ""}
      >
        {state.data.map((tool) => (
          <option key={tool.name} value={tool.name}>
            {tool.name}
          </option>
        ))}
      </select>
    </label>
  );
}

// ===================== 第3步：展示工具 schema =====================
function ToolSchemaList({ state }: { state: LoadState<ToolDefinition[]> }) {
  if (state.type === "loading") {
    return <SmallState text="工具加载中" />;
  }
  if (state.type === "error") {
    return <SmallState text={state.message} tone="error" />;
  }

  return (
    <div className="grid gap-2">
      {state.data.map((tool) => (
        <div
          className="rounded-md border border-slate-200 bg-slate-50 p-3"
          key={tool.name}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-slate-950">
            <Hammer size={16} aria-hidden="true" />
            {tool.name}
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            {tool.description}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tool.parameters.map((parameter) => (
              <code
                className="rounded bg-white px-2 py-1 text-xs text-slate-700"
                key={parameter.name}
              >
                {parameter.name}: {parameter.type}
              </code>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===================== 第4步：展示 Memory、工具结果和下一步 =====================
function DemoResult({
  state,
}: {
  state: LoadState<AgentCoreDemoData | null>;
}) {
  if (state.type === "loading") {
    return <SmallState text="正在运行 Agent 核心演示" />;
  }
  if (state.type === "error") {
    return <SmallState text={state.message} tone="error" />;
  }
  if (!state.data) {
    return <SmallState text="点击运行演示后，这里会展示 Memory 和工具结果" />;
  }

  return (
    <div className="grid grid-cols-[1fr_320px] gap-4 max-xl:grid-cols-1">
      <MemoryTimeline messages={state.data.messages} />
      <div className="space-y-4">
        <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Braces size={16} aria-hidden="true" />
            工具结果
          </div>
          <p className="mt-2 text-sm text-slate-500">
            {state.data.tool_result.tool_name}
          </p>
          <pre className="mt-3 whitespace-pre-wrap rounded-md bg-white p-3 text-xs leading-5 text-slate-700">
            {state.data.tool_result.output}
          </pre>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
          {state.data.next_step}
        </div>
      </div>
    </div>
  );
}

// ===================== 第5步：展示 Agent Memory 时间线 =====================
function MemoryTimeline({ messages }: { messages: MemoryMessage[] }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
        <MessageCircle size={16} aria-hidden="true" />
        Memory
      </div>
      <div className="mt-4 grid gap-3">
        {messages.map((message) => (
          <div className="rounded-md bg-white p-3" key={message.id}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase text-slate-500">
                {message.role}
                {message.name ? ` / ${message.name}` : ""}
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
              {message.content}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function SmallState({
  text,
  tone = "muted",
}: {
  text: string;
  tone?: "muted" | "error";
}) {
  return (
    <div
      className={
        tone === "error"
          ? "rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"
          : "rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500"
      }
    >
      {text}
    </div>
  );
}
```

.2.6.12.1 组件讲解
​        `AgentCorePanel` 是受控组件。
​        它不直接请求后端，只接收：

```Plain
tools
demo
task
selectedToolName
running
```

​        也只触发：

```Plain
onTaskChange
onToolChange
onRun
```

​        真正的请求和状态更新都在 store 里完成。

#### 12.2.6.13 在首页接入 AgentCorePanel
​        打开 `frontend/web/app/page.tsx`，新增导入：

```TypeScript
import { AgentCorePanel } from "./components/agent-core-panel";
import { useAgentCore } from "./hooks/use-agent-core";
```

​        在 `Home()` 中创建状态：

```TypeScript
const agentCore = useAgentCore();
```

​        在 `AgentThinkingPanel` 下方加入：

```TypeScript
<AgentCorePanel
  demo={agentCore.demo}
  onRun={agentCore.runDemo}
  onTaskChange={agentCore.setTask}
  onToolChange={agentCore.setSelectedToolName}
  running={agentCore.running}
  selectedToolName={agentCore.selectedToolName}
  task={agentCore.task}
  tools={agentCore.tools}
/>
```

.2.6.13.1 代码讲解
​        首页现在的 Agent 学习路径是：

```Plain
Agent 思维模型
  |
  v
Agent 记忆与工具协议
  |
  v
聊天工作台
```

​        这能让用户先理解概念，再观察工具协议，最后回到真实会话流程。

### 12.2.7 关键理解
​        Memory 不是数据库表，也不是最终聊天记录。
​        Memory 是 Agent 每次运行时给模型看的上下文材料。它可以来自用户消息，也可以来自历史对话、上传文件、工具结果、计划步骤和上一步执行结果。数据库负责长期保存，Memory 负责把当前这次推理最需要的材料组织成模型能理解的上下文，两者职责不能混在一起。
​        工具协议也不是工具函数本身。
​        工具协议是工具函数对外暴露的说明：

```Plain
工具叫什么
能做什么
需要什么参数
返回什么结果
```

​        Agent 只有拿到工具 schema，才能决定什么时候调用工具，以及如何构造参数。

### 12.2.8 技术难点与亮点
​        本节的难点不在代码量，而在边界划分。Memory、聊天记录和数据库持久化看起来都在保存消息，但 Memory 面向的是“本次推理要给模型看的上下文”；工具 schema 和工具函数也不能混在一起，前者用于描述和选择，后者才是真正执行。装饰器从函数签名生成参数描述，工具注册表负责发现和查找工具，工具执行结果再回写 Memory，这几步必须连成一条清晰链路。
​        项目亮点在于后续 ReActAgent 需要的基础结构已经出现了。新增工具时，不需要在多个地方硬编码工具信息，只要用装饰器声明名称、描述和参数说明，再注册到 `ToolRegistry` 即可。前端也没有等到最后才补页面，而是同步展示工具 schema、Memory 和结果，这会让读者在开发过程中始终看到 Agent 内部状态的变化。

### 12.2.9 面试考点
​        面试里可以从 Agent Memory 和普通聊天消息的区别讲起。普通聊天消息主要面向展示和历史记录，Agent Memory 更强调本次推理上下文；工具 schema 的价值在于让模型或服务知道有哪些工具、每个工具需要什么参数；装饰器解决的是“业务函数”和“工具描述”重复维护的问题；`ToolRegistry` 则提供统一的工具注册、列表查询和按名称调用入口。工具结果必须写回 Memory，是因为 Agent 后续回答需要基于观察结果继续判断。本节不直接实现完整 ReActAgent，是为了先把 Memory 和工具协议两块地基铺稳。

### 12.2.10 运行验证
​        下面命令默认在项目根目录执行。

#### 12.2.10.1 检查后端代码

```Bash
cd backend/api
uv run python -m compileall app
```

​        预期没有 Python 编译错误。

#### 12.2.10.2 检查前端类型

```Bash
cd ../../frontend/web
pnpm typecheck
```

​        预期没有 TypeScript 报错。

#### 12.2.10.3 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        本节修改了 API 和 UI 代码，需要重新构建：

```Bash
docker compose build --pull=false api ui
docker compose up -d --force-recreate api ui nginx
```

​        这里重启 Nginx 是为了让它重新解析新的 API/UI 容器地址，避免旧容器 IP 导致 502。

#### 12.2.10.4 验证工具列表接口

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期返回中有：

```Plain
summarize_text
extract_keywords
draft_plan
```

#### 12.2.10.5 验证 Agent 核心演示接口

```Bash
curl -X POST http://localhost:8088/api/agent-core/demo \
  -H "Content-Type: application/json" \
  -d '{"task":"帮我拆解一个 Agent 工具调用流程","tool_name":"draft_plan"}'
```

​        预期返回中：

```Plain
messages 至少有 4 条
selected_tool.name 是 draft_plan
tool_result.output 中有 3 个计划步骤
```

#### 12.2.10.6 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        页面中应该能看到“Agent 记忆与工具协议”面板。
​        操作步骤：
​        验证时先输入一个任务，再选择 `draft_plan`、`extract_keywords` 或 `summarize_text` 中的一个工具，随后点击“运行演示”。页面应当同时更新 Memory 时间线和工具结果区域。Memory 中先出现用户任务，再出现 Agent 决定调用工具的消息，随后是带工具名的 `tool` 消息，最后出现提示下一步可以交给 LLM 继续生成回答的 assistant 消息。

### 12.2.11 小结
​        本节完成了 Agent 核心的第二块基础能力。后端定义了 Agent Memory、工具参数、工具 schema 和工具执行结果，并用装饰器把普通 Python 函数封装成可注册、可列举、可按名称调用的工具；应用服务把用户任务、工具选择、工具结果和下一步提示写入同一段 Memory；前端则新增了工具协议演示面板，把工具列表、参数 schema、Memory 时间线和工具输出放在同一个可观察界面中。
​        第 13 章会进入 PlannerAgent 任务规划，让 LLM 根据用户任务生成结构化计划，并在前端展示计划目标、步骤和预期输出。到那时，本节的 Memory 和工具协议会继续作为后续 Agent 执行链路的基础。

## 12.3 本章小结

​        完成“Agent 思维模型立论”和“Agent Memory 与工具协议”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第十一章. 应用配置与 LLM 客户端就位](11-应用配置与%20LLM%20客户端就位.md) · [返回目录](../README.md) · [第十三章. PlannerAgent 与 ReActAgent 执行闭环 →](13-PlannerAgent%20与%20ReActAgent%20执行闭环.md)
