# 第二十四章. 多 Agent 协作统筹

![](../assets/ch13-loop.jpg)


一个经理 Agent 拆子任务，几个工人并行，再汇总。观察结果是一种特殊的 tool output：`kind: "multi_agent_result"`。前端 `parseToolOutput` 已经认识这个形状，卡片上能画出子任务标题。后端 TypeScript 还不会产出它。

并行不是越快越好。共享一个数据库会话去 gather 一堆写，会撞 flush。旧 Runtime 为此加过锁。迁过来时记住：要么串行记审计，要么每条调用自己的短会话。

经理自己不要跑 shell。它只分配和验收。工人才碰沙箱。角色写在计划的 assignee 上，不要靠模型临时发挥。

---

[← 第二十三章. A2A 协议与工具接入](23-A2A%20协议与工具接入.md) · [返回目录](../README.md) · [第二十五章. 设置面板落成 →](25-设置面板落成.md)
