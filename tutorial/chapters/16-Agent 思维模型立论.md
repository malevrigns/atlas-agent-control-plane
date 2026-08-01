# 第十六章. Agent 思维模型立论

## 16.1 本章目标
​        第 15 章让项目具备了调用 LLM 的基础能力，但“能调用模型”和“具备 Agent 能力”不是同一件事。普通聊天调用通常只是一问一答，而复杂 Agent 需要理解目标、拆解步骤、选择工具、观察结果，再决定是否继续执行。第十六章先不急着接真实模型，而是用一个稳定的演示模块，把几种典型思维模式放在同一个页面里对比。
​        本章会区分普通 ChatBot、CoT、ReAct 和任务拆解，并实现一个不依赖 API Key 的 Agent 思维模型演示服务。后端暴露模式说明接口和任务对比接口，前端通过独立 API、store、hook 和组件展示同一个任务在不同模式下的处理差异。这样读者可以先看清概念边界，再进入后续真实 Agent 调用循环。

## 16.2 最终效果
​        本章结束后，后端新增两个接口：

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

​        本章先不调用真实 LLM。第 15 章已经完成了 LLM 客户端，但第 16 章的重点是理解 Agent 的思维结构。如果一上来就把模型调用、提示词、工具调用、流式输出全部混在一起，会很难看清每个概念的边界。

## 16.3 本章要解决的问题
​        第 15 章已经可以调用 LLM，但直接调用 LLM 还不是 Agent。
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

## 16.4 本章技术方案
​        本章新增一个独立模块：

```Plain
api/app/domain/agent_thinking
api/app/application/agent_thinking_service.py
api/app/api/routes/agent_thinking.py
ui/app/lib/agent-thinking-api.ts
ui/app/stores/agent-thinking-store.ts
ui/app/hooks/use-agent-thinking.ts
ui/app/components/agent-thinking-panel.tsx
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

​        本章选择确定性演示，不调用真实 LLM，原因是：
​        这样做有两个好处。首先，它不需要 API Key，也不会受到模型随机性和网络状态影响，每次点击都能得到稳定结果，适合用来理解概念。其次，它把 ChatBot、CoT、ReAct 和任务拆解的差异放在同一张页面里，让后续接入 PlannerAgent 和 ReActAgent 时有一个清楚的参照。

## 16.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/api/router.py
api/app/api/routes/agent_thinking.py
api/app/application/agent_thinking_service.py
api/app/domain/agent_thinking/__init__.py
api/app/domain/agent_thinking/entities.py
api/app/schemas/agent_thinking.py
ui/README.md
ui/app/components/agent-thinking-panel.tsx
ui/app/hooks/use-agent-thinking.ts
ui/app/lib/agent-thinking-api.ts
ui/app/page.tsx
ui/app/stores/agent-thinking-store.ts
ui/app/types.ts
```

## 16.6 实施步骤
### 16.6.1 定义 Agent 思维领域实体
​        创建 `api/app/domain/agent_thinking/__init__.py`：

```Python
"""Agent thinking domain objects."""
```

​        创建 `api/app/domain/agent_thinking/entities.py`：

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

#### 16.6.1.1 代码讲解
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

### 16.6.2 编写 AgentThinkingService
​        创建 `api/app/application/agent_thinking_service.py`：

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

#### 16.6.2.1 代码讲解
​        `MODE_INFOS` 是模式说明。它是固定数据，所以本章不需要建表。
​        `list_modes()` 给前端页面加载右侧模式说明。这个接口不需要请求体。
​        `compare()` 是本章的核心入口。业务流程是：

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

​        这些工具还没有真正实现。现在只是让你先看到 ReAct 为什么离不开工具协议。第 17 章会正式进入 Memory 和工具协议。

### 16.6.3 定义接口 Schema
​        创建 `api/app/schemas/agent_thinking.py`：

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

#### 16.6.3.1 代码讲解
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

### 16.6.4 编写 API 路由
​        创建 `api/app/api/routes/agent_thinking.py`：

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

#### 16.6.4.1 代码讲解
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

### 16.6.5 注册路由
​        打开 `api/app/api/router.py`：

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

#### 16.6.5.1 代码讲解
​        新增路由文件后，必须在总路由里注册。
​        如果忘了这一步，文件虽然存在，但接口不会出现在 FastAPI 应用中。访问：

```Plain
/api/agent-thinking/modes
```

​        会返回 404。

### 16.6.6 扩展前端类型
​        打开 `ui/app/types.ts`，新增：

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

#### 16.6.6.1 代码讲解
​        前端类型要和后端 Schema 对齐。
​        这里的结构关系是：

```Plain
ThinkingComparisonData
  |
  +-- task
  +-- demos: ThinkingModeDemo[]
```

​        页面渲染时，会对 `demos` 做循环，为每一种模式渲染一张卡片。

### 16.6.7 封装前端 API 请求
​        创建 `ui/app/lib/agent-thinking-api.ts`：

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

#### 16.6.7.1 代码讲解
​        组件不应该直接写：

```TypeScript
fetch("/api/agent-thinking/compare")
```

​        原因是接口路径、统一响应解析和错误处理都属于 API 层职责。统一放到 `lib/agent-thinking-api.ts` 后，组件只关心“加载模式”和“生成对比”两个动作。

### 16.6.8 创建独立 zustand store
​        创建 `ui/app/stores/agent-thinking-store.ts`：

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

#### 16.6.8.1 代码讲解
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

