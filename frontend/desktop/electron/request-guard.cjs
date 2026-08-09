"use strict";

/**
 * 渲染进程 → 主进程的 API 请求校验。
 *
 * 桌面端把 API Key 保存在主进程，渲染进程只能通过 IPC 通道发请求。
 * 这层校验是安全边界：渲染进程被 XSS 或恶意依赖污染时，攻击者也只能
 * 访问 /api/ 下的既定方法，不能用相对路径逃逸到别的 origin 或本地文件。
 *
 * 抽成独立模块是为了能被 node:test 直接覆盖——安全逻辑不应该只存在于
 * 一个无法测试的 Electron 主进程闭包里。
 */

const ALLOWED_METHODS = new Set(["GET", "POST", "PATCH", "DELETE"]);

/**
 * 校验并归一化一次 API 请求。
 *
 * @param {unknown} request 渲染进程传来的原始请求对象。
 * @returns {{path: string, method: string, body: unknown}} 归一化后的请求。
 * @throws {Error} 路径或方法不合法时抛出。
 */
function normalizeApiRequest(request) {
  const requestPath = String((request && request.path) || "");
  const method = String((request && request.method) || "GET").toUpperCase();

  // 1. 必须是 /api/ 前缀的绝对路径，禁止协议相对地址（//evil.test）。
  if (!requestPath.startsWith("/api/") || requestPath.startsWith("//")) {
    throw new Error("invalid Atlas API path");
  }
  // 2. 禁止路径穿越与反斜杠绕过。
  if (requestPath.includes("..") || requestPath.includes("\\")) {
    throw new Error("invalid Atlas API path");
  }
  // 3. 禁止控制字符（CR/LF 注入）。
  if (/[\u0000-\u001f\u007f]/.test(requestPath)) {
    throw new Error("invalid Atlas API path");
  }
  // 4. 方法白名单。
  if (!ALLOWED_METHODS.has(method)) {
    throw new Error("unsupported Atlas API method");
  }

  return {
    path: requestPath,
    method,
    body: request ? request.body : undefined,
  };
}

module.exports = { ALLOWED_METHODS, normalizeApiRequest };
