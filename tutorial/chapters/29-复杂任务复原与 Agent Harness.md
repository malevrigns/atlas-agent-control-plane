# 第二十九章. 复杂任务复原与 Agent Harness

![](../assets/ch13-loop.jpg)


进程会挂。第 38 步死了，不应从第 1 步重来。恢复靠事件和 checkpoint：已完成的步骤进 history，`start_step_index` 指向下一刀。若所有步骤都完成、死在 summarize，应直接进 summarize，而不是把下标顶出数组。

Harness 是固定剧本：给定输入，期望某串事件。TypeScript 还没有这套。直答至少要保证：中途 abort、刷新、再发，库里的消息仍在。那是复原的最小集。

`resume: true` 的 stream 不要重复插入用户消息。前端重试按钮走这条。

---

[← 第二十八章. Agent Runner 与模型工具选择](28-Agent%20Runner%20与模型工具选择.md) · [返回目录](../README.md) · [第三十章. 生产构建、测试与可观测性 →](30-生产构建、测试与可观测性.md)