### 16.6.9 创建 hook 管页面生命周期
​        创建 `ui/app/hooks/use-agent-thinking.ts`：

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

#### 16.6.9.1 代码讲解
​        hook 负责“页面什么时候加载数据”。
​        如果把 `useEffect()` 写在组件里，组件会同时负责：

```Plain
布局
交互
生命周期
数据请求
```

​        职责会变重。拆成 hook 后，组件只负责展示，store 负责状态，API 文件负责请求。

### 16.6.10 创建 AgentThinkingPanel 组件
​        创建 `ui/app/components/agent-thinking-panel.tsx`。
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

#### 16.6.10.1 代码讲解
​        这个组件是受控组件。`textarea` 的值来自 `task`，输入变化时调用 `onTaskChange()`。
​        点击按钮时调用 `onRun()`，组件本身不直接请求接口。这样组件可以保持简单：

```Plain
组件接收状态
组件触发事件
store 处理业务
```

​        按钮在 `running` 时禁用，避免连续点击造成重复请求。
​        `ModeList` 和 `ComparisonResult` 都接收 `LoadState`。这样加载中、错误和成功状态都有明确展示，不会出现页面空白。

### 16.6.11 在首页接入面板
​        打开 `ui/app/page.tsx`，新增导入：

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

#### 16.6.11.1 代码讲解
​        `page.tsx` 仍然只做页面编排。它不直接写接口请求，也不直接写对比逻辑。
​        首页现在的大结构是：

```Plain
状态区域
Agent 思维模型面板
聊天工作台
```

​        这个顺序是有原因的：先让用户理解任务可以用哪些模式处理，再进入下方真实会话区。第 17 章开始，Agent 能力会逐渐从演示面板迁移到真实会话流程。

## 16.7 关键理解
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

## 16.8 技术难点与亮点
​        本章的难点是把概念讲清楚，同时不把概念写成散乱文案。聊天回复、思考摘要、工具行动和任务计划不是同一类东西；页面可以展示过程摘要和执行步骤，但不应该把模型隐藏推理当成普通内容暴露出来。即使这一章只是概念演示，也要有可运行接口和可观察页面。
​        项目亮点在于它不依赖真实 LLM，也能讲清 Agent 思维差异。新增接口稳定可测，前端使用独立状态管理，没有污染会话 store；页面还能直观看到 ReAct 为什么需要工具协议，以及任务拆解为什么会成为 PlannerAgent 的前置能力。

## 16.9 面试考点
​        面试里可以围绕 ChatBot 和 Agent 的区别展开：ChatBot 更像直接回答，Agent 则强调目标、计划、工具和观察。CoT 适合复杂推理，但页面上更应该展示可解释摘要，而不是完整隐藏推理。ReAct 中的 Reason 对应判断和选择，Act 对应工具调用或外部动作；任务拆解则把长任务变成可执行计划。概念演示也写成 API，是为了让后续真实 Agent 能平滑替换演示数据。

## 16.10 运行验证
​        下面命令默认在项目根目录执行。

### 16.10.1 检查后端代码

```Bash
cd api
uv run python -m compileall app
```

​        预期没有 Python 编译错误。

### 16.10.2 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

​        预期没有 TypeScript 报错。

### 16.10.3 启动服务
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

### 16.10.4 验证模式列表接口

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

### 16.10.5 验证任务对比接口

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

### 16.10.6 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        页面中应该能看到“Agent 思维模型”面板。
​        操作步骤：
​        验证时输入一个任务，点击“生成对比”，页面应当出现四张对比卡片。普通 ChatBot 卡片会直接给出整体回答，CoT 卡片会展示分析摘要，ReAct 卡片会出现可能调用的工具，任务拆解卡片会把目标拆成多个阶段。这个结果说明后端演示接口和前端状态流都已经接通。

## 16.11 常见问题

### 16.11.1 访问 `/api/agent-thinking/modes` 返回 404 怎么办
​        检查 `api/app/api/router.py` 是否注册了 `agent_thinking.router`。如果后端代码已经存在但路由没有挂进去，FastAPI 就不会暴露这一组接口。

### 16.11.2 页面看不到 Agent 思维模型面板怎么办
​        检查 `ui/app/page.tsx` 是否已经引入并渲染 `AgentThinkingPanel`。如果 Docker 环境里仍然是旧页面，还需要重新构建并重启 UI。

### 16.11.3 为什么本章不直接调用第 15 章的 LLM
​        本章目标是理解 Agent 思维结构。先用稳定演示跑通概念，再接入真实模型更容易理解。否则 API Key、模型随机性、网络失败和提示词效果都会混在一起，反而看不清模式差异。

### 16.11.4 为什么 ReAct 的工具只是字符串
​        第 16 章只解释工具调用在 ReAct 中的位置，因此先用字符串表示可能调用的工具。第 17 章会正式定义工具协议和工具 schema，让这些字符串变成可执行工具能力。

## 16.12 本章小结
​        本章完成了 Agent 思维模型的第一个可运行演示。后端定义了 ChatBot、CoT、ReAct 和任务拆解四种模式，新增模式说明接口和任务对比接口；前端新增 Agent 思维模型面板，并继续保持 API、store、hook、组件拆分。这个稳定演示说明了为什么 Agent 不只是聊天框，而需要规划、工具和可观察过程。
​        第 17 章会进入 Agent 记忆与工具协议，实现 Memory、工具装饰器、工具 schema 和基础 Agent 调用循环。
