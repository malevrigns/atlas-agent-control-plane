import { readFile } from "node:fs/promises";

import { Hono } from "hono";

import { ok, sandboxAuth, SandboxError, type SandboxSettings } from "./core.js";
import { FileService } from "./files.js";
import { ShellService } from "./shell.js";

export function createSandboxApp(settings: SandboxSettings) {
  const files = new FileService(settings);
  const shell = new ShellService(settings, files);
  const app = new Hono();
  app.use("*", sandboxAuth(settings));
  app.onError((error, c) => {
    if (error instanceof SandboxError) {
      return c.json(
        { code: error.code, message: error.message, data: null, error: { user_message: error.message } },
        error.statusCode as 400,
      );
    }
    console.error(error);
    return c.json({ code: 500, message: "internal server error", data: null }, 500);
  });

  const api = new Hono();
  api.get("/status", (c) =>
    c.json(
      ok({
        service: settings.appName,
        environment: settings.env,
        status: "ok",
        version: settings.version,
        workspace_dir: settings.workspaceDir,
      }),
    ),
  );

  api.get("/vnc/status", (c) =>
    c.json(
      ok({
        enabled: settings.vncEnabled,
        display: settings.vncDisplay,
        vnc_port: settings.vncPort,
        web_port: settings.vncWebPort,
        iframe_path: settings.vncIframePath,
        websocket_path: "sandbox-vnc/websockify",
        message: settings.vncEnabled
          ? "noVNC remote desktop is configured."
          : "VNC remote desktop is disabled.",
      }),
    ),
  );

  api.get("/files", async (c) => {
    const data = await files.list(
      c.req.query("path") ?? ".",
      c.req.query("workspace") ?? "",
      c.req.query("full_access") === "true",
    );
    return c.json(ok(data));
  });

  api.get("/files/read", async (c) => {
    const path = c.req.query("path");
    if (!path) {
      throw new SandboxError("path is required");
    }
    return c.json(
      ok(await files.read(path, c.req.query("workspace") ?? "", c.req.query("full_access") === "true")),
    );
  });

  api.post("/files/write", async (c) => {
    const body = await c.req.json<{ path: string; content: string; create_parent?: boolean }>();
    return c.json(
      ok(
        await files.write(
          body.path,
          body.content ?? "",
          Boolean(body.create_parent),
          c.req.query("workspace") ?? "",
          c.req.query("full_access") === "true",
        ),
      ),
    );
  });

  api.post("/files/replace", async (c) => {
    const body = await c.req.json<{ path: string; old_text: string; new_text: string }>();
    return c.json(
      ok(
        await files.replace(
          body.path,
          body.old_text,
          body.new_text,
          c.req.query("workspace") ?? "",
          c.req.query("full_access") === "true",
        ),
      ),
    );
  });

  api.delete("/files", async (c) => {
    const path = c.req.query("path");
    if (!path) {
      throw new SandboxError("path is required");
    }
    return c.json(
      ok(await files.delete(path, c.req.query("workspace") ?? "", c.req.query("full_access") === "true")),
    );
  });

  api.get("/files/download", async (c) => {
    const path = c.req.query("path");
    if (!path) {
      throw new SandboxError("path is required");
    }
    const target = await files.existingFile(
      path,
      c.req.query("workspace") ?? "",
      c.req.query("full_access") === "true",
    );
    const bytes = await readFile(target);
    const name = target.split(/[\\/]/).pop() ?? "download";
    return new Response(bytes, {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="${name}"`,
      },
    });
  });

  api.post("/shell/sessions", async (c) => {
    const body = await c.req.json<{ command: string; cwd?: string }>();
    if (!body.command?.trim()) {
      throw new SandboxError("command is required");
    }
    return c.json(
      ok(
        shell.execute(
          body.command,
          body.cwd ?? ".",
          c.req.query("workspace") ?? "",
          c.req.query("full_access") === "true",
        ),
      ),
    );
  });
  api.get("/shell/sessions", (c) => c.json(ok(shell.list())));
  api.get("/shell/sessions/:id", (c) => c.json(ok(shell.get(c.req.param("id")))));
  api.post("/shell/sessions/:id/wait", async (c) => {
    const body = (await c.req.json().catch(() => ({}))) as { timeout_seconds?: number };
    return c.json(ok(await shell.wait(c.req.param("id"), body.timeout_seconds)));
  });
  api.post("/shell/sessions/:id/write", async (c) => {
    const body = await c.req.json<{ input: string }>();
    return c.json(ok(shell.write(c.req.param("id"), body.input ?? "")));
  });
  api.post("/shell/sessions/:id/terminate", (c) => c.json(ok(shell.terminate(c.req.param("id")))));

  api.get("/browser/status", (c) =>
    c.json(
      ok({
        enabled: settings.browserEnabled,
        status: settings.browserEnabled ? "idle" : "disabled",
        message: "Playwright browser is managed by the TypeScript sandbox image.",
      }),
    ),
  );

  api.get("/supervisor/services", (c) => c.json(ok({ items: [] })));

  app.route(settings.prefix, api);
  return app;
}
