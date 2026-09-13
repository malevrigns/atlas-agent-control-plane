# 第四十五章. Memory Control Plane 与 Checkpoint DAG

![](../assets/ch27-memory.jpg)


记忆要有写入门禁和生命周期。Checkpoint 是带父节点的恢复点，不是把整份 state JSON 随手 dump。TypeScript 里这两张表都还没建。会话事件目前承担了「发生过什么」；真正的 DAG 要等执行机长出来再挂上。

设计上仍然有效：事件是事实源，任务状态是可重建视图，checkpoint 是验证过的恢复点。不要用前端 localStorage 冒充。

---

[← 第四十四章. 项目简历落笔](44-项目简历落笔.md) · [返回目录](../README.md) · [第四十六章. Tool Runtime 权限、幂等与审计 →](46-Tool%20Runtime%20权限、幂等与审计.md)
