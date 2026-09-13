import { Hono } from "hono";

import { ok } from "../../../core/errors.js";

/** Empty-but-shaped responses so the existing web workbench does not 404
 *  while later phases port memories / RAG / skills / MCP. */
export function stubRoutes() {
  const router = new Hono();

  router.get("/config/app", (c) =>
    c.json(
      ok({
        modules: [],
        integrations: [],
        llm: { default_provider: "openai_compatible", default_model: "deepseek-chat" },
      }),
    ),
  );
  router.get("/config/llm", (c) =>
    c.json(ok({ default_provider: "openai_compatible", default_model: "deepseek-chat", providers: [] })),
  );

  const empty = (c: { json: (body: unknown) => Response }) => c.json(ok({ items: [] }));
  router.get("/memories", empty);
  router.get("/rag/knowledge-bases", empty);
  router.get("/rag/health", (c) => c.json(ok({ status: "ok", backend: "sql" })));
  router.get("/skills", empty);
  router.get("/skills/context", (c) => c.json(ok({ items: [], query: "" })));
  router.get("/mcp/servers", empty);
  router.get("/mcp/tools", empty);
  router.get("/mcp/concepts", empty);
  router.get("/a2a/concepts", empty);
  router.get("/a2a/agents", empty);
  router.get("/multi-agent/roles", empty);
  router.get("/harness/cases", empty);
  router.get("/observability/checks", empty);
  router.get("/security/checks", empty);
  router.get("/acceptance/checks", empty);
  router.get("/control-plane/tasks", empty);
  router.get("/control-plane/tool-invocations", empty);
  router.get("/agent-core/tools", empty);
  router.get("/sandboxes/current", (c) =>
    c.json(
      ok({
        id: "default",
        name: "atlas-sandbox",
        base_url: process.env.SANDBOX_API_BASE_URL ?? "http://localhost:8100/api",
        status: "unavailable",
        message: "TypeScript sandbox is not in this slice; Python sandbox still serves :8100",
      }),
    ),
  );

  return router;
}
