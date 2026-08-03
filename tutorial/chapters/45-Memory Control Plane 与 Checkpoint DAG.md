# 第四十五章. Memory Control Plane 与 Checkpoint DAG

## 45.1 本章目标

前面的记忆系统已经能存储和检索信息，但复杂 Agent 任务还有一个更难的问题：进程重启、上下文裁剪或长时间中断之后，系统如何知道“真正做到哪里”？

完成本章后，你将能够：

- 区分原始事件、Artifact、任务物化状态和长期记忆；
- 使用结构化 `TaskState` 代替一段不可验证的摘要；
- 使用 Checkpoint DAG 保存恢复点，并校验证据和不可丢失的约束；
- 设计 candidate、verified、superseded 的记忆生命周期；
- 用环境指纹和内容寻址 Artifact 还原执行现场。

## 45.2 四层事实模型

Control Plane 不是又建一张“万能记忆表”，而是明确四类数据的职责：

| 层 | 数据 | 特征 |
| --- | --- | --- |
| L0 | 会话事件、工具审计 | append-only，回放事实 |
| L1 | Artifact | 按 SHA-256 寻址，保存大输出、文件、补丁、测试报告 |
| L2 | `agent_tasks` | 可更新的任务工作状态，可从 L0/L1 重建 |
| L3 | `agent_memories` | 跨任务复用的类型化经验与事实 |

重要原则是：**摘要可以过时，事实源不能被摘要覆盖。**

## 45.3 结构化任务状态

新的 `TaskState` 在 `api/app/domain/control_plane/entities.py` 中定义。它包含：

```text
goal + acceptance_criteria
requirements + decisions
progress(done / doing / blocked)
known_failures + open_questions
next_actions + must_preserve
environment_ref + artifact_refs
current_event_seq + version + state_hash
```

`requirements` 和 `decisions` 中的每一项都应带 `evidence` 或 `source_event_id`。`must_preserve` 放置后续 Checkpoint 不得静默丢失的约束，例如“保持旧 API 兼容”。

更新时必须传 `expected_version`：

```http
PATCH /api/control-plane/tasks/{task_id}
Content-Type: application/json

{
  "expected_version": 3,
  "status": "running",
  "next_actions": [
    {"action": "run_tests", "evidence": "event:219"}
  ]
}
```

如果服务器当前版本已经是 4，这次更新就应失败，而不是覆盖别的 Worker 写入的状态。

## 45.4 Checkpoint DAG

Checkpoint 记录父节点、覆盖事件范围、快照、稳定哈希和验证报告。

```text
CP-001 (full)
  └─ CP-002 (incremental)
       └─ CP-003 (incremental)
            └─ CP-004 (incremental, current)
```

创建接口：

```http
POST /api/control-plane/tasks/{task_id}/checkpoints
Content-Type: application/json

{
  "kind": "incremental",
  "parent_checkpoint_id": "<previous-checkpoint-id>",
  "covered_event_start": 201,
  "covered_event_end": 219
}
```

`CheckpointValidator` 会检查：

1. 快照必需字段是否齐全；
2. 事件区间是否合法；
3. 需求和决策是否带证据；
4. 父节点的 `must_preserve` 是否被丢失；
5. 活动任务是否有下一步，是否绑定环境指纹。

快照使用字段排序后的稳定 JSON 生成 SHA-256。同一状态不因字段顺序不同而得到不同哈希。

## 45.5 Memory Write Gate

新建记忆默认为 `candidate`，需要有来源才能验证：

```http
POST /api/memories/{memory_id}/verify
Content-Type: application/json

{
  "provenance": ["event:219", "artifact:sha256:..."],
  "authority": "tool_verified",
  "verification": {"method": "test_suite", "passed": true}
}
```

记忆的关键控制字段如下：

- `scope` / `project_id` / `task_id` / `user_id`：限定作用域；
- `confidence` / `authority`：表达可信度和来源权威性；
- `valid_from` / `valid_to` / `ttl_seconds`：表达有效期；
- `provenance`：保存消息、事件、制品或外部来源引用；
- `supersedes`：将新记忆连到已过时的旧记忆；
- `sensitivity`：阻止秘密内容被普通检索注入。

检索结果不再只返回正文，还返回 `provenance` 和 `reason`。这使调试者能够回答：“为什么这条记忆被放进了模型上下文？”

## 45.6 环境指纹与 Artifact

恢复一个任务不能只看文本，还要知道它在什么环境中运行。`POST /api/control-plane/environment` 可记录应用版本、依赖锁定、工作区状态和安全的配置摘要，然后生成指纹。

Artifact 接口接收文件与元数据，按内容 SHA-256 存储。工具大输出也会自动转为 Artifact，上下文只保留脱敏预览和制品引用。

## 45.7 Checkpoint 恢复与继续

创建 Checkpoint 后，最终版本还提供带乐观锁的恢复接口：

```http
POST /api/control-plane/tasks/{task_id}/checkpoints/{checkpoint_id}/restore
Content-Type: application/json
X-Atlas-API-Key: <key>

{
  "expected_version": 3,
  "resume": false
}
```

服务端会重新计算快照哈希、检查 `validator_report.valid`、确认 Checkpoint 属于目标任务，再恢复任务物化状态。`resume=false` 适合先人工核对；`resume=true` 会把任务状态改为 `running`。恢复的是控制面状态与引用，不会假装撤销已经发生的外部副作用。

恢复接口只接受白名单内的任务物化字段，不会把快照中的未知数据直接写回数据库。客户端应先读取当前任务版本，把它作为 `expected_version` 提交；若任务已被其他操作者修改，服务返回冲突，要求重新核对，避免旧快照覆盖新状态。

## 45.8 本章验收

```bash
cd api
uv run alembic upgrade head
uv run python -m unittest tests.test_checkpoint_service tests.test_memory_control_plane
```

应验证：

- 同一快照多次哈希结果相同；
- 丢失 `must_preserve` 的子 Checkpoint 验证失败；
- 无 provenance 的候选记忆不能进入 verified；
- 过期、被替代或敏感记忆不会注入普通上下文。

## 45.9 本章小结

记忆不再是“一段模型说过的话”，而是带类型、证据、作用域、时效和替代关系的可治理数据。Checkpoint 也不是随手摘要，而是可校验、可定位事件范围、可验证恢复的状态节点。

---

[← 第四十四章. 项目简历落笔](44-项目简历落笔.md) · [返回目录](../README.md) · [第四十六章. Tool Runtime 权限、幂等与审计 →](46-Tool%20Runtime%20权限、幂等与审计.md)
