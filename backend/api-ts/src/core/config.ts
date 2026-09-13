import { z } from "zod";

const booleanish = z
  .union([z.boolean(), z.string()])
  .transform((value) => {
    if (typeof value === "boolean") {
      return value;
    }
    return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
  });

const settingsSchema = z.object({
  apiAppName: z.string().default("AtlasAgent API"),
  apiEnv: z.string().default("development"),
  apiVersion: z.string().default("0.1.0"),
  apiPrefix: z.string().default("/api"),
  apiAuthEnabled: booleanish.default(false),
  atlasApiKey: z.string().default(""),
  logLevel: z.string().default("INFO"),
  host: z.string().default("127.0.0.1"),
  port: z.coerce.number().int().positive().default(8000),
  databaseUrl: z.string().default("file:./var/atlas.db"),
  uploadDir: z.string().default("uploads"),
  artifactDir: z.string().default("artifacts"),
  maxUploadSize: z.coerce.number().int().positive().default(10 * 1024 * 1024),
  maxFilePreviewSize: z.coerce.number().int().positive().default(64 * 1024),
  corsAllowOrigins: z
    .string()
    .default("http://localhost:3000,http://127.0.0.1:3000,http://localhost:8088,http://127.0.0.1:8088"),
  llmApiKey: z.string().default(""),
  llmBaseUrl: z.string().default("https://api.deepseek.com/v1"),
  llmModel: z.string().default("deepseek-chat"),
});

export type Settings = z.infer<typeof settingsSchema>;

function readEnv(): Record<string, unknown> {
  return {
    apiAppName: process.env.API_APP_NAME,
    apiEnv: process.env.API_ENV,
    apiVersion: process.env.API_VERSION,
    apiPrefix: process.env.API_PREFIX,
    apiAuthEnabled: process.env.API_AUTH_ENABLED,
    atlasApiKey: process.env.ATLAS_API_KEY,
    logLevel: process.env.LOG_LEVEL,
    host: process.env.HOST,
    port: process.env.PORT,
    databaseUrl: process.env.DATABASE_URL,
    uploadDir: process.env.UPLOAD_DIR,
    artifactDir: process.env.ARTIFACT_DIR,
    maxUploadSize: process.env.MAX_UPLOAD_SIZE,
    maxFilePreviewSize: process.env.MAX_FILE_PREVIEW_SIZE,
    corsAllowOrigins: process.env.CORS_ALLOW_ORIGINS,
    llmApiKey: process.env.LLM_API_KEY,
    llmBaseUrl: process.env.LLM_BASE_URL,
    llmModel: process.env.LLM_MODEL,
  };
}

export function loadSettings(
  overrides: Partial<Record<keyof Settings, unknown>> = {},
): Settings {
  const parsed = settingsSchema.parse({ ...readEnv(), ...overrides });
  if (parsed.apiAuthEnabled && (!parsed.atlasApiKey || parsed.atlasApiKey === "change-me")) {
    throw new Error("ATLAS_API_KEY is required when API_AUTH_ENABLED=true");
  }
  return parsed;
}

/** Accept SQLAlchemy URLs from start.sh and turn them into libsql/postgres targets. */
export function normalizeDatabaseUrl(url: string): { kind: "sqlite" | "postgres"; url: string } {
  if (url.startsWith("sqlite+aiosqlite:///")) {
    const path = url.slice("sqlite+aiosqlite:///".length);
    return { kind: "sqlite", url: path.startsWith("file:") ? path : `file:${path}` };
  }
  if (url.startsWith("sqlite:///")) {
    return { kind: "sqlite", url: `file:${url.slice("sqlite:///".length)}` };
  }
  if (url.startsWith("file:") || url.startsWith(":memory:")) {
    return { kind: "sqlite", url };
  }
  if (url.startsWith("postgresql+asyncpg://")) {
    return { kind: "postgres", url: `postgresql://${url.slice("postgresql+asyncpg://".length)}` };
  }
  if (url.startsWith("postgres://") || url.startsWith("postgresql://")) {
    return { kind: "postgres", url };
  }
  return { kind: "sqlite", url: url.startsWith("file:") ? url : `file:${url}` };
}

export function corsOrigins(settings: Settings): string[] {
  const raw = settings.corsAllowOrigins.trim();
  if (raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.map(String);
      }
    } catch {
      // fall through to comma split
    }
  }
  return raw
    .split(",")
    .map((item) => item.trim().replace(/^["']|["']$/g, ""))
    .filter(Boolean);
}
