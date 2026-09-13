import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { createSandboxApp } from "../src/app.js";
import { loadSandboxSettings } from "../src/core.js";

function makeApp(auth = false) {
  const workspaceDir = mkdtempSync(join(tmpdir(), "atlas-sandbox-"));
  process.env.WORKSPACE_DIR = workspaceDir;
  process.env.SANDBOX_AUTH_ENABLED = auth ? "true" : "false";
  process.env.ATLAS_API_KEY = auth ? "sandbox-secret" : "";
  const settings = loadSandboxSettings();
  settings.workspaceDir = workspaceDir;
  settings.authEnabled = auth;
  settings.atlasApiKey = auth ? "sandbox-secret" : "";
  return { app: createSandboxApp(settings), workspaceDir };
}

describe("sandbox", () => {
  it("status is public even with auth on", async () => {
    const { app } = makeApp(true);
    const response = await app.request("/api/status");
    expect(response.status).toBe(200);
    const body = (await response.json()) as { data: { status: string } };
    expect(body.data.status).toBe("ok");
  });

  it("rejects shell without a key", async () => {
    const { app } = makeApp(true);
    const response = await app.request("/api/shell/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "echo hi" }),
    });
    expect(response.status).toBe(401);
  });

  it("writes and reads a jailed file", async () => {
    const { app } = makeApp(false);
    const written = await app.request("/api/files/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "notes/hello.txt", content: "atlas", create_parent: true }),
    });
    expect(written.status).toBe(200);
    const read = await app.request("/api/files/read?path=notes/hello.txt");
    const body = (await read.json()) as { data: { content: string } };
    expect(body.data.content).toBe("atlas");
  });

  it("rejects path escape", async () => {
    const { app } = makeApp(false);
    const response = await app.request("/api/files/read?path=../secret");
    expect(response.status).toBe(400);
  });

  it("runs a shell command and waits", async () => {
    const { app } = makeApp(false);
    const started = await app.request("/api/shell/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: process.platform === "win32" ? "echo atlas" : "echo atlas" }),
    });
    expect(started.status).toBe(200);
    const id = ((await started.json()) as { data: { id: string } }).data.id;
    const waited = await app.request(`/api/shell/sessions/${id}/wait`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeout_seconds: 5 }),
    });
    const body = (await waited.json()) as { data: { output: string } };
    expect(body.data.output.toLowerCase()).toContain("atlas");
  });
});
