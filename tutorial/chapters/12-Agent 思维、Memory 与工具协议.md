# 第十二章. Agent 思维、Memory 与工具协议

直答能聊天。工作台要的是「调用工具之前先过门」。工具协议不是 OpenAI 的 function calling 本身，而是控制平面对一次调用的记录：谁、以什么参数、风险几级、是否幂等、输出落在哪。

现行 TypeScript API 还没有完整的 ToolRuntime。直答路径不调工具。这一章把约定写在前面，避免以后每个 handler 自己 `fetch` 沙箱。一次调用至少留下：工具名、参数、request_hash、decision、status、耗时。表名沿用 `tool_invocations`。查询接口已经在 `/api/control-plane/tool-invocations` 占位，现在返回空列表。

![工具是具体的，协议是同一把尺子](../assets/ch12-tools.jpg)

思维过程不要和最终回答混在一条消息里。SSE 上 `thinking_delta` 是过程，`answer_delta` 是给用户看的正文。落库时思维进 `task_done.payload.reasoning`，正文进 assistant 消息。前端 `ReasoningBlock` 和 `MessageBubble` 分开渲染。

记忆更往后。现在 `GET /api/sessions/:id/context` 返回的 `memory_context.items` 是空数组，预算字段是填过的。先把位置留好，第 27 章再往里塞。不要在消息表里用特殊 role 冒充长期记忆。

这一章没有能跑的新命令。你要是急着看工具调用，先用沙箱的 `/api/files` 和 `/api/shell` 手工打。等 Runtime 迁过来，这些 HTTP 会变成工具 handler 背后的唯一出口。

---

[← 第十一章. 应用配置与 LLM 客户端就位](11-应用配置与%20LLM%20客户端就位.md) · [返回目录](../README.md) · [第十三章. PlannerAgent 与 ReActAgent 执行闭环 →](13-PlannerAgent%20与%20ReActAgent%20执行闭环.md)
