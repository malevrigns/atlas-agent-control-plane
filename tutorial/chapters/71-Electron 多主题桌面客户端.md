# 第七十一章. Electron 多主题桌面客户端

## 71.1 本章目标

Web 工作台依然保留，但长时间运行的 Agent 还需要一个适合驻留、多面板观察和系统级快捷操作的桌面客户端。本章使用 Electron + React + Vite 实现独立客户端。

设计目标是“在同一视野中判断任务、Checkpoint、记忆证据和工具风险”，而不是把 Web 页面套一层窗口。

## 71.2 信息架构

客户端使用选定的 Checkpoint 时间线方向：

| 区域 | 职责 |
| --- | --- |
| 图标轨道 | 任务、记忆、工具、设置入口与 API 状态 |
| 任务侧栏 | 项目目标、当前状态、Checkpoint 列表 |
| 主时间线 | CP 父子顺序、事件范围、验证状态、展开详情 |
| 命令区 | 任务输入、快捷建议、工具授权策略 |

主流程中的交互已实现：选任务、展开 Checkpoint、切换授权策略、输入命令、暂停/继续、切换主题。

## 71.3 三套主题

样式使用 CSS 变量，由 `document.documentElement.dataset.theme` 选择：

- `Ink`：近黑底与冷蓝强调，适合长时间运行监看；
- `Dawn`：浅色表面，适合亮光办公环境；
- `Contrast`：更高前景/背景对比，强化边界和焦点。

主题值保存到 `localStorage`，重开客户端后保留用户选择。组件只使用语义 token，不在单个卡片中写死颜色。

## 71.4 Electron 安全边界

`desktop/electron/main.cjs` 开启：

```javascript
webPreferences: {
  preload,
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
}
```

`preload.cjs` 只暴露平台和版本信息。渲染器不能直接访问 Node.js、文件系统或子进程。外部 URL 交给系统浏览器，不在 Electron 窗口中随意导航。

如果后续增加本地文件选择等能力，应在 preload 中为每个动作定义最小 IPC 契约，而不是把整个 `ipcRenderer` 暴露给 React。

## 71.5 开发与构建

```bash
cd desktop
npm install
npm run electron:dev
```

如 API 地址不是默认网关：

```bash
VITE_ATLAS_API_BASE=http://localhost:8000 npm run electron:dev
```

构建渲染器和执行打包前测试：

```bash
npm run build
npm run test:sites
```

生成当前平台发行物：

```bash
npm run desktop:dist
```

Electron Builder 已配置 Linux AppImage、macOS DMG/ZIP 和 Windows NSIS，正式发布应在目标平台上构建并配置签名。

## 71.6 可访问性与响应式

- 图标按钮使用 Phosphor Icons，带可读标签；
- 输入、选择器和可展开 Checkpoint 可通过键盘聚焦；
- 三套主题均定义焦点环和状态色；
- 视口变窄时，面板改为纵向布局，不依赖固定 1440 宽度。

## 71.7 验收

必须分别验证以下状态：

1. 无 API 时显示演示数据与离线标识；
2. API 恢复后状态点更新；
3. Checkpoint 展开不破坏时间线对齐；
4. Ink、Dawn、Contrast 主题均无文字低对比或焦点丢失；
5. Electron 重启后主题保留；
6. DevTools 无 React 运行错误。

## 71.8 本章小结

桌面客户端的价值不是“多一个入口”，而是把 Control Plane 中最重要的任务状态、恢复点和工具风险组织成一个适合长时间操作的桌面工具。
