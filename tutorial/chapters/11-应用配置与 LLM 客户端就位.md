# 第十一章. 应用配置与 LLM 客户端就位

配置在第 3 章已经进了 `loadSettings()`。这一章把模型从「没有密钥就离线直答」接到真的 HTTP 调用上。不要为每个厂商写一个 SDK。OpenAI 的 `/chat/completions` 已经被国内一串网关模仿，DeepSeek、通义、Ollama 都吃这套。一个 `fetch` 就够。

密钥只从环境来，`LLM_API_KEY`。不要写进 yaml 再提交。`LLM_BASE_URL` 默认 `https://api.deepseek.com/v1`，`LLM_MODEL` 默认 `deepseek-chat`。换模型改这两行，不要改业务。

![电台：同一套协议，换频率就能说话](../assets/ch11-llm.jpg)

`generateAnswer` 现在住在 `agent-stream.ts` 里，直答路径调用它。有密钥就 POST JSON：`messages`、`temperature`、`model`。失败不要把上游 HTML 错误页转给用户，回一句带 HTTP 状态的中文说明，让 SSE 仍然能 `task_done`。空内容同样当失败，别把空白气泡当成功。

```ts
const response = await fetch(`${settings.llmBaseUrl.replace(/\/$/, "")}/chat/completions`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${settings.llmApiKey}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: settings.llmModel,
    messages: [
      { role: "system", content: "You are AtlasAgent. Answer concisely with evidence when you have it." },
      { role: "user", content: prompt },
    ],
    temperature: 0.2,
  }),
});
```

超时、连接池、`enable_thinking` 这类事，旧 Python 客户端做过一轮。TypeScript 这一层还没抽成独立 `OpenAICompatibleClient`。直答先稳。等执行机迁过来，再把 client 提出来给规划、批评、摘要共用，避免每个服务自己 `fetch` 一份。

本地验证：不配密钥，发「ping」，应看到离线说明。配上 Key 再发一次，回答应变成长得像模型的句子，`task_done` 仍然在。不要在这一章接 function calling。工具协议是下一章。

---

[← 第十章. 文件存储拓界](10-文件存储拓界.md) · [返回目录](../README.md) · [第十二章. Agent 思维、Memory 与工具协议 →](12-Agent%20思维、Memory%20与工具协议.md)
