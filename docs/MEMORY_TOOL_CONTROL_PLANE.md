# Memory 与 Tool Control Plane

本文件描述升级后的事实边界、状态恢复、记忆写入与工具执行契约。

## 1. 事实源与物化状态

AtlasAgent 不再把一段可变文本当作任务的唯一事实。系统保留三层数据：

1. 会话事件与工具调用审计是 append-only 事实记录；
2. Artifact 保存大输出、文件、补丁、日志、截图和测试报告，按 SHA-256 内容寻址；
3. `agent_tasks` 是可更新的工作状态，Checkpoint 是带状态哈希的可恢复快照。

任务状态至少包含目标、验收标准、需求、决策、进度、已知失败、待决问题、下一步、必须保留约束、环境引用和制品引用。更新使用 `expected_version` 做乐观并发控制，避免后写覆盖先写。

## 2. Checkpoint DAG

每个 Checkpoint 指向可选的父 Checkpoint，并记录：

- 覆盖的事件序号区间；
- 完整或增量快照；
- 稳定序列化后的 `state_hash`；
- `CheckpointValidator` 生成的验证报告。

验证器会拒绝缺少必要字段、需求/决策无证据、事件区间非法，或丢失父节点 `must_preserve` 约束的快照。环境指纹缺失和活动任务无下一步会产生警告。

## 3. 类型化长期记忆

`agent_memories` 在原四类内容之上增加以下控制字段：

| 维度 | 作用 |
| --- | --- |
| `scope` / `scope_ref` | 限定 global、project、task、session 等使用范围 |
| `status` | candidate、verified、superseded、rejected 等生命周期 |
| `confidence` / `authority` | 表达可信度与来源权威等级 |
| `evidence_refs` / `provenance` | 指向消息、事件、制品或外部来源 |
| `valid_from` / `valid_to` | 让记忆自然失效 |
| `supersedes_id` | 显式连接被替代记忆 |
| `content_hash` | 去重、审计和稳定引用 |

`MemoryWriteGate` 先把抽取结果作为 candidate；只有证据、范围和质量满足策略后，记忆才能 verified。检索默认只注入已验证、未过期、未被替代且不含秘密的记录。

检索分数综合语义/词项相关度、范围匹配、重要度、可信度、权威度、时间新鲜度和任务关联；返回值携带 `provenance`、`reason` 与检索轨迹，便于解释为什么某条记忆进入上下文。

## 4. 统一 Tool Runtime

所有工具定义均声明版本、风险级别、所需权限、幂等性、超时和输出模式。调用链路固定为：

```text
参数校验 -> 权限/风险策略 -> 审批判断 -> 幂等查重
        -> 限时执行 -> 秘密脱敏 -> 大输出制品化 -> 审计落库
```

调用状态包括 `pending`、`running`、`succeeded`、`failed`、`timed_out`、`denied`、`approval_required` 和 `deduplicated`。高于自动批准阈值的工具必须显式批准；缺少权限时直接拒绝。相同工具与幂等键的成功调用不会再次产生副作用。

## 5. 关键接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/control-plane/tasks` | 新建结构化任务状态 |
| `PATCH /api/control-plane/tasks/{id}` | 带版本保护更新任务 |
| `POST /api/control-plane/tasks/{id}/checkpoints` | 创建并校验 Checkpoint |
| `POST /api/control-plane/tasks/{id}/checkpoints/{checkpoint_id}/restore` | 校验哈希与版本后恢复/继续任务 |
| `POST /api/control-plane/artifacts` | 保存内容寻址制品 |
| `POST /api/control-plane/environment` | 捕获环境指纹 |
| `GET /api/control-plane/tool-invocations` | 查看工具审计记录 |
| `POST /api/memories/{id}/verify` | 验证或拒绝候选记忆 |
| `POST /api/agent-core/tools/{name}/invoke` | 经 Runtime 调用工具 |

## 6. 数据迁移与验证

数据库升级：

```bash
cd backend/api
uv run alembic upgrade head
```

完整后端测试：

```bash
cd backend/api
uv run python -m unittest discover -s tests
```

升级迁移位于 `backend/api/migrations/versions/202608010001_memory_tool_control_plane.py`。
