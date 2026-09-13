# 第三章. 后端 API 与通用模块奠基

前两章把仓库的边界画清楚了，也把 Compose 里的基础设施容器写进了配置。到这一章为止，机器上还没有一个进程会回答 HTTP。前端以后要说话，沙箱以后要被调度，Agent 以后要把事件推出去——这些请求必须先落到一个入口上。这一章就把那个入口立起来。

代码在 `backend/api-ts`。语言是 TypeScript，框架是 Hono。不要再新建 Python 服务。

![深夜工位](../assets/ch03-desk.jpg)

## 为什么先做一个会喘气的进程

很多人一上手就写登录、写数据库、写 Agent 循环。那样看起来进度很快，过两周会发现每条接口的返回形状都不一样，错误有的是字符串，有的是 `{ detail: ... }`，有的直接把栈抛给浏览器。AtlasAgent 后面会有会话、文件、SSE、工具调用、验收门禁，前端会把这些东西织成一条时间线。如果后端现在不定规矩，第 26 章的工作台会把大量时间花在“兼容每个接口的怪癖”上。

所以这一章只做两件事。第一件，让进程能启动，并诚实回答 `GET /api/status`。第二件，在业务接口变多之前，把配置、统一信封、异常和 CORS 接到同一个 `createApp()` 里。做完之后，表面上仍然只有一个 status，内里已经是后面所有路由要站的那块底板。

## 为什么是 Hono

Express 也能返回 JSON。AtlasAgent 后面要推很长时间的 SSE，要和浏览器、沙箱、模型网关打交道，请求对象最好就是 Web 标准的 `Request` / `Response`。Hono 几乎不做自己的抽象，路由、中间件、流式输出都贴着这个标准。前端已经是 Next.js，后端再用同一套语言，类型和工具链少绕一圈。

仓库里的入口是 `src/main.ts`。它读配置、打开数据库、把 `createApp()` 交出去，然后用 `@hono/node-server` 听端口：

```ts
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

  serve({ fetch: app.fetch, hostname: settings.host, port: settings.port });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

`createApp` 和 `serve` 分开，是为了测试可以不听端口：vitest 里直接 `app.request("/api/status")` 就能打到同一套路由。这一点后面写契约测试时会用到。

![入口像一扇刚打开的门](../assets/ch03-gateway.jpg)

## 配置先集中，再谈路由

服务启动时必须知道自己是谁、听哪个口、数据库文件在哪、前端从哪些 Origin 打过来。这些东西散落在业务函数里，换环境就要改代码。`src/core/config.ts` 用 zod 把环境变量收成一份 `Settings`：

```ts
const settingsSchema = z.object({
  apiAppName: z.string().default("AtlasAgent API"),
  apiEnv: z.string().default("development"),
  apiVersion: z.string().default("0.1.0"),
  apiPrefix: z.string().default("/api"),
  apiAuthEnabled: booleanish.default(false),
  atlasApiKey: z.string().default(""),
  host: z.string().default("127.0.0.1"),
  port: z.coerce.number().int().positive().default(8000),
  databaseUrl: z.string().default("file:./var/atlas.db"),
  corsAllowOrigins: z
    .string()
    .default("http://localhost:3000,http://127.0.0.1:3000"),
});

export function loadSettings(overrides: Partial<Settings> = {}): Settings {
  return settingsSchema.parse({ ...readEnv(), ...overrides });
}
```

布尔环境变量在 shell 里永远是字符串，`"true"` 和 `true` 不是一回事，所以单独做了 `booleanish`。鉴权打开时如果还拿着空的或 `change-me` 的密钥，启动直接失败——这比带着默认密钥上线要好。

Compose 里把 `HOST` 设成 `0.0.0.0`，容器外才能探到健康检查。本机 `pnpm dev` 默认绑 `127.0.0.1`，避免服务意外暴露到局域网。

## 第一个接口：我还活着

`src/presentation/http/routes/status.ts` 几乎没有业务。它读配置，包进统一信封，返回去。数据库那条是后来加的：对 `sessions` 表 `select 1` 一下，连不上就说 `error`，不把异常细节甩给调用方。

```ts
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
```

Hono 的路由是拼出来的。`app.route("/api", api)` 再 `api.route("/status", statusRoutes())`，对外就是 `/api/status`。局部文件只关心自己那一截路径，前缀由装配函数决定。Docker 健康检查打的也是这个地址：进程活着不算数，路由能响应才算数。

成功时的形状是这样的。外层永远是 `code`、`message`、`data`、`error`；真正的业务在 `data` 里。

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "service": "AtlasAgent API",
    "environment": "development",
    "status": "ok",
    "version": "0.1.0"
  },
  "error": null
}
```

