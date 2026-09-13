# 第四十六章. Tool Runtime 权限、幂等与审计

![](../assets/ch12-tools.jpg)


一次工具调用：鉴权、风险、审批、幂等键、超时、脱敏、落制品、写审计。handler 只在门说 yes 之后跑。TypeScript 还没有这层，沙箱 HTTP 是裸的，靠沙箱自己的 API Key 挡外部。接 Runtime 时不要让路由继续直打沙箱。

幂等键撞车应返回第一次的结果，而不是再执行一遍 `rm`。审计表就是 `tool_invocations`。列表接口先占位。

---

[← 第四十五章. Memory Control Plane 与 Checkpoint DAG](45-Memory%20Control%20Plane%20与%20Checkpoint%20DAG.md) · [返回目录](../README.md) · [第四十八章. 键盘优先 TUI 客户端 →](48-键盘优先%20TUI%20客户端.md)
