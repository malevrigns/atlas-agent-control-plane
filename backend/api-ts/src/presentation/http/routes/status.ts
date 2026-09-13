import { Hono } from "hono";

import type { Settings } from "../../../core/config.js";
import { ok } from "../../../core/errors.js";
import type { Database } from "../../../infrastructure/db/client.js";
import { sessions } from "../../../infrastructure/db/schema.js";

export function statusRoutes(settings: Settings, db: Database) {
  const router = new Hono();

  router.get("/", (c) =>
    c.json(
      ok({
        service: settings.apiAppName,
        environment: settings.apiEnv,
        status: "ok",
        version: settings.apiVersion,
      }),
    ),
  );

  router.get("/database", async (c) => {
    try {
      await db.select({ id: sessions.id }).from(sessions).limit(1);
      return c.json(ok({ status: "ok" }));
    } catch {
      return c.json(ok({ status: "error" }));
    }
  });

  return router;
}
