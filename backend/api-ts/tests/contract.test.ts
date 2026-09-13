import { describe, expect, it } from "vitest";

import { apiSessionToken } from "../src/core/auth.js";
import { normalizeDatabaseUrl } from "../src/core/config.js";
import { json, makeTestApp } from "./helpers.js";

describe("wire contract", () => {
  it("serves the public status envelope", async () => {
    const { app } = await makeTestApp();
    const response = await app.request("/api/status");
    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBeTruthy();
    const body = await json<{
      code: number;
      message: string;
      data: { status: string; service: string };
      error: null;
    }>(response);
    expect(body).toMatchObject({
      code: 200,
      message: "success",
      error: null,
    });
    expect(body.data.status).toBe("ok");
    expect(body.data.service).toBe("AtlasAgent API");
  });

  it("echoes incoming X-Request-ID", async () => {
    const { app } = await makeTestApp();
    const response = await app.request("/api/status", {
      headers: { "X-Request-ID": "req-fixed" },
    });
    expect(response.headers.get("x-request-id")).toBe("req-fixed");
  });

  it("rejects missing credentials with WWW-Authenticate", async () => {
    const { app } = await makeTestApp({
      apiAuthEnabled: true,
      atlasApiKey: "secret-key",
    });
    const response = await app.request("/api/sessions");
    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe("AtlasApiKey");
    const body = await json<{ code: number; error: { type: string; user_message: string } }>(
      response,
    );
    expect(body.code).toBe(401);
    expect(body.error.user_message).toBe("authentication required");
  });

  it("exchanges the API key for an HttpOnly atlas_session cookie", async () => {
    const { app } = await makeTestApp({
      apiAuthEnabled: true,
      atlasApiKey: "secret-key",
    });
    const response = await app.request("/api/auth/session", {
      method: "POST",
      headers: { "X-Atlas-API-Key": "secret-key" },
    });
    expect(response.status).toBe(200);
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("atlas_session=");
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie).toContain(apiSessionToken("secret-key"));

    const check = await app.request("/api/auth/check", {
      headers: { Cookie: `atlas_session=${apiSessionToken("secret-key")}` },
    });
    expect(check.status).toBe(204);
  });

  it("normalizes SQLAlchemy URLs", () => {
    expect(normalizeDatabaseUrl("sqlite+aiosqlite:///C:/tmp/atlas.db")).toEqual({
      kind: "sqlite",
      url: "file:C:/tmp/atlas.db",
    });
    expect(normalizeDatabaseUrl("postgresql+asyncpg://postgres:x@postgres:5432/atlas_agents")).toEqual({
      kind: "postgres",
      url: "postgresql://postgres:x@postgres:5432/atlas_agents",
    });
  });
});
