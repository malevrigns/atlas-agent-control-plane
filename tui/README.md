# AtlasAgent TUI

键盘优先的控制平面客户端。它读取与 Web/Electron 相同的 API，集中展示任务状态、Checkpoint 时间线和 Tool Runtime 审计；API 不可用时自动进入带标签的演示数据模式。

```bash
cd tui
uv sync
uv run atlas-tui
```

如 API 不在默认地址：

```bash
ATLAS_API_URL=http://127.0.0.1:8088 uv run atlas-tui
```

快捷键：`/` 聚焦输入，`r` 刷新，`t` 在深色/浅色/Nord 三主题之间切换，`1/2/3` 切换任务、检查点和审计区，`q` 退出。
