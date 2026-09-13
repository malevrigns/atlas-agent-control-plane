# 第十三章. PlannerAgent 与 ReActAgent 执行闭环

直答用 `mode: "chat"`。真要干活，得先有一份计划：步骤 id、标题、期望输出。计划本身是事件 `plan_created`，不是一张独立的「计划表」。刷新之后前端从事件里把 steps 拼回来，执行中的状态用后续的 `step_started` / `tool_called` / `step_completed` 覆盖。

现行 TypeScript 控制平面还停在直答外壳。`agent-stream.ts` 不会产出 `plan_created`。这一章讲闭环长什么样，免得把 chat 和 plan 两条时间线搅在一起。

![回路：走一步，看一眼，再决定](../assets/ch13-loop.jpg)

规划器吃用户目标和上下文，吐出 steps。执行器对每一步调工具，直到该步的期望输出能被某次观察满足，或次数用尽。批评器看观察，决定 accept / retry / replan / fail。不要让模型自己宣布「我做完了」——完成是后面验收门禁的事。

前端 `AgentRunBlock` 一张卡片对应一次 `plan_created`。历史卡片的 `executing` 必须是 false，否则旧任务会永远转圈。事件要按计划时间窗切开，resume 复用同一个 plan_id 时取时间最晚的终结事件。

等执行机迁进 `api-ts`，stream 里会在 `message_created` 之后出现 `plan_created`，然后才是步骤。在那之前，工作台的直答仍然有用：它证明信封、SSE、落库是通的。不要为了「看起来像 Agent」去假造计划事件。

---

[← 第十二章. Agent 思维、Memory 与工具协议](12-Agent%20思维、Memory%20与工具协议.md) · [返回目录](../README.md) · [第十四章. AgentTaskRunner 与 Redis Stream 任务流转 →](14-AgentTaskRunner%20与%20Redis%20Stream%20任务流转.md)
