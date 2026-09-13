# 第十四章. AgentTaskRunner 与 Redis Stream 任务流转

浏览器不能一直开着 HTTP 等到第 38 步。请求应马上返回「已入队」，真正执行在后台。旧实现用 Redis Stream 做多副本队列，本机用 SQLite 文件队列。TypeScript 运行时目前把直答做在请求内的 async generator 里，没有独立 worker。队列是下一步要补的，契约可以先定。

任务至少有：id、session_id、类型（先只支持 execute_plan）、状态。认领要有空闲窗口，默认十五分钟——Agent 跑过 30 秒是常态，太短会被另一副本抢走。回收要在每次 poll 时做，不能只在进程启动时 XCLAIM 一次。

![队列是河，任务是漂过去的光](../assets/ch14-queue.jpg)

`/api/control-plane/tasks` 已经能创建和列出任务，SQLite 表 `agent_tasks` 在。它还不是执行队列，只是给 TUI 和以后的驾驶舱一个能写进去的地方。状态从 pending 到 running 的跳变，要等 runner 接上。

本地现在没有 Redis 也能用工作台，因为对话不经过队列。哪天要把「关浏览器任务还在跑」做出来，再在 `api-ts` 里加一层 `AgentTaskQueue`：接口保持 enqueue / reserve / ack，底下先内存或 SQLite，需要多副本再接 Redis。不要一上来就把 Compose 绑回 Redis，单机体验会倒退。

---

[← 第十三章. PlannerAgent 与 ReActAgent 执行闭环](13-PlannerAgent%20与%20ReActAgent%20执行闭环.md) · [返回目录](../README.md) · [第十五章. 上下文工程 →](15-上下文工程.md)
