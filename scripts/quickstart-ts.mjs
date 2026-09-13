#!/usr/bin/env node
/** TypeScript zero-dep boot: SQLite + in-process API, no Docker. */

import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiDir = join(root, "backend", "api-ts");
const dataDir = join(apiDir, "var", "standalone");
mkdirSync(dataDir, { recursive: true });

const env = {
  ...process.env,
  DATABASE_URL: process.env.DATABASE_URL ?? `file:${join(dataDir, "atlas.db")}`,
  API_AUTH_ENABLED: process.env.API_AUTH_ENABLED ?? "false",
  UPLOAD_DIR: process.env.UPLOAD_DIR ?? join(dataDir, "uploads"),
  ARTIFACT_DIR: process.env.ARTIFACT_DIR ?? join(dataDir, "artifacts"),
  HOST: process.env.HOST ?? "127.0.0.1",
  PORT: process.env.PORT ?? "8000",
};

const child = spawn("pnpm", ["start"], { cwd: apiDir, env, stdio: "inherit", shell: true });
child.on("exit", (code) => process.exit(code ?? 0));
