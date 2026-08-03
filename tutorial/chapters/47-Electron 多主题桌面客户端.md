# 第四十七章. Electron 多主题桌面客户端

## 47.1 本章目标

Web 工作台依然保留，但长时间运行的 Agent 还需要一个适合驻留、多面板观察和系统级快捷操作的桌面客户端。本章使用 Electron + React + TypeScript + Vite 实现独立客户端。

设计目标是“在同一视野中判断任务、Checkpoint、记忆证据和工具风险”，而不是把 Web 页面套一层窗口。

## 47.2 信息架构

客户端使用选定的 Checkpoint 时间线方向：

| 区域 | 职责 |
| --- | --- |
| 图标轨道 | 任务、记忆、工具、设置入口与 API 状态 |
| 任务侧栏 | 项目目标、当前状态、Checkpoint 列表 |
| 主时间线 | CP 父子顺序、事件范围、验证状态、展开详情 |
| 命令区 | 任务输入、快捷建议、工具授权策略 |

主流程中的交互已实现：选任务、展开 Checkpoint、切换授权策略、输入命令、暂停/继续、切换主题。

## 47.3 三套主题

样式使用 CSS 变量，由 `document.documentElement.dataset.theme` 选择：

- `Ink`：近黑底与冷蓝强调，适合长时间运行监看；
- `Dawn`：浅色表面，适合亮光办公环境；
- `Contrast`：更高前景/背景对比，强化边界和焦点。

主题值保存到 `localStorage`，重开客户端后保留用户选择。组件只使用语义 token，不在单个卡片中写死颜色。

## 47.4 Electron 安全边界

`desktop/electron/main.cjs` 开启：

```javascript
webPreferences: {
  preload,
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
}
```

`preload.cjs` 只暴露平台、版本信息和受限的 `request(path, options)` 契约。渲染器不能直接访问 Node.js、文件系统、子进程或任意网络地址；主进程只允许 `/api/` 路径与 GET/POST/PATCH/DELETE，并从进程环境读取 API 地址和密钥。外部 URL 交给系统浏览器，不在 Electron 窗口中随意导航。

渲染层在 `src/vite-env.d.ts` 中声明同一份 `window.atlasDesktop` 契约，`request<T>()` 的请求选项只允许受支持的方法，响应由调用处指定业务类型。这样 preload 运行时白名单与 TSX 编译期约束相互对应，但 TypeScript 不能代替主进程的运行时校验。

如果后续增加本地文件选择等能力，应在 preload 中为每个动作定义最小 IPC 契约，而不是把整个 `ipcRenderer` 暴露给 React。

## 47.5 连接真实 Control Plane

桌面端不再用本地按钮状态伪装控制成功。渲染器通过 preload 的 `request()` 调用主进程，主进程再访问同源 Control Plane：

- `GET /api/control-plane/tasks` 获取任务；
- `GET /api/control-plane/tasks/{task_id}/checkpoints` 获取恢复点；
- `PATCH /api/control-plane/tasks/{task_id}` 执行暂停、继续和下一步动作更新；
- `POST /api/control-plane/tasks/{task_id}/checkpoints/{checkpoint_id}/restore` 执行恢复。

主进程只接受 `/api/` 路径、禁止 `..`，并限制 GET/POST/PATCH/DELETE。API 地址和密钥来自 `ATLAS_API_BASE_URL`、`ATLAS_API_KEY`，不会由不可信渲染内容指定。在线请求失败时，客户端明确显示离线状态并使用演示数据；演示模式不会显示“已成功写入服务端”之类误导反馈。

暂停、继续和恢复操作完成后必须重新读取服务端状态，不能仅修改 React 本地 state。Checkpoint 恢复还要携带当前 `expected_version`，冲突时提示用户刷新核对。

## 47.6 开发与构建

渲染入口为 `src/main.tsx`，主界面为 `src/App.tsx`，API、任务与 Checkpoint 模型集中在 `src/types.ts`。`tsconfig.json` 开启 `strict`、未使用符号检查和 Bundler 模块解析；不要仅把 `.jsx` 改名为 `.tsx` 后用 `any` 绕过错误。

```bash
cd desktop
npm install
npm run electron:dev
```

如 API 地址不是默认网关：

```bash
ATLAS_API_BASE_URL=http://localhost:8088 ATLAS_API_KEY=... npm run electron:dev
```

构建渲染器和执行打包前测试：

```bash
npm run typecheck
npm run build
npm run test:sites
```

`npm run build` 本身也会先运行 `tsc --noEmit`，因此本地打包和 CI 不会绕过类型门禁。新增后端字段时，应先更新 `src/types.ts`，再调整映射与组件 props；新增 IPC 能力时，还要同步 preload 实现和 `vite-env.d.ts` 声明。

生成当前平台发行物：

```bash
npm run desktop:dist
```

Electron Builder 已配置 Linux AppImage、macOS DMG/ZIP 和 Windows NSIS，正式发布应在目标平台上构建并配置签名。

## 47.7 可访问性与响应式

- 图标按钮使用 Phosphor Icons，带可读标签；
- 输入、选择器和可展开 Checkpoint 可通过键盘聚焦；
- 三套主题均定义焦点环和状态色；
- 视口变窄时，面板改为纵向布局，不依赖固定 1440 宽度。

## 47.8 验收

必须分别验证以下状态：

1. 无 API 时显示演示数据与离线标识；
2. API 恢复后状态点更新；
3. Checkpoint 展开不破坏时间线对齐；
4. Ink、Dawn、Contrast 主题均无文字低对比或焦点丢失；
5. Electron 重启后主题保留；
6. DevTools 无 React 运行错误。
7. `npm run typecheck` 在严格模式下通过，仓库中不存在遗留 `.jsx` 源文件。

最终版本还应验证：在线时任务、Checkpoint、暂停/继续、恢复和下一步动作都来自真实 API；只有 API 不可达时才显示带离线标识的演示数据。

## 47.9 本章小结

桌面客户端的价值不是“多一个入口”，而是把 Control Plane 中最重要的任务状态、恢复点和工具风险组织成一个适合长时间操作的桌面工具。

---

[← 第四十六章. Tool Runtime 权限、幂等与审计](46-Tool%20Runtime%20权限、幂等与审计.md) · [返回目录](../README.md) · [第四十八章. 键盘优先 TUI 客户端 →](48-键盘优先%20TUI%20客户端.md)
