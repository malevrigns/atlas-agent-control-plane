# 第十七章. Agent Memory 与工具协议

> **演进提示**：本章保留了早期教学版的 `ConversationMemory + ToolRegistry` 最小闭环，用于讲清基本概念。完整项目已在第 69、70 章升级为分层 Memory Control Plane 和统一 Tool Runtime；生产代码请以后两章为准。

## 17.1 本章目标
​        第 16 章已经把 ChatBot、CoT、ReAct 和任务拆解放在同一个页面里比较过，但那一章仍然停留在“思维模型”的层面。真正进入 Agent 执行之前，还需要补上两个基础能力：一个是 Agent 运行时要看的上下文，也就是 Memory；另一个是 Agent 能够识别、选择和调用的工具协议。
​        本章会把这两部分做成一个最小闭环。后端会定义 `ConversationMemory`、工具 schema、工具注册表和内置教学工具，再通过 `AgentCoreService` 把用户任务、工具选择、工具结果和下一步提示写进同一段 Memory。前端则继续按照 API、store、hook、组件拆分，把工具列表、参数 schema、Memory 时间线和工具调用结果展示出来。这样到了第 18 章和第 19 章时，PlannerAgent 和 ReActAgent 就不是凭空出现，而是接在这一章搭好的上下文和工具系统之上。

## 17.2 最终效果
​        本章结束后，后端新增两个接口：

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
​        本章仍然不实现完整 PlannerAgent 和 ReActAgent。它先把 Memory 和工具协议搭起来。第 18 章会让 PlannerAgent 生成计划，第 19 章会让 ReActAgent 根据计划逐步执行。

## 17.3 本章要解决的问题
​        第 16 章已经解释了 ChatBot、CoT、ReAct 和任务拆解的区别。
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

​        所以本章先做一个最小闭环：

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

## 17.4 本章技术方案
​        后端新增模块：

```Plain
api/app/domain/agent_core/memory.py
api/app/domain/agent_core/tools.py
api/app/infrastructure/agent_tools/builtin.py
api/app/application/agent_core_service.py
api/app/api/routes/agent_core.py
```

​        前端新增模块：

