# 第七章. 对话消息与 SSE 事件流

会话空着没有用。用户打字，系统要一边落库一边把过程推到浏览器。落库的是消息；推上去的是事件。这两张表不要合成一张——消息是对话正文，事件是「发生过什么」，包括计划、工具、失败，刷新之后时间线靠事件重建。

`session_messages` 只有 role 和 content。`session_events` 是 `type` 加一段 JSON `payload`。用户发言时两张表各写一行：消息本身，以及 `message_created`。未读数加一。助手回答同样落两条，但不加未读。

![光在线里走，页面才能跟](../assets/ch07-stream.jpg)

真正让工作台「活」的是 `POST /api/sessions/:id/messages/stream`。它不是一次 JSON 返回，而是 SSE：`event: 名字` 下一行 `data: JSON`，块与块之间空行。Hono 用 `streamSSE` 写。生成器在 `agent-stream.ts`：

```ts
export async function* streamUserMessage(...) {
  const running = await sessions.updateStatus(sessionId, "running");
  yield { event: "session_status", data: running };

  const created = await sessions.createUserMessage(sessionId, content);
  yield { event: "message_created", data: created.event };

  yield { event: "answer_started", data: { session_id: sessionId, mode: "chat" } };
  const answer = await generateAnswer(settings, content);
  // answer_delta 切片推送
  const assistant = await sessions.createAssistantMessage(sessionId, answer);
  yield { event: "task_done", data: done };
}
```

没有 `LLM_API_KEY` 时，`generateAnswer` 返回一段离线说明，链路仍然完整：事件有了，消息有了，刷新不会丢。配了密钥就打 OpenAI 兼容的 `/chat/completions`。不要在这一章把 ReAct 循环塞进来。直答先通，计划执行是第 13 章。

前端 `readSseStream` 按 `\n\n` 切块。坏 JSON 丢掉，不要整条流炸掉。切会话必须 `AbortController.abort()`，否则旧流的 `tool_called` 会在 700 毫秒展示延迟之后写进新会话。流必须同源，cookie 才能带上——生产走 Nginx 且 `proxy_buffering off`，开发走 App Router 的 stream 代理，不要让浏览器直连 `127.0.0.1:8000`。

```bash
curl -N -X POST http://127.0.0.1:8000/api/sessions/$ID/messages/stream \
  -H "Content-Type: application/json" \
  -d "{\"content\":\"ping\"}"
```

应陆续看到 `session_status`、`message_created`、`answer_delta`、`task_done`。再 `GET .../messages`，应有 user 和 assistant 各一条。

---

[← 第六章. 会话开立与左侧列表](06-会话开立与左侧列表.md) · [返回目录](../README.md) · [第八章. 会话状态与任务收放 →](08-会话状态与任务收放.md)
