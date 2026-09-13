import { createHash, timingSafeEqual } from "node:crypto";

import type { MiddlewareHandler } from "hono";

import type { Settings } from "./config.js";
import { AppError } from "./errors.js";

export function apiSessionToken(apiKey: string): string {
  return createHash("sha256").update(`atlas-session:${apiKey}`, "utf8").digest("hex");
}

export function safeEqual(left: string, right: string): boolean {
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

function isPublic(path: string, method: string): boolean {
  const normalized = path.replace(/\/+$/, "") || "/";
  if (normalized === "/api/status") {
    return true;
  }
  if (normalized === "/api/auth/session" && (method === "POST" || method === "DELETE")) {
    return true;
  }
  return false;
}

export function authMiddleware(settings: Settings): MiddlewareHandler {
  return async (c, next) => {
    if (!settings.apiAuthEnabled || c.req.method === "OPTIONS") {
      return next();
    }
    const path = new URL(c.req.url).pathname;
    if (isPublic(path, c.req.method)) {
      return next();
    }
    const suppliedKey = c.req.header("x-atlas-api-key") ?? "";
    const suppliedSession = c.req.header("cookie")?.match(/(?:^|;\s*)atlas_session=([^;]+)/)?.[1] ?? "";
    const expected = settings.atlasApiKey;
    const keyMatches = safeEqual(suppliedKey, expected);
    const sessionMatches = safeEqual(suppliedSession, apiSessionToken(expected));
    if (!keyMatches && !sessionMatches) {
      throw new AppError("authentication required", { code: 401, statusCode: 401 });
    }
    return next();
  };
}

export function sessionCookie(settings: Settings, token: string): string {
  const parts = [
    `atlas_session=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Strict",
    `Max-Age=${8 * 60 * 60}`,
  ];
  if (settings.apiEnv === "production") {
    parts.push("Secure");
  }
  return parts.join("; ");
}
