import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { z } from "zod";

import { streamUserMessage } from "../../../application/agent-stream.js";
import { FileService } from "../../../application/file-service.js";
import { SessionService } from "../../../application/session-service.js";
import type { Settings } from "../../../core/config.js";
import { AppError, ok } from "../../../core/errors.js";

const createSessionBody = z.object({
  title: z.string().default("新工作区"),
  workspace_dir: z.string().default(""),
  full_access: z.boolean().default(false),
});

const messageBody = z.object({
  content: z.string(),
  skill_ids: z.array(z.string()).optional(),
  resume: z.boolean().optional(),
});

export function sessionRoutes(
  sessions: SessionService,
  files: FileService,
  settings: Settings,
) {
  const router = new Hono();

  router.post("/", async (c) => {
    const body = createSessionBody.parse(await c.req.json().catch(() => ({})));
    const session = await sessions.createSession(
      body.title,
      body.workspace_dir,
      body.full_access,
    );
    return c.json(ok(session), 200);
  });

  router.get("/", async (c) => {
    const items = await sessions.listSessions();
    return c.json(ok({ items }));
  });

  router.get("/:sessionId", async (c) => {
    const session = await sessions.getSession(c.req.param("sessionId"));
    return c.json(ok(session));
  });

  router.get("/:sessionId/messages", async (c) => {
    const items = await sessions.listMessages(c.req.param("sessionId"));
    return c.json(ok({ items }));
  });

  router.get("/:sessionId/events", async (c) => {
    const items = await sessions.listEvents(c.req.param("sessionId"));
    return c.json(ok({ items }));
  });

  router.get("/:sessionId/context", async (c) => {
    const snapshot = await sessions.emptyContext(c.req.param("sessionId"));
    return c.json(ok(snapshot));
  });

  router.post("/:sessionId/messages", async (c) => {
    const body = messageBody.parse(await c.req.json());
    const created = await sessions.createUserMessage(c.req.param("sessionId"), body.content);
    return c.json(ok({ message: created.message, event: created.event }));
  });

  router.post("/:sessionId/messages/stream", async (c) => {
    const sessionId = c.req.param("sessionId");
    const body = messageBody.parse(await c.req.json());
    await sessions.getSession(sessionId);
    c.header("Cache-Control", "no-cache");
    c.header("Connection", "keep-alive");
    c.header("X-Accel-Buffering", "no");
    return streamSSE(c, async (stream) => {
      try {
        for await (const frame of streamUserMessage(sessions, settings, sessionId, body.content, {
          resume: body.resume,
          skillIds: body.skill_ids,
        })) {
          await stream.writeSSE({
            event: frame.event,
            data: JSON.stringify(frame.data),
          });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "stream failed";
        await stream.writeSSE({
          event: "task_error",
          data: JSON.stringify({
            session_id: sessionId,
            type: "task_error",
            payload: { user_message: message, mode: "chat" },
          }),
        });
      }
    });
  });

  router.post("/:sessionId/stop", async (c) => {
    const session = await sessions.updateStatus(c.req.param("sessionId"), "stopped");
    return c.json(ok(session));
  });

  router.post("/:sessionId/read", async (c) => {
    const session = await sessions.clearUnread(c.req.param("sessionId"));
    return c.json(ok(session));
  });

  router.delete("/:sessionId", async (c) => {
    await sessions.deleteSession(c.req.param("sessionId"));
    return c.body(null, 204);
  });

  router.get("/:sessionId/files", async (c) => {
    const items = await files.listSessionFiles(c.req.param("sessionId"));
    return c.json(ok({ items }));
  });

  router.post("/:sessionId/files", async (c) => {
    const body = await c.req.parseBody();
    const upload = body.upload;
    if (!isFile(upload)) {
      throw new AppError("upload is required", { code: 400, statusCode: 400 });
    }
    const bytes = new Uint8Array(await upload.arrayBuffer());
    const saved = await files.saveUpload(
      { name: upload.name, type: upload.type, data: bytes },
      c.req.param("sessionId"),
    );
    return c.json(ok(saved.sessionFile));
  });

  router.delete("/:sessionId/files/:sessionFileId", async (c) => {
    await files.deleteSessionFile(c.req.param("sessionId"), c.req.param("sessionFileId"));
    return c.body(null, 204);
  });

  return router;
}

function isFile(value: unknown): value is File {
  return Boolean(value) && typeof value === "object" && typeof (value as File).arrayBuffer === "function";
}