![信封：外层统一，内容另说](../assets/ch03-envelope.jpg)

## 信封和错误是一回事的两面

只统一成功、不统一失败，前端照样得写一堆分支。`src/core/errors.ts` 里的 `ok()` 和 `fail()` 共用同一个外壳。业务层抛 `AppError`，不要在每个 handler 里手写 `c.json(..., 404)`。

```ts
export function ok<T>(data: T, message = "success"): ApiEnvelope<T> {
  return { code: 200, message, data, error: null };
}

export class AppError extends Error {
  constructor(
    message: string,
    options: { code?: number; statusCode?: number } = {},
  ) {
    super(message);
    this.code = options.code ?? options.statusCode ?? 400;
    this.statusCode = options.statusCode ?? options.code ?? 400;
  }
}
```

`createApp()` 里的 `onError` 把 `AppError` 翻成信封，401 再带上 `WWW-Authenticate: AtlasApiKey`，给 Nginx 的 `auth_request` 和浏览器一个明确信号。未预料的异常记日志，对外只说 internal server error，并带上 `X-Request-ID`。请求进来时如果没带这个头，中间件会生成一个，响应里原样还回去。联调时把终端、Nginx、浏览器对上号，靠的就是它。

HTTP 状态码和信封里的 `code` 不是同一个东西。前者是协议层的对错，后者是项目自己的业务码。两者现在多数时候相等，但前端应先看 HTTP，再读 `error.user_message`。不要把它们揉成一个字段，后面做任务失败提示时会后悔。

## 装配顺序不是随便排的

`src/app.ts` 是公共能力汇合的地方。先贴 request id，再 CORS，再鉴权，再业务路由，错误处理挂在最外。日志和中间件要在路由开始接客之前就位，否则启动失败时你看不到原因，浏览器预检 OPTIONS 也会被鉴权挡回去。

```ts
export function createApp(settings: Settings, db: Database) {
  const app = new Hono<AppEnv>();

  app.use("*", async (c, next) => {
    const requestId = c.req.header("x-request-id") || crypto.randomUUID();
    c.set("requestId", requestId);
    await next();
    c.header("X-Request-ID", requestId);
  });

  app.use("*", cors({ origin: corsOrigins(settings), credentials: true }));
  app.use("*", authMiddleware(settings));
  app.onError((error, c) => { /* AppError → 信封 */ });

  const api = new Hono<AppEnv>();
  api.route("/status", statusRoutes(settings, db));
  app.route(settings.apiPrefix, api);
  return app;
}
```

CORS 不是权限系统。允许 `localhost:3000` 访问，只表示浏览器可以把这个来源的请求送过来。真正的登录是下一层的 API Key 和 `atlas_session` cookie。现在把 Origin 写进配置，是因为第 4 章前端默认就跑在 3000；不提前放行，下一章会卡在预检上，回头再改 CORS 会把两章的问题缠在一起。

这一章故意不写会话、不写 Agent、不把 Compose 绑死在 Postgres 上。现行运行时用 SQLite 文件库，`DATABASE_URL=file:./var/atlas.db` 就能起。数据库 schema 和会话路由是后面的章节，不挤进这一章。

## 跑起来

需要 Node 22 和 pnpm。在仓库根目录：

```bash
cd backend/api-ts
pnpm install
pnpm dev
```

另开一个终端：

```bash
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/not-found
curl -D - -H "Origin: http://localhost:3000" http://127.0.0.1:8000/api/status
```

第一条应看到 `code: 200` 和 `status: "ok"`。第二条应是 404 信封，`data` 为 `null`。第三条的响应头里应有 `access-control-allow-origin: http://localhost:3000`。契约测试已经把这几条写进 `backend/api-ts/tests/contract.test.ts`，改信封之前先跑 `pnpm test`。

整套带 Nginx 的栈用根目录的 `BUILD=true ./scripts/start.sh`（Windows 用 `start.ps1`）。Compose 构建的是 `backend/api-ts`，健康检查同样打 `/api/status`。

## 这一章留下了什么

一个能启动的 TypeScript 进程，一条可被 curl、浏览器和 Docker 共同验证的状态接口，以及后面所有路由要遵守的信封、错误和跨域约定。下一章把 Next.js 工作台和 Nginx 接到这个入口上。会话列表、SSE、工具运行时都还没出场——那是好事。底板不稳，上面叠多少 Agent 都会晃。

---

[← 第二章. Docker Compose 基础设施奠基](02-Docker%20Compose%20基础设施奠基.md) · [返回目录](../README.md) · [第四章. 前端 UI 与 Nginx 网关贯通 →](04-前端%20UI%20与%20Nginx%20网关贯通.md)
