# AtlasAgent 自研状态机设计

## 目标

在不引入 LangGraph、LangChain 或其他 Agent 编排框架的前提下，把当前线性的 Planner -> ReAct 循环改造成显式的 Plan -> Execute -> Reflect -> Summarize 状态机，并先修复工具失败仍被记录为步骤完成的问题。

## 约束

- 不引入 Agent 编排框架。
- 不新增 SHA-256、状态哈希、Schema 哈希或哈希校验。
- 不用规则兜底、吞异常或伪成功掩盖模型与工具错误。
- 保留现有 Memory、RAG、ToolRuntime、Session SSE 和直接聊天路径。
- 新增生产函数遵守 50 行限制，新文件不超过 300 行。

## 首期边界

首期只交付一个可运行纵切片：类型化状态、纯路由器、严格 Critic、状态感知的单步执行，以及 ReAct 主执行路径接入。持久 Run Ledger、独立 Worker、原生 Function Calling、Coder/Critic 沙箱和 Prometheus 分别作为后续独立变更，以便每一阶段都有可验证基线。

## 状态模型

```text
EXECUTING
  -> REFLECTING
       accept + remaining -> EXECUTING(next step)
       accept + finished  -> SUMMARIZING
       retry              -> EXECUTING(same step)
       replan             -> REPLANNING
       fail               -> FAILED
  -> SUMMARIZING
  -> COMPLETED

approval_required -> BLOCKED
```

`AgentRunState` 是 `frozen=True, slots=True` 的不可变值对象。它只保存可观察状态，不保存模型隐藏推理：

- `run_id`、`session_id`
- 当前计划快照和 `plan_revision`
- `phase`、`step_index`、`attempt`
- 已产生的 `StepObservation`
- 最近一次 `Reflection`
- `replan_feedback`、`final_answer`、`error`

`AgentStateRouter` 是纯函数组件，不访问数据库、LLM 或工具。所有非法转换直接抛出明确异常。

## 工具结果语义

| ToolInvocationStatus | 状态机行为 |
| --- | --- |
| `succeeded`、`deduplicated` | 进入 Reflect，由 Critic 判断是否接受结果 |
| `failed`、`timed_out`、`denied` | 进入 Reflect，不能产生 `step_completed` |
| `approval_required` | 进入 `BLOCKED`，产生 `step_blocked` |
| `pending`、`running` | 非法终态，显式报错 |

ReAct 单步执行只产生 `step_started` 与 `tool_called`。只有 Critic 返回 `accept` 后才能写入 `step_completed`。`retry` 保持当前步骤并增加 attempt；`fail` 写入 `step_failed` 和 `task_error`。

## Critic 协议

Critic 接收计划步骤与真实 `ToolCallResult`，只输出以下 JSON：

```json
{
  "action": "accept | retry | replan | fail",
  "reason": "可观察原因"
}
```

解析失败、未知 action、空 reason，以及对非成功工具结果返回 `accept` 都是协议错误，直接暴露为失败，不切换到规则模式。

## 兼容策略

- 普通聊天继续走 `AgentRunnerService._stream_direct_answer()`。
- Planner 的现有计划事件格式保持不变。
- 现有 SSE 事件保留，新增 `step_reflected`、`step_failed`、`step_blocked`。
- 同步 `execute_latest_plan()` 收集统一流式执行器产生的 SessionEvent，避免维护第二套循环。
- `replan` 在首期形成显式状态和事件；若尚未配置 Replanner，则明确结束为错误，不隐式继续旧计划。

## 验证

- 纯路由矩阵覆盖 accept、retry、replan、fail、blocked 和非法工具终态。
- 回归测试复现并修复 denied/failed/timed_out 仍产生 `step_completed` 的问题。
- Critic 测试验证严格 JSON 和非成功结果不可 accept。
- 编排测试验证成功路径的事件顺序，以及失败路径不存在 `step_completed`、`task_done`。
- 完整后端测试必须保持通过。
