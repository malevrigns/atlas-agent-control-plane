import { mkdirSync } from "node:fs";

import { serve } from "@hono/node-server";

import { createSandboxApp } from "./app.js";
import { loadSandboxSettings } from "./core.js";

const settings = loadSandboxSettings();
mkdirSync(settings.workspaceDir, { recursive: true });
const app = createSandboxApp(settings);
console.log(`AtlasAgent Sandbox (TypeScript)`);
console.log(`  API   http://${settings.host}:${settings.port}${settings.prefix}/status`);
console.log(`  Work  ${settings.workspaceDir}`);
serve({ fetch: app.fetch, hostname: settings.host, port: settings.port });