```Plain
ui/app/lib/agent-core-api.ts
ui/app/stores/agent-core-store.ts
ui/app/hooks/use-agent-core.ts
ui/app/components/agent-core-panel.tsx
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

​        本章只使用内置确定性工具，不调用真实外部工具。这样做是为了先把协议讲清楚：工具需要先被描述给模型或前端，调用前要根据 schema 检查参数，调用后要把结果重新写回 Memory，最后再由前端把这个过程展示出来。等这个闭环稳定后，再把搜索、文件、Shell 或浏览器工具接进来，复杂度才不会一下子失控。

## 17.5 新增和修改的文件

```Plain
README.md
api/README.md
api/app/api/router.py
api/app/api/routes/agent_core.py
api/app/application/agent_core_service.py
api/app/domain/agent_core/__init__.py
api/app/domain/agent_core/memory.py
api/app/domain/agent_core/tools.py
api/app/infrastructure/agent_tools/__init__.py
api/app/infrastructure/agent_tools/builtin.py
api/app/schemas/agent_core.py
docs/course/chapters/17-agent-memory-tools.md
docs/course/outline.md
ui/README.md
ui/app/components/agent-core-panel.tsx
ui/app/hooks/use-agent-core.ts
ui/app/lib/agent-core-api.ts
ui/app/page.tsx
ui/app/stores/agent-core-store.ts
ui/app/types.ts
```

## 17.6 实施步骤
### 17.6.1 定义 Agent Memory
​        创建 `api/app/domain/agent_core/__init__.py`：

```Python
"""Agent memory and tool protocol domain objects."""
```

​        创建 `api/app/domain/agent_core/memory.py`：

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

#### 17.6.1.1 代码讲解
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

### 17.6.2 定义工具协议
​        创建 `api/app/domain/agent_core/tools.py`：

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

#### 17.6.2.1 代码讲解
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

### 17.6.3 编写内置工具
​        创建 `api/app/infrastructure/agent_tools/__init__.py`：

```Python
"""Built-in agent tools."""
```

​        创建 `api/app/infrastructure/agent_tools/builtin.py`：

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

#### 17.6.3.1 代码讲解
​        这里定义了三个教学工具。`summarize_text` 用来演示最简单的“文本输入到文本输出”，`extract_keywords` 用来模拟 Agent 从任务中抓重点，`draft_plan` 则把任务改写成三个粗粒度步骤。它们的能力都很克制，但三者足以覆盖工具 schema、参数构造、工具执行和结果回写 Memory 的完整路径。
​        这些工具现在都不调用外部 API，原因是本章重点是工具协议，而不是工具能力本身。真实工具会牵涉网络、文件系统、权限、超时和错误处理，如果在这里提前引入，读者反而不容易看清工具协议这一层到底负责什么。
​        `build_builtin_tool_registry()` 负责把工具注册到 `ToolRegistry`。后续新增搜索工具、文件工具、Shell 工具时，也会进入类似的注册流程。

### 17.6.4 编写 AgentCoreService
​        创建 `api/app/application/agent_core_service.py`：

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

#### 17.6.4.1 代码讲解
​        `run_demo()` 是本章后端最重要的业务流程：

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

​        本章的 `_choose_tool()` 只是简单规则。第 19 章会让 LLM 根据上下文选择工具。

### 17.6.5 定义接口 Schema
​        创建 `api/app/schemas/agent_core.py`：

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

#### 17.6.5.1 代码讲解
​        Schema 是接口契约。
​        前端最关心这三个结构：

```Plain
tools       当前有哪些工具
messages    Memory 时间线
tool_result 工具执行结果
```

​        `AgentCoreDemoRequest.tool_name` 允许为空。为空时后端会根据任务内容自动选择工具；有值时使用前端选中的工具。

### 17.6.6 编写 API 路由
​        创建 `api/app/api/routes/agent_core.py`：

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

#### 17.6.6.1 代码讲解
​        路由层继续保持薄：

```Plain
接收请求
调用 service
把领域对象转成 response schema
返回 ApiResponse
```

​        这里有很多 `to_*_response()` 函数，它们看起来有点啰嗦，但很重要。
​        原因是领域层和接口层要隔离。领域层以后可能把 `ToolDefinition` 改得更适合模型，接口层仍然可以保持前端需要的结构。

### 17.6.7 注册路由
​        打开 `api/app/api/router.py`：

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

#### 17.6.7.1 代码讲解
​        新增路由文件后必须注册到总路由。
​        否则 `agent_core.py` 文件存在，但接口不会被 FastAPI 加载，访问时会得到 404。

### 17.6.8 扩展前端类型
​        打开 `ui/app/types.ts`，新增：

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

#### 17.6.8.1 代码讲解
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

### 17.6.9 封装前端 API
​        创建 `ui/app/lib/agent-core-api.ts`：

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

#### 17.6.9.1 代码讲解
​        组件不直接写接口路径。
​        `fetchAgentTools()` 只负责读取工具列表。
​        `runAgentCoreDemo()` 只负责提交任务和工具名。
​        这样组件不需要知道后端返回外层是 `ApiResponse`，也不需要重复写 `fetch()`。

### 17.6.10 创建前端 store
​        创建 `ui/app/stores/agent-core-store.ts`：

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

#### 17.6.10.1 代码讲解
​        这个 store 独立于 `session-store` 和 `agent-thinking-store`。
​        原因是第 17 章的状态是工具协议演示：

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

### 17.6.11 创建 hook
​        创建 `ui/app/hooks/use-agent-core.ts`：

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

#### 17.6.11.1 代码讲解
​        hook 负责页面生命周期。
​        组件挂载时，`useEffect()` 会调用 `loadTools()`，这样页面一打开就能看到工具列表。

### 17.6.12 创建 AgentCorePanel 组件
​        创建 `ui/app/components/agent-core-panel.tsx`。
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

#### 17.6.12.1 组件讲解
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

### 17.6.13 在首页接入 AgentCorePanel
​        打开 `ui/app/page.tsx`，新增导入：

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

#### 17.6.13.1 代码讲解
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

## 17.7 关键理解
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

## 17.8 技术难点与亮点
​        本章的难点不在代码量，而在边界划分。Memory、聊天记录和数据库持久化看起来都在保存消息，但 Memory 面向的是“本次推理要给模型看的上下文”；工具 schema 和工具函数也不能混在一起，前者用于描述和选择，后者才是真正执行。装饰器从函数签名生成参数描述，工具注册表负责发现和查找工具，工具执行结果再回写 Memory，这几步必须连成一条清晰链路。
​        项目亮点在于后续 ReActAgent 需要的基础结构已经出现了。新增工具时，不需要在多个地方硬编码工具信息，只要用装饰器声明名称、描述和参数说明，再注册到 `ToolRegistry` 即可。前端也没有等到最后才补页面，而是同步展示工具 schema、Memory 和结果，这会让读者在开发过程中始终看到 Agent 内部状态的变化。

## 17.9 面试考点
​        面试里可以从 Agent Memory 和普通聊天消息的区别讲起。普通聊天消息主要面向展示和历史记录，Agent Memory 更强调本次推理上下文；工具 schema 的价值在于让模型或服务知道有哪些工具、每个工具需要什么参数；装饰器解决的是“业务函数”和“工具描述”重复维护的问题；`ToolRegistry` 则提供统一的工具注册、列表查询和按名称调用入口。工具结果必须写回 Memory，是因为 Agent 后续回答需要基于观察结果继续判断。本章不直接实现完整 ReActAgent，是为了先把 Memory 和工具协议两块地基铺稳。

## 17.10 运行验证
​        下面命令默认在项目根目录执行。

### 17.10.1 检查后端代码

```Bash
cd api
uv run python -m compileall app
```

​        预期没有 Python 编译错误。

### 17.10.2 检查前端类型

```Bash
cd ../ui
pnpm typecheck
```

​        预期没有 TypeScript 报错。

### 17.10.3 启动服务
​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        第 17 章修改了 API 和 UI 代码，需要重新构建：

```Bash
docker compose build --pull=false api ui
docker compose up -d --force-recreate api ui nginx
```

​        这里重启 Nginx 是为了让它重新解析新的 API/UI 容器地址，避免旧容器 IP 导致 502。

### 17.10.4 验证工具列表接口

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期返回中有：

```Plain
summarize_text
extract_keywords
draft_plan
```

### 17.10.5 验证 Agent 核心演示接口

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

### 17.10.6 验证页面
​        访问：

```Plain
http://localhost:8088
```

​        页面中应该能看到“Agent 记忆与工具协议”面板。
​        操作步骤：
​        验证时先输入一个任务，再选择 `draft_plan`、`extract_keywords` 或 `summarize_text` 中的一个工具，随后点击“运行演示”。页面应当同时更新 Memory 时间线和工具结果区域。Memory 中先出现用户任务，再出现 Agent 决定调用工具的消息，随后是带工具名的 `tool` 消息，最后出现提示下一步可以交给 LLM 继续生成回答的 assistant 消息。

## 17.11 常见问题

### 17.11.1 访问 `/api/agent-core/tools` 返回 404 怎么办
​        检查 `api/app/api/router.py` 是否注册了 `agent_core.router`。如果路由文件已经写好但没有挂到总路由，FastAPI 不会加载这一组接口，浏览器或 curl 访问时就会返回 404。

### 17.11.2 访问网关返回 502 怎么办
​        第 17 章同时改了 API 和 UI 代码，Docker 环境里如果还在运行旧容器，Nginx 可能代理到旧地址或不可用容器。可以先执行 `docker compose build --pull=false api ui`，再执行 `docker compose up -d --force-recreate api ui nginx`，让 API、UI 和网关一起重新创建。

### 17.11.3 页面里没有新面板怎么办
​        检查 `ui/app/page.tsx` 是否已经引入 `AgentCorePanel` 和 `useAgentCore`，并确认页面里已经渲染这个面板。如果源码已经改完但页面仍然没有变化，通常是 UI 镜像没有重新构建，或者浏览器打开的仍然是旧前端资源。

### 17.11.4 为什么工具只是内置函数，不是真实搜索或文件工具
​        本章目标是工具协议，而不是外部工具能力。内置函数能让参数 schema、工具注册、工具调用和 Memory 回写先稳定下来。真实文件工具、Shell 工具、浏览器工具会在后续沙箱阶段接入，届时它们也会复用本章建立的工具协议思路。

## 17.12 本章小结
​        本章完成了 Agent 核心的第二块基础能力。后端定义了 Agent Memory、工具参数、工具 schema 和工具执行结果，并用装饰器把普通 Python 函数封装成可注册、可列举、可按名称调用的工具；应用服务把用户任务、工具选择、工具结果和下一步提示写入同一段 Memory；前端则新增了工具协议演示面板，把工具列表、参数 schema、Memory 时间线和工具输出放在同一个可观察界面中。
​        第 18 章会进入 PlannerAgent 任务规划，让 LLM 根据用户任务生成结构化计划，并在前端展示计划目标、步骤和预期输出。到那时，本章的 Memory 和工具协议会继续作为后续 Agent 执行链路的基础。
