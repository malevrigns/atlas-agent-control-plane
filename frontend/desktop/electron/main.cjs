const { app, BrowserWindow, ipcMain, net, shell } = require("electron");
const path = require("node:path");
const { normalizeApiRequest, normalizeStreamRequest } = require("./request-guard.cjs");

const API_BASE = process.env.ATLAS_API_BASE_URL || "http://127.0.0.1:8088";
const API_KEY = process.env.ATLAS_API_KEY || "";

ipcMain.handle("atlas:api-request", async (_event, request) => {
  const { path: requestPath, method, body } = normalizeApiRequest(request);
  const headers = { Accept: "application/json" };
  if (API_KEY) headers["X-Atlas-API-Key"] = API_KEY;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await net.fetch(new URL(requestPath, API_BASE).toString(), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok || Number(payload?.code || response.status) >= 400) {
    throw new Error(payload?.message || `Atlas API returned ${response.status}`);
  }
  return payload?.data;
});

// SSE 流式请求：渲染进程发起后，主进程逐块把文本推回去。
// API Key 仍然只存在于主进程；每个流有独立 id，支持窗口关闭清理与主动取消。
const activeStreams = new Map();

ipcMain.on("atlas:api-stream", async (event, request) => {
  const streamId = String(request && request.id ? request.id : "");
  const reply = (channel, payload) => {
    if (!event.sender.isDestroyed()) event.sender.send(channel, payload);
  };
  if (!streamId) return;
  try {
    const { path: requestPath, body } = normalizeStreamRequest(request);
    const controller = new AbortController();
    activeStreams.set(streamId, controller);
    const headers = { Accept: "text/event-stream", "Content-Type": "application/json" };
    if (API_KEY) headers["X-Atlas-API-Key"] = API_KEY;
    const response = await net.fetch(new URL(requestPath, API_BASE).toString(), {
      method: "POST",
      headers,
      body: JSON.stringify(body ?? {}),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      let message = `Atlas API returned ${response.status}`;
      try {
        const errorPayload = await response.json();
        if (errorPayload && errorPayload.message) message = errorPayload.message;
      } catch {
        // 非 JSON 错误体时保留默认信息。
      }
      throw new Error(message);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      reply(`atlas:api-stream-chunk:${streamId}`, decoder.decode(value, { stream: true }));
    }
    reply(`atlas:api-stream-end:${streamId}`, null);
  } catch (error) {
    const aborted = error && error.name === "AbortError";
    if (aborted) reply(`atlas:api-stream-end:${streamId}`, null);
    else reply(`atlas:api-stream-error:${streamId}`, error instanceof Error ? error.message : String(error));
  } finally {
    activeStreams.delete(streamId);
  }
});

ipcMain.on("atlas:api-stream-cancel", (_event, streamId) => {
  const controller = activeStreams.get(String(streamId));
  if (controller) controller.abort();
});

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 1024,
    minWidth: 1040,
    minHeight: 720,
    backgroundColor: "#050506",
    title: "AtlasAgent",
    icon: path.join(__dirname, "..", "assets", "icon.ico"),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    const current = win.webContents.getURL();
    if (current && new URL(url).origin !== new URL(current).origin) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  const devUrl = process.env.ATLAS_DESKTOP_DEV_URL;
  if (devUrl) win.loadURL(devUrl);
  else win.loadFile(path.join(__dirname, "..", "dist", "client", "index.html"));
  win.once("ready-to-show", () => win.show());
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
