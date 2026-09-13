import { Hono } from "hono";
import { cors } from "hono/cors";

import { FileService } from "./application/file-service.js";
import { SessionService } from "./application/session-service.js";
import { authMiddleware } from "./core/auth.js";
import { corsOrigins, type Settings } from "./core/config.js";
import { AppError, fail, suggestionFor } from "./core/errors.js";
import type { Database } from "./infrastructure/db/client.js";
import { authRoutes } from "./presentation/http/routes/auth.js";
import { fileRoutes } from "./presentation/http/routes/files.js";
import { sessionRoutes } from "./presentation/http/routes/sessions.js";
import { statusRoutes } from "./presentation/http/routes/status.js";
import { controlPlaneRoutes } from "./presentation/http/routes/control-plane.js";
import { stubRoutes } from "./presentation/http/routes/stubs.js";

export type AppEnv = {
  Variables: {
    requestId: string;
  };
};

export function createApp(settings: Settings, db: Database) {
  const sessions = new SessionService(db);
  const files = new FileService(db, sessions, settings);
  const app = new Hono<AppEnv>();

  app.use("*", async (c, next) => {
    const requestId = c.req.header("x-request-id") || crypto.randomUUID();
    c.set("requestId", requestId);
    await next();
    c.header("X-Request-ID", requestId);
  });

  app.use(
    "*",
    cors({
      origin: corsOrigins(settings),
      credentials: true,
      allowHeaders: ["Content-Type", "X-Atlas-API-Key", "X-Request-ID", "Accept"],
      allowMethods: ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    }),
  );

  app.use("*", authMiddleware(settings));

  app.onError((error, c) => {
    const requestId = c.get("requestId") ?? null;
    if (error instanceof AppError) {
      if (error.statusCode === 401) {
        c.header("WWW-Authenticate", "AtlasApiKey");
      }
      return c.json(fail(error, requestId), error.statusCode as 400);
    }
    console.error(error);
    return c.json(
      fail(
        new AppError("internal server error", {
          code: 500,
          statusCode: 500,
          errorType: "internal_error",
          suggestion: suggestionFor("internal_error"),
        }),
        requestId,
      ),
      500,
    );
  });

  const api = new Hono<AppEnv>();
  api.route("/auth", authRoutes(settings));
  api.route("/status", statusRoutes(settings, db));
  api.route("/sessions", sessionRoutes(sessions, files, settings));
  api.route("/files", fileRoutes(files));
  api.route("/control-plane", controlPlaneRoutes(db));
  api.route("/", stubRoutes());
  app.route(settings.apiPrefix, api);
  return app;
}
