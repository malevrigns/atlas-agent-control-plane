# 第十八章. Playwright、CDP 与 BrowserTool

沙箱要会开网页。Playwright 是 Node 的本家，比在 Python 里包一层自然。现行 `sandbox-ts` 只提供 `/api/browser/status`，还没有真正拉起 Chromium。镜像里也可以后装浏览器，但会显著变胖。这一章先把调用形状定住。

浏览器属于沙箱，不属于 API 进程。控制平面只发「打开这个 URL、截图、取正文」。CDP 端口留给调试和 VNC 观察，不要暴露到宿主机 0.0.0.0。Compose 里 `BROWSER_HEADLESS` 在有 VNC 时应为 false，让窗口画在 Xvfb 的 `:99` 上，x11vnc 才能看到。

![镜头对着房间，房间是沙箱](../assets/ch18-browser.jpg)

工具层以后会有 `browser_navigate`、`browser_snapshot`、`browser_click`。超时用沙箱配置的 `BROWSER_DEFAULT_TIMEOUT_MS`，不要让模型把 timeout 开到五分钟。截图落成制品，路径进 tool 事件的 payload，前端才能给下载链。

在 Playwright 接通之前，status 接口应诚实说 idle 或 disabled，不要假装有一个正在跑的 page。工作台的 VNC 面板可以先连上桌面，哪怕桌面是空的。

---

[← 第十七章. Sandbox Shell 与 Docker 隔离](17-Sandbox%20Shell%20与%20Docker%20隔离.md) · [返回目录](../README.md) · [第十九章. VNC 远程桌面与工具预览 →](19-VNC%20远程桌面与工具预览.md)
