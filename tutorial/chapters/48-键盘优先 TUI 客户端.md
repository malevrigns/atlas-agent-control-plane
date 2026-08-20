# 第四十八章. 键盘优先 TUI 客户端

## 48.1 本章目标

在 SSH、低带宽、远程服务器和键盘工作流中，Web 都不是最短路径。本章使用 Textual 提供一个独立 Python TUI，它与其他客户端复用同一套 API，不把业务逻辑复制到终端。

## 48.2 面板布局

TUI 使用三栏布局：

```text
任务列表 | 任务摘要 + Checkpoint 时间线 + 命令输入 | 工具审计
```

中间区展示状态、版本、进度计数和 `state_hash`。Checkpoint 显示验证标记、事件范围和创建时间。审计区显示工具名、状态、风险、策略决策和耗时。

## 48.3 API 客户端

`atlas_agent_tui/api.py` 封装：

- API 状态检查；
- 会话列表和会话创建；
- Control Plane 任务、Checkpoint 和工具审计查询；
- 会话消息 SSE 流式消费。

当 API 不可达，应用会加载明确标记的演示数据，而不是伪装已连接。按 `r` 可重新检测 API，恢复后会切回真实数据。

## 48.4 键盘绑定

| 键 | 动作 |
| --- | --- |
| `/` | 聚焦命令输入 |
| `r` | 刷新数据/重连 API |
| `n` | 进入新会话标题输入模式 |
| `t` | 循环切换 dark、light、Nord 主题 |
| `1` | 聚焦任务列表 |
| `2` | 聚焦 Checkpoint 区 |
| `3` | 聚焦工具审计区 |
| `q` | 退出 |

使用组合键前，先确认不会与终端、tmux 或 shell 快捷键冲突。本项目因此优先使用单键绑定。

## 48.5 运行

```bash
cd frontend/tui
uv sync
uv run atlas-tui
```

默认 API 地址为 `http://localhost:8088`。如果直接连接 FastAPI：

```bash
ATLAS_API_URL=http://localhost:8000 uv run atlas-tui
```

可执行文件入口由 `pyproject.toml` 声明，所以 TUI 可作为独立 Python 包安装，不依赖项目 API 的源码路径。

## 48.6 发送任务与 SSE

在输入框中回车后，TUI 向当前会话的流式消息接口发送指令。当收到 `tool_called`、`step_completed`、`task_done` 或 `task_error` 事件时，过程信息写入审计区。事件流结束后再刷新结构化任务和审计记录。

如果没有会话，按 `n`，输入标题并回车创建；不要用演示任务代替真实会话创建。

## 48.7 无头测试

Textual 的 `run_test()` 可在无真实终端的环境中驱动应用：

```bash
cd frontend/tui
uv run python -m unittest discover -s tests
```

当前测试覆盖 API 客户端行为、SSE 事件解析和应用挂载。后续增加快捷键时，应在无头测试中使用 `pilot.press()` 验证焦点和状态变化。

## 48.8 本章小结

TUI 不是 Web 客户端的缩水版。它选择最需要在终端观察的任务状态、Checkpoint 和工具审计，并用稳定的键盘路径完成新会话、发任务和切换上下文。

---

[← 第四十六章. Tool Runtime 权限、幂等与审计](46-Tool%20Runtime%20权限、幂等与审计.md) · [返回目录](../README.md) · [第四十九章. 迁移、测试与交付验收 →](49-迁移、测试与交付验收.md)
