import { mkdirSync } from "node:fs";

import { serve } from "@hono/node-server";

import { createApp } from "./app.js";
import { loadSettings } from "./core/config.js";
import { openDatabase } from "./infrastructure/db/client.js";

async function main() {
  const settings = loadSettings();
  mkdirSync(settings.uploadDir, { recursive: true });
  mkdirSync(settings.artifactDir, { recursive: true });
  const { db } = await openDatabase(settings.databaseUrl);
  const app = createApp(settings, db);

  console.log(`AtlasAgent API (TypeScript)`);
  console.log(`  API   http://${settings.host}:${settings.port}${settings.apiPrefix}/status`);
  console.log(`  Data  ${settings.databaseUrl}`);
  if (!settings.apiAuthEnabled) {
    console.log("  Auth  disabled (API_AUTH_ENABLED=false)");
  }

  serve({ fetch: app.fetch, hostname: settings.host, port: settings.port });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
