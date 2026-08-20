# AtlasAgent 客户端指南

两个客户端共用同一套 FastAPI 接口。Web 适合浏览器协作（并可作为 PWA 安装到桌面/移动端），TUI 适合 SSH、低带宽和键盘工作流。

## Textual TUI

TUI 位于 `frontend/tui/`，提供任务、Checkpoint、工具审计三栏信息和命令输入，支持三套终端主题及离线演示数据。

```bash
cd frontend/tui
uv sync
ATLAS_API_URL=http://localhost:8088 ATLAS_API_KEY=... uv run atlas-tui
```

常用键位：

| 键位 | 动作 |
| --- | --- |
| `n` | 新建会话，然后在输入框输入标题 |
| `/` | 聚焦输入框 |
| `t` | 循环切换主题 |
| `r` | 刷新控制平面数据 |
| `1` / `2` / `3` | 切换到任务、Checkpoint、审计区 |
| `Enter` | 发送任务 |
| `q` | 退出 |

后端不可达时，TUI 会自动回退到演示模式，因此可以先体验布局与键盘操作，再接入真实服务。

## API 地址

- 本地直接运行 API：`http://localhost:8000`
- 通过 Nginx 统一网关：`http://localhost:8088`

如需切换地址，TUI 使用 `ATLAS_API_URL` 与 `ATLAS_API_KEY`。Web 会用一次 API Key 换取 HttpOnly、SameSite=Strict 的 8 小时会话，不把原始密钥放进 localStorage/sessionStorage。
