# 第十七章. Sandbox Shell 与 Docker 隔离

文件工具还不够。Agent 要跑测试、看 git status、装依赖。命令必须在沙箱里，cwd 必须落在工作区里。`ShellService` 不调 `shell: true` 的无参 spawn：Linux 用 `sh -c`，Windows 用 `cmd.exe /c`。参数仍是一整句，危险和 Python 时代的 `create_subprocess_shell` 同类，所以更要把 cwd 钉死。

会话存在内存 Map 里。id 是 uuid。stdout/stderr 拼进 `output`，超 `SHELL_OUTPUT_LIMIT` 截断并打标。`wait` 有超时，到期不杀进程，只把当前快照返回——调用方再决定 terminate。这和「等到死」不同，避免一次 `sleep 3600` 卡住整个控制平面。

![工具摊在台上，动手的地方有边界](../assets/ch12-tools.jpg)

```ts
execute(command: string, cwd: string, workspace: string, fullAccess: boolean) {
  const workdir = this.files.resolvePath(cwd || ".", workspace, fullAccess);
  const isWin = process.platform === "win32";
  const child = spawn(isWin ? "cmd.exe" : "sh", isWin ? ["/c", command] : ["-c", command], {
    cwd: workdir,
    env: process.env,
    windowsHide: true,
  });
  // 收集输出、登记 session
}
```

Compose 里 sandbox 镜像基于 `node:22-bookworm-slim`，另装 xvfb、x11vnc、websockify。API 容器不装这些。两边的卷分开：`api_uploads` 不是 `/workspace`。Agent 要碰用户上传的文件，应通过控制平面把文件同步进工作区，而不是让沙箱去读 API 的盘。

健康检查用 node fetch 打 `/api/status`。启动脚本先起 Xvfb 再 `pnpm start`。本机开发可以不启 VNC，只跑 Hono。

```bash
curl -X POST http://127.0.0.1:8100/api/shell/sessions \
  -H "Content-Type: application/json" \
  -d "{\"command\":\"echo atlas\"}"
```

把返回的 id 拿去 `/wait`，output 里应有 atlas。

---

[← 第十六章. Sandbox 服务与文件工具](16-Sandbox%20服务与文件工具.md) · [返回目录](../README.md) · [第十八章. Playwright、CDP 与 BrowserTool →](18-Playwright、CDP%20与%20BrowserTool.md)
