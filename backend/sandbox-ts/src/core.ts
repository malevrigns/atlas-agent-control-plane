import { createHash, timingSafeEqual } from "node:crypto";
import { resolve } from "node:path";

import type { MiddlewareHandler } from "hono";

export type SandboxSettings = {
  appName: string;
  env: string;
  version: string;
  prefix: string;
  authEnabled: boolean;
  atlasApiKey: string;
  host: string;
  port: number;
  workspaceDir: string;
  maxFileReadBytes: number;
  maxFileWriteBytes: number;
  maxUploadSize: number;
  shellOutputLimit: number;
  shellDefaultTimeoutSeconds: number;
  vncEnabled: boolean;
  vncDisplay: string;
  vncPort: number;
  vncWebPort: number;
  vncIframePath: string;
  browserEnabled: boolean;
};

function boolEnv(name: string, fallback: boolean): boolean {
  const raw = process.env[name];
  if (raw === undefined) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(raw.toLowerCase());
}

function numEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) {
    return fallback;
  }
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

export function loadSandboxSettings(): SandboxSettings {
  const authEnabled = boolEnv("SANDBOX_AUTH_ENABLED", false);
  const atlasApiKey = process.env.ATLAS_API_KEY ?? "";
  if (authEnabled && (!atlasApiKey || atlasApiKey === "change-me")) {
    throw new Error("ATLAS_API_KEY is required when SANDBOX_AUTH_ENABLED=true");
  }
  return {
    appName: process.env.SANDBOX_APP_NAME ?? "AtlasAgent Sandbox",
    env: process.env.SANDBOX_ENV ?? "development",
    version: process.env.SANDBOX_VERSION ?? "0.1.0",
    prefix: process.env.SANDBOX_API_PREFIX ?? "/api",
    authEnabled,
    atlasApiKey,
    host: process.env.HOST ?? "127.0.0.1",
    port: numEnv("PORT", 8100),
    workspaceDir: resolve(process.env.WORKSPACE_DIR ?? process.env.SANDBOX_WORKSPACE_DIR ?? "workspace"),
    maxFileReadBytes: numEnv("MAX_FILE_READ_BYTES", 64 * 1024),
    maxFileWriteBytes: numEnv("MAX_FILE_WRITE_BYTES", 512 * 1024),
    maxUploadSize: numEnv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024),
    shellOutputLimit: numEnv("SHELL_OUTPUT_LIMIT", 64 * 1024),
    shellDefaultTimeoutSeconds: numEnv("SHELL_DEFAULT_TIMEOUT_SECONDS", 10),
    vncEnabled: boolEnv("VNC_ENABLED", true),
    vncDisplay: process.env.VNC_DISPLAY ?? ":99",
    vncPort: numEnv("VNC_PORT", 5900),
    vncWebPort: numEnv("VNC_WEB_PORT", 6080),
    vncIframePath: process.env.VNC_IFRAME_PATH ?? "",
    browserEnabled: boolEnv("BROWSER_ENABLED", true),
  };
}

export class SandboxError extends Error {
  constructor(
    message: string,
    readonly statusCode = 400,
    readonly code = statusCode,
  ) {
    super(message);
    this.name = "SandboxError";
  }
}

export function ok<T>(data: T) {
  return { code: 200, message: "success", data, error: null };
}

function safeEqual(left: string, right: string): boolean {
  if (!left || !right) {
    return false;
  }
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  if (a.length !== b.length) {
    return false;
  }
  return timingSafeEqual(a, b);
}

function sessionToken(apiKey: string): string {
  return createHash("sha256").update(`atlas-session:${apiKey}`, "utf8").digest("hex");
}

export function sandboxAuth(settings: SandboxSettings): MiddlewareHandler {
  return async (c, next) => {
    if (!settings.authEnabled || c.req.method === "OPTIONS") {
      return next();
    }
    const path = new URL(c.req.url).pathname.replace(/\/+$/, "") || "/";
    if (path === "/api/status") {
      return next();
    }
    const key = c.req.header("x-atlas-api-key") ?? "";
    const cookie = c.req.header("cookie")?.match(/(?:^|;\s*)atlas_session=([^;]+)/)?.[1] ?? "";
    if (safeEqual(key, settings.atlasApiKey) || safeEqual(cookie, sessionToken(settings.atlasApiKey))) {
      return next();
    }
    c.header("WWW-Authenticate", "AtlasApiKey");
    return c.json({ code: 401, message: "authentication required", data: null }, 401);
  };
}
