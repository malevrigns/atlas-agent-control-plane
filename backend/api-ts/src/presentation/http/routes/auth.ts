import { Hono } from "hono";

import { apiSessionToken, safeEqual, sessionCookie } from "../../../core/auth.js";
import type { Settings } from "../../../core/config.js";
import { AppError, ok } from "../../../core/errors.js";

export function authRoutes(settings: Settings) {
  const router = new Hono();

  router.post("/session", async (c) => {
    const supplied = c.req.header("x-atlas-api-key") ?? "";
    if (settings.apiAuthEnabled) {
      const expected = settings.atlasApiKey;
      if (!expected || !safeEqual(supplied, expected)) {
        throw new AppError("invalid API key", { code: 401, statusCode: 401 });
      }
      c.header("Set-Cookie", sessionCookie(settings, apiSessionToken(expected)));
    }
    return c.json(ok({ authenticated: true }));
  });

  router.delete("/session", (c) => {
    c.header("Set-Cookie", "atlas_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict");
    return c.json(ok({ authenticated: false }));
  });

  router.get("/check", (c) => c.body(null, 204));

  return router;
}
