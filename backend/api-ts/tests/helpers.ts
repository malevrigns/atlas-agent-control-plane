import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { createApp } from "../src/app.js";
import { loadSettings, type Settings } from "../src/core/config.js";
import { openDatabase } from "../src/infrastructure/db/client.js";

export async function makeTestApp(overrides: Partial<Settings> = {}) {
  const uploadDir = mkdtempSync(join(tmpdir(), "atlas-upload-"));
  const settings = loadSettings({
    apiAuthEnabled: false,
    atlasApiKey: "",
    databaseUrl: ":memory:",
    uploadDir,
    artifactDir: uploadDir,
    ...overrides,
  });
  const { db } = await openDatabase(":memory:");
  const app = createApp(settings, db);
  return { app, settings, db };
}

export async function json<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}
