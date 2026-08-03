const { contextBridge } = require("electron");
const { ipcRenderer } = require("electron");

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
}));
