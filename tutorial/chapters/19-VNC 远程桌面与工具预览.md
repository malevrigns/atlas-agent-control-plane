# 第十九章. VNC 远程桌面与工具预览

![](../assets/ch18-browser.jpg)


用户要看见 Agent 在浏览器里干什么。Xvfb 提供虚拟屏，x11vnc 读它，websockify 转成浏览器能接的 WebSocket。这三件是操作系统进程，不是 TypeScript。`sandbox-ts` 的启动脚本把它们拉起来，Hono 只回答「VNC 配了没有」。

```ts
api.get("/vnc/status", (c) =>
  c.json(
    ok({
      enabled: settings.vncEnabled,
      display: settings.vncDisplay,
      vnc_port: settings.vncPort,
      web_port: settings.vncWebPort,
      iframe_path: settings.vncIframePath,
      websocket_path: "sandbox-vnc/websockify",
      message: settings.vncEnabled
        ? "noVNC remote desktop is configured."
        : "VNC remote desktop is disabled.",
    }),
  ),
);
```

Nginx 把 `/sandbox-vnc/` 转到 6080，并带 `Upgrade`。前面要 `auth_request`，桌面不能裸奔。WebSocket 无法经 Next rewrite 转，所以开发期要么走网关 8088，要么设 `NEXT_PUBLIC_VNC_WS_BASE` 直连。不要指望 `pnpm dev` 单独把 VNC 也代理了。

前端 noVNC 组件吃的是 `websocket_path`。路径写错一条斜杠，画面就是黑的，日志还正常——先 curl `/sandbox-api/vnc/status` 对一下字段。

本机不想装 Xvfb 时，把 `VNC_ENABLED=false`，status 会说明禁用，工作台隐藏面板即可。

---

[← 第十八章. Playwright、CDP 与 BrowserTool](18-Playwright、CDP%20与%20BrowserTool.md) · [返回目录](../README.md) · [第二十章. SearchTool 搜索能力成形 →](20-SearchTool%20搜索能力成形.md)
