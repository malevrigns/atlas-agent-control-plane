# AtlasAgent 客户端指南

三个客户端共用同一套 FastAPI 接口。Web 适合浏览器协作，Electron 适合长期驻留与多面板观察，TUI 适合 SSH、低带宽和键盘工作流。

## Electron 桌面客户端

桌面端位于 `frontend/desktop/`，渲染层使用 React + TypeScript（TSX）。左侧图标导航在三个工作区之间切换：

| 工作区 | 内容 |
| --- | --- |
| **任务** | 任务与 Checkpoint 时间线、工具审计、暂停/恢复、命令输入 |
| **技能** | 技能注册中心：列表与搜索、草稿编辑、发布、启停、版本历史、注入命中调试 |
| **知识库** | RAG 知识库：建库、文档摄取与状态、重建索引、检索验证台 |

源码结构：`App.tsx` 只负责外壳与导航，三个视图在 `src/views/`，全部 API 调用收敛在 `src/api.ts`，
共享组件在 `src/components.tsx`。

内置主题：

- `Ink`：近黑底、冷蓝强调色，默认主题；
- `Dawn`：浅色背景，适合明亮环境；
- `Contrast`：高对比配色，强化边界与焦点。

主题选择保存在浏览器本地存储，三个工作区共用同一套 CSS 变量。

Electron 壳启用 `contextIsolation`、关闭 `nodeIntegration`、开启 `sandbox`，预加载脚本只暴露平台、版本和受限的 Atlas API 请求；API Key 留在主进程环境中。渲染进程发起的每个请求都经过 `electron/request-guard.cjs` 校验：必须是 `/api/` 前缀的绝对路径，禁止路径穿越、反斜杠、协议相对地址与控制字符，方法限于 GET/POST/PATCH/DELETE。该模块可被 `npm test` 直接覆盖。

开发与构建：

```bash
cd frontend/desktop
npm install
npm run electron:dev
npm run typecheck
npm run build
npm test          # 10 项：IPC 安全边界 + Sites 打包产物
```

`npm run build` 会先执行严格 TypeScript 检查，再生成 Vite 与 Sites 产物；任务、Checkpoint、API envelope 和 `window.atlasDesktop` IPC 契约都有显式类型。

核心交互：

- 选择任务和 Checkpoint；
- 展开/收起时间线节点；
- 切换工具授权策略；
- 输入命令或使用快捷建议；
- 暂停/恢复任务；
- 管理技能：创建草稿、发布、启停、派生新版本、预览注入命中；
- 管理知识库：摄取文档、查看摄取状态与失败原因、重建索引、验证检索效果；
- 切换三套主题。

技能与知识库两个视图在后端不可达时显示明确的离线提示，不会渲染演示数据——管理界面显示假数据会误导操作。

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

如需切换地址，Electron 使用 `ATLAS_API_BASE_URL`，TUI 使用 `ATLAS_API_URL`；二者都使用 `ATLAS_API_KEY`。Web 会用一次 API Key 换取 HttpOnly、SameSite=Strict 的 8 小时会话，不把原始密钥放进 localStorage/sessionStorage。
