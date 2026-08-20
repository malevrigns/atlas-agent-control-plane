# 第四十六章. Tool Runtime 权限、幂等与审计

## 46.1 本章目标

第 12 章的工具协议解决了“模型如何看到工具和参数”。这还不足以支撑生产级执行，因为它没有回答：谁允许调用、风险有多高、重试会不会重复产生副作用、大输出放在哪里、出错后如何审计。

本章将工具执行收敛到一个统一 Runtime。

## 46.2 工具定义是执行合同

`ToolDefinition` 新增：

```python
version: str
risk_level: ToolRiskLevel
required_permissions: tuple[str, ...]
idempotent: bool
timeout_seconds: float
output_mode: str
```

参数校验也不再只检查“必填值是否存在”，而是：

- 拒绝未声明参数；
- 对 integer、number、boolean 和 string 做显式转换；
- 转换失败时返回稳定的 400 错误。

工具 handler 只负责业务逻辑；权限、审批、超时、幂等和审计都由 Runtime 处理。

## 46.3 风险与权限

风险分为 `low`、`medium`、`high`、`critical`。权限是功能级声明，例如 `sandbox.shell.execute`、`sandbox.files.write`、`network.search`。

`ToolPolicyEngine` 依次检查：

1. 调用上下文是否包含所需权限；
2. 风险级别是否高于自动批准阈值；
3. 需审批时是否有 `approved=true` 与审批理由。

决策结果为 `allow`、`deny` 或 `require_approval`。未通过策略时 handler 不会被执行。

## 46.4 幂等调用

调用方可传入 `idempotency_key`：

```json
{
  "arguments": {"task": "发布应用"},
  "project_id": "atlas",
  "allowed_permissions": [],
  "idempotency_key": "release-2026-08-01"
}
```

Runtime 用“工具名 + 幂等键”查询内存与持久化审计记录。已成功的同键调用返回 `deduplicated`，不会重新执行 handler。

请求同时生成 `request_hash`，内容包括工具名、版本和规范化参数，用于审计这个键对应的真实请求。

## 46.5 超时、脱敏与大输出

handler 在独立线程中运行，由 `asyncio.wait_for` 限时。结果状态包括：

```text
pending / running / succeeded / failed / timed_out
denied / approval_required / deduplicated
```

输出在返回前扫描 API Key、Token、Password、Bearer 凭据等模式，匹配部分替换为 `[REDACTED]`。

当原始输出超过 `TOOL_OUTPUT_INLINE_LIMIT`，Runtime 会将完整内容存成 `tool_output` Artifact，返回值只包含脱敏预览和 `artifact_id`。这避免把整段日志塞进事件流或模型上下文。

## 46.6 调用示例

```http
POST /api/agent-core/tools/{tool_name}/invoke
Content-Type: application/json

{
  "arguments": {"command": "pytest -q"},
  "project_id": "atlas",
  "task_id": "<task-id>",
  "actor": "user",
  "allowed_permissions": ["sandbox.shell.execute"],
  "approved": true,
  "approval_reason": "用户要求运行测试",
  "idempotency_key": "test-run-004"
}
```

返回结果携带 `invocation_id`、`status`、`risk_level`、`duration_ms`、`artifact_id` 和 `audit`。调试者可通过以下接口查看同一记录：

```http
GET /api/control-plane/tool-invocations?project_id=atlas&task_id=<task-id>
```

## 46.7 如何接入新工具

1. 用 `@agent_tool` 声明名称、说明和参数；
2. 设置版本、风险级别、权限、幂等性和超时；
3. 使用 `ToolRegistry` 注册；
4. 调用方只通过 `ToolRuntime.execute()` 执行；
5. 为 allow、deny、approval、timeout、idempotency 和 artifactization 分别写测试。

不应在 ReAct 或 HTTP Route 里直接调用 `tool.handler`，否则会绕过所有控制面。

## 46.8 本章验收

```bash
cd backend/api
uv run python -m unittest tests.test_tool_runtime tests.test_tool_selection_service
```

重点检查：

- 缺少权限时是 `denied`；
- 高风险未批准时是 `approval_required`；
- 重复幂等键不会二次执行；
- 超时和 handler 异常都转为可观察结果；
- 秘密被脱敏，大输出返回 Artifact 引用。

## 46.9 本章小结

统一协议解决“怎么调”，统一 Runtime 才解决“能不能调、会不会重复调、出错后能不能说清”。将安全和可观测性放在 handler 之外，新工具才不会每次重复实现一套不一致的边界。

---

[← 第四十五章. Memory Control Plane 与 Checkpoint DAG](45-Memory%20Control%20Plane%20与%20Checkpoint%20DAG.md) · [返回目录](../README.md) · [第四十八章. 键盘优先 TUI 客户端 →](48-键盘优先%20TUI%20客户端.md)
