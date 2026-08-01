# AtlasAgent 客户端指南

三个客户端共用同一套 FastAPI 接口。Web 适合浏览器协作，Electron 适合长期驻留与多面板观察，TUI 适合 SSH、低带宽和键盘工作流。

## Electron 桌面客户端

桌面端位于 `desktop/`，界面采用选定的 Checkpoint 时间线方向：左侧图标导航，中间任务/Checkpoint 列表，主区域展示可展开的时间线与工具审计，底部固定命令输入。

内置主题：

- `Ink`：近黑底、冷蓝强调色，默认主题；
- `Dawn`：浅色背景，适合明亮环境；
- `Contrast`：高对比配色，强化边界与焦点。

主题选择保存在浏览器本地存储。Electron 壳启用 `contextIsolation`、关闭 `nodeIntegration`，预加载脚本只暴露平台和版本信息。

开发与构建：

```bash
cd desktop
npm install
npm run electron:dev
npm run build
```

核心交互：

- 选择任务和 Checkpoint；
- 展开/收起时间线节点；
- 切换工具授权策略；
- 输入命令或使用快捷建议；
- 暂停/恢复任务；
- 切换三套主题。

## Textual TUI

TUI 位于 `tui/`，提供任务、Checkpoint、工具审计三栏信息和命令输入，支持三套终端主题及离线演示数据。

```bash
cd tui
uv sync
ATLAS_API_URL=http://localhost:8000 uv run atlas-tui
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

如需切换地址，Electron 在构建或开发时设置 `VITE_ATLAS_API_BASE`；TUI 使用 `ATLAS_API_URL` 环境变量。
