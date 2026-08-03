import { requestApi } from "./api";
import type { SandboxInstanceData, VncStatusData } from "../types";


// ===================== 第1步：读取当前任务沙箱状态 =====================
export function fetchCurrentSandbox(): Promise<SandboxInstanceData> {
  return requestApi<SandboxInstanceData>("/api/sandboxes/current");
}


// ===================== 第2步：等待沙箱通过健康检查 =====================
export function waitCurrentSandbox(): Promise<SandboxInstanceData> {
  return requestApi<SandboxInstanceData>("/api/sandboxes/current/wait", {
    method: "POST",
    body: JSON.stringify({
      retries: 3,
      interval_seconds: 1,
    }),
  });
}


// ===================== 第3步：读取 noVNC 远程桌面状态 =====================
export function fetchVncStatus(): Promise<VncStatusData> {
  return requestApi<VncStatusData>("/sandbox-api/vnc/status");
}
