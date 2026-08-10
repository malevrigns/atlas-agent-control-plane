const { contextBridge } = require("electron");
const { ipcRenderer } = require("electron");

let nextStreamId = 0;

contextBridge.exposeInMainWorld("atlasDesktop", Object.freeze({
  platform: process.platform,
  versions: Object.freeze({
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  }),
  request: (path, options = {}) => ipcRenderer.invoke("atlas:api-request", {
    path,
    method: options.method || "GET",
    body: options.body,
  }),
  /**
   * 发起一次 SSE 流式请求（POST）。
   *
   * handlers.onChunk 收到原始文本块（可能包含多条或半条 SSE 记录，
   * 由渲染进程的解析器负责按 \n\n 组包）；onEnd/onError 收尾。
   * 返回 cancel 函数，可中断底层请求。
   */
  stream: (path, body, handlers = {}) => {
    nextStreamId += 1;
    const streamId = `s${Date.now()}-${nextStreamId}`;
    const chunkChannel = `atlas:api-stream-chunk:${streamId}`;
    const endChannel = `atlas:api-stream-end:${streamId}`;
    const errorChannel = `atlas:api-stream-error:${streamId}`;

    const onChunk = (_event, text) => {
      if (typeof handlers.onChunk === "function") handlers.onChunk(text);
    };
    const cleanup = () => {
      ipcRenderer.removeListener(chunkChannel, onChunk);
      ipcRenderer.removeAllListeners(endChannel);
      ipcRenderer.removeAllListeners(errorChannel);
    };
    ipcRenderer.on(chunkChannel, onChunk);
    ipcRenderer.once(endChannel, () => {
      cleanup();
      if (typeof handlers.onEnd === "function") handlers.onEnd();
    });
    ipcRenderer.once(errorChannel, (_event, message) => {
      cleanup();
      if (typeof handlers.onError === "function") handlers.onError(String(message));
    });
    ipcRenderer.send("atlas:api-stream", { id: streamId, path, body });

    return () => {
      ipcRenderer.send("atlas:api-stream-cancel", streamId);
    };
  },
}));
