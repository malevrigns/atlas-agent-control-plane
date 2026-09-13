# 第二十章. SearchTool 搜索能力成形

Agent 不能只会读工作区。公开网上的资料要经过搜索工具，结果当成观察，而不是当成真理。旧实现接 Bing。TypeScript 控制平面还没有这条工具。接口一旦加上，应长得和其他工具一样：名字 `web_search`，参数 `query`、`count`，输出一段可引用的摘要列表，每条带 URL。

密钥用 `BING_SEARCH_API_KEY`，没有密钥时工具应返回明确失败，而不是空数组假装搜过。超时用 `SEARCH_TIMEOUT_SECONDS`。市场默认 `zh-CN`。

![工具还是工具，只是刃口换成了检索](../assets/ch12-tools.jpg)

搜索不要在 API 进程里无界并发。和 shell 一样计入步骤预算。结果进 `tool_called` 事件，前端预览面板展示标题和链接。点击链接在新标签打开，rel 只要 http/https。

在 Runtime 接通之前，这一章没有可跑的新命令。你可以用普通浏览器验证「前端预览将来要展示的字段」长什么样：title、url、snippet。字段越少越好，模型摘要已经够吵了。

---

[← 第十九章. VNC 远程桌面与工具预览](19-VNC%20远程桌面与工具预览.md) · [返回目录](../README.md) · [第二十一章. MCP 协议与工具接入 →](21-MCP%20协议与工具接入.md)
