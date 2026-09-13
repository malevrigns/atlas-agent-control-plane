import { desc, eq } from "drizzle-orm";
import { Hono } from "hono";
import { z } from "zod";

import { AppError, ok } from "../../../core/errors.js";
import { newId, nowIso } from "../../../domain/sessions.js";
import type { Database } from "../../../infrastructure/db/client.js";
import { agentTasks } from "../../../infrastructure/db/schema.js";

const createTask = z.object({
  title: z.string().min(1),
  goal: z.string().default(""),
  project_id: z.string().default("default"),
  acceptance_criteria: z.array(z.string()).optional(),
});

export function controlPlaneRoutes(db: Database) {
  const router = new Hono();

  router.post("/tasks", async (c) => {
    const body = createTask.parse(await c.req.json());
    const stamp = nowIso();
    const row = {
      id: newId(),
      sessionId: null,
      projectId: body.project_id,
      title: body.title,
      goal: body.goal,
      status: "pending",
      version: 1,
      stateHash: newId().slice(0, 12),
      progress: { done: [] as string[], doing: [] as string[], blocked: [] as string[] },
      createdAt: stamp,
      updatedAt: stamp,
    };
    await db.insert(agentTasks).values(row);
    return c.json(ok(toTask(row)));
  });

  router.get("/tasks", async (c) => {
    const projectId = c.req.query("project_id") ?? "default";
    const rows = await db
      .select()
      .from(agentTasks)
      .where(eq(agentTasks.projectId, projectId))
      .orderBy(desc(agentTasks.updatedAt));
    return c.json(ok({ items: rows.map(toTask) }));
  });

  router.get("/tasks/:taskId", async (c) => {
    const row = await db.query.agentTasks.findFirst({
      where: eq(agentTasks.id, c.req.param("taskId")),
    });
    if (!row) {
      throw new AppError("task not found", { code: 404, statusCode: 404 });
    }
    return c.json(ok(toTask(row)));
  });

  router.get("/tasks/:taskId/checkpoints", (c) => c.json(ok({ items: [] })));
  router.get("/tool-invocations", (c) => c.json(ok({ items: [] })));
  return router;
}

function toTask(row: {
  id: string;
  title: string;
  goal: string;
  status: string;
  version: number;
  stateHash: string;
  progress: { done: string[]; doing: string[]; blocked: string[] };
}) {
  return {
    id: row.id,
    title: row.title,
    goal: row.goal,
    status: row.status,
    version: row.version,
    state_hash: row.stateHash,
    progress: row.progress,
  };
}
