# 第二十八章. Agent Runner 与模型工具选择

![](../assets/ch13-loop.jpg)


Runner 决定这一步把哪些工具 schema 喂给模型。不是把注册表全倒进去。模块开关关掉的工具不应出现。模型用 function calling 挑一个，Runtime 再执行。TypeScript 直答路径还没有 tools 字段。

选择策略写在配置：`auto` / `none` / `required`。调试时用 none，强迫模型说话不调工具。生产用 auto。required 只适合「这一步必须调搜索」这种窄场景。

重复调用同一工具同一参数，要靠幂等和缓存拦住，不要靠提示词求它别调。那是第 46 章和第 60 章。

---

[← 第二十七章. 长期记忆与上下文注入](27-长期记忆与上下文注入.md) · [返回目录](../README.md) · [第二十九章. 复杂任务复原与 Agent Harness →](29-复杂任务复原与%20Agent%20Harness.md)
