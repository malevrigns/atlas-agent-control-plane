# 第四章. 前端 UI 与 Nginx 网关贯通

## 4.1 合章说明

​        旧版教程把“前端 UI 最小服务初成”与“Nginx 网关贯通”拆成了相邻两章。两者实际上属于同一条能力链：前者把基础结构立住，后者让它进入可用状态。本章将它们合并为前后两个阶段，保留原来的实现、验证与工程判断，同时减少能力尚未闭环时的章节跳转。

## 4.2 第一阶段：前端 UI 最小服务初成

### 4.2.1 本阶段目标

​        前四章主要在搭后端和基础工程，项目虽然已经能通过 `/api/status` 回答自己是否正常，但它仍然停留在命令行世界里。笔者认为，一个 Agent 工作台如果一直只能用 `curl` 验证，就很难让人形成产品感。真正的用户不会打开终端观察 JSON，他们需要在浏览器里看到入口、状态、模块边界和后续能力的雏形。
​        本阶段的目标，就是把 AtlasAgent 从“后端服务可用”推进到“浏览器里有一个最小工作台”。读者会创建一个 Next.js 前端应用，理解 App Router 下 `layout.tsx` 和 `page.tsx` 的分工，使用 pnpm 管理依赖，使用 Tailwind CSS 写出基础界面，再用 `lucide-react` 给导航和状态区域加入图标。更重要的是，页面不只是静态壳子，它会真实请求第 3 章已经整理好的 `/api/status`，让前端第一次和后端连起来。

### 4.2.2 最终效果

​        本阶段结束后，项目会新增一个前端工作台页面。读者在浏览器里访问下面的地址，就能看到 AtlasAgent 的第一个 UI 入口。

```Plain
http://localhost:3000
```

​        这个页面不是宣传页，也不是只放一个标题的占位页。它会采用工作台结构：左侧是模块导航，顶部显示当前页面和 API 状态，中间有 API 状态卡片，右侧预留后续能力卡片，底部再放一个任务流预览。这样做的用意，是让读者从 UI 出现的第 1 章开始，就看到它未来会承载会话、文件、沙箱和设置，而不是等功能堆起来后再临时调整布局。
​        页面启动后会请求同源路径：

```Plain
/api/status
```

​        如果后端 API 正常，右上角会显示：

```Plain
API 正常
```

​        本阶段仍然保持克制，不实现会话列表、聊天输入、文件预览、设置面板或 VNC。原因不是这些功能不重要，而是 UI 的第一步应该先证明前后端可以稳定通信。只有这个闭环成立，后面再往页面里填真实业务数据才有意义。

### 4.2.3 本阶段要解决的问题

​        第 3 章已经让后端 API 有了统一响应、异常处理、日志和 CORS，但项目还没有用户界面。这意味着我们虽然已经打好了 API 的基础，却还没有把这些能力交给浏览器。继续只靠 `curl` 验证接口，当然可以证明接口存在，却无法证明产品体验会如何展开。
​        AtlasAgent 之后要展示的内容很多：会话列表、用户输入、Agent 推理过程、工具调用结果、文件变化、浏览器观察、Shell 输出、任务失败原因和最终回答。所有这些信息都需要一个可以持续扩展的页面容器。因此本阶段要先创建 UI 最小服务，让浏览器打开工作台页面，并让这个页面读取后端 `/api/status`。这一步完成后，项目链路会从“终端访问 API”变成“浏览器访问 UI，UI 再访问 API”。

```Plain
浏览器
  |
  v
Next.js UI
  |
  |  /api/status
  v
FastAPI API
```

### 4.2.4 本阶段技术方案

​        本阶段选择 Next.js 作为前端框架。纯 HTML、CSS 和 JavaScript 可以更轻，但它很快会在状态管理、组件拆分和构建部署上变得吃力；Vite + React 也足够优秀，启动快、结构简单；但本项目后续会有多个页面、复杂状态展示、Docker 构建、网关转发和部署联调，Next.js 的 App Router、standalone 构建产物和 rewrite 机制更贴合这条路线。
​        依赖管理选择 pnpm。笔者在教程项目里比较看重锁文件的稳定性，因为读者可能在不同机器、不同时间重新安装依赖。如果锁文件不稳定，前端问题很容易变成“你那里能跑，我这里不能跑”。pnpm 的安装速度、磁盘复用和锁文件表现都比较适合这种逐章演进的项目。
​        本阶段会创建 `ui/package.json` 和 `pnpm-lock.yaml`，搭出 Next.js App Router 目录，编写工作台首页，引入 Tailwind CSS 和 lucide 图标，配置 `/api` rewrite 到后端，再把 UI 服务加入 Docker Compose。暂时不做登录、会话数据、聊天输入、SSE 流式事件、复杂组件拆分，也不通过 Nginx 访问前端。本章第二阶段会专门加入 Nginx，把 `/` 转发到 UI，把 `/api` 转发到 API。

### 4.2.5 新增和修改的文件

​        本阶段的文件分布比前几章更明显：根目录负责把 UI 接入整体工程，`ui/` 目录负责前端自身的依赖、构建、样式和页面。读者可以先把这些文件看成一个最小 Next.js 应用，再观察它如何通过 Compose 和后端服务连起来。

```Plain
.env.example
README.md
docker-compose.yml
ui/.dockerignore
ui/README.md
ui/Dockerfile
ui/package.json
ui/pnpm-lock.yaml
ui/next.config.ts
ui/postcss.config.mjs
ui/tsconfig.json
ui/next-env.d.ts
ui/app/globals.css
ui/app/layout.tsx
ui/app/page.tsx
ui/public/.gitkeep
```

### 4.2.6 开始前检查：确认 Node.js 和 pnpm 可用

​        本阶段第一次使用前端环境，所以动手之前要先确认 Node.js 和 pnpm 可用。后端章节主要依赖 Python 和 Docker，而前端构建会进入 Node.js 生态。如果这里版本不合适，后面出现的构建报错往往和业务代码无关。
​        先检查 Node.js：

```Bash
node --version
```

​        正常情况下会看到类似输出：

```Plain
v25.9.0
```

​        Next.js 16 要求较新的 Node.js。建议使用 Node.js 20 或更新版本。

​        Next.js 16 要求较新的 Node.js。示例里显示的是 `v25.9.0`，实际开发中使用 Node.js 20 或更新版本即可。继续检查 pnpm：

```Bash
pnpm --version
```

​        正常情况下会看到类似输出：

```Plain
10.33.2
```

​        如果没有安装 pnpm，可以先执行：

```Bash
npm install -g pnpm
```

​        安装完成后重新执行 `pnpm --version`。这一步虽然简单，但建议认真做完，因为后面 `pnpm install`、`pnpm build` 和 Docker 构建都会依赖同一套前端工具链。

### 4.2.7 实施步骤
#### 4.2.7.1 创建前端项目配置

​        先在 `ui/` 目录创建 `package.json`。这个文件是前端项目的入口，它定义项目名称、脚本、包管理器版本以及运行和构建所需的依赖。

```JSON
{
  "name": "atlas-agents-ui",
  "version": "0.1.0",
  "private": true,
  "packageManager": "pnpm@10.33.2",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "lucide-react": "^0.561.0",
    "next": "^16.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.0.0",
    "@types/node": "^24.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.0.0"
  }
}
```

​        这里的核心依赖可以按职责理解。`next` 负责应用框架和构建，`react` 与 `react-dom` 负责页面运行时，`tailwindcss` 负责样式表达，`lucide-react` 提供界面图标，`typescript` 则负责类型检查。脚本里保留 `dev`、`build`、`start` 和 `typecheck`，是为了同时覆盖开发调试、生产构建、生产启动和静态类型检查这几种常见动作。

#### 4.2.7.2 安装依赖并生成锁文件

​        配置写好后进入 `ui` 目录，安装依赖。

```Bash
cd ui
```

​        安装依赖：

```Bash
pnpm install
```

​        安装完成后会生成：

```Plain
ui/pnpm-lock.yaml
```

​        `package.json` 描述项目需要什么依赖，`pnpm-lock.yaml` 记录实际安装到的版本。前者像需求说明，后者像锁定后的安装快照。后续其他电脑或 Docker 构建时，会按锁文件安装一致版本，这能避免教程项目因为依赖小版本变化出现不可复现的问题。

#### 4.2.7.3 创建 Next.js 配置

​        接着在 `ui/` 下创建 `next.config.ts`。这个配置文件有两个关键点：一个是 `output: "standalone"`，它会让 Next.js 构建出更适合 Docker 运行的独立服务目录；另一个是 `rewrites()`，它会把浏览器请求的 `/api/:path*` 转发到真实后端地址。

```TypeScript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.API_PROXY_URL ?? "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
```

​        本地开发时，浏览器请求的是 UI 自己的路径：

```Plain
/api/status
```

​        Next.js 会转发到本机后端：

```Plain
http://localhost:8000/api/status
```

​        到 Docker Compose 中，代理地址会变成容器网络里的服务名：

```Plain
http://api:8000/api/status
```

​        这样前端代码里不用写死后端真实地址。页面只写 `fetch("/api/status")`，至于这个 `/api` 最后被转到 `localhost:8000` 还是 `api:8000`，交给 Next.js 配置和环境变量处理。这个设计会在本章第二阶段接入 Nginx 时继续发挥作用。

#### 4.2.7.4 创建 TypeScript 和 PostCSS 配置

​        然后创建 TypeScript 和 PostCSS 配置。`tsconfig.json` 定义前端代码如何被 TypeScript 理解，`postcss.config.mjs` 则让 Next.js 能处理 Tailwind CSS。

```JSON
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ]
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

​        创建 `ui/postcss.config.mjs`：

```JavaScript
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```

​        `tsconfig.json` 里开启了 `strict`，这意味着页面代码从一开始就要对类型负责。对于 Agent 工作台这种状态很多、接口很多的前端来说，类型检查不是负担，而是防止状态字段写错、接口数据理解错的基本保护。执行 `pnpm build` 后，Next.js 可能会自动补充 `.next/dev/types/**/*.ts` 到 `include` 中，这是正常现象。

#### 4.2.7.5 创建应用入口

​        App Router 的根布局写在 `ui/app/layout.tsx`。这个文件会包裹所有页面内容，所以全局样式和页面元信息也从这里进入应用。

```TypeScript
import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AtlasAgent",
  description: "AtlasAgent workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
```

​        这里设置了 `lang="zh-CN"`，引入 `globals.css`，并定义页面标题和描述。现在的布局还很薄，但它是后续页面共享结构的入口。等项目继续扩展，导航外壳、主题、全局状态或字体配置都可能在这里继续演进。

#### 4.2.7.6 编写全局样式

​        接下来写全局样式。`ui/app/globals.css` 先引入 Tailwind CSS，再设置基础颜色、盒模型、页面高度和默认字体。

```CSS
@import "tailwindcss";

:root {
  color-scheme: light;
  --background: #f6f7f9;
  --foreground: #17202a;
}

* {
  box-sizing: border-box;
}

html,
body {
  min-height: 100%;
}

body {
  margin: 0;
  background: var(--background);
  color: var(--foreground);
  font-family: Arial, Helvetica, sans-serif;
}
```

​        本阶段先使用简单的全局样式，不引入复杂设计系统。原因和前几章一样：先把闭环跑通，再在真实组件出现时逐步抽象。现在只需要确保页面有稳定背景、文字颜色、盒模型和基础字体即可。

#### 4.2.7.7 编写工作台页面

​        首页写在 `ui/app/page.tsx`。文件开头需要写：

```TypeScript
"use client";
```

​        因为本阶段页面会在浏览器里使用 `useEffect` 请求 `/api/status`，所以它是客户端组件。先定义 API 返回类型，让前端结构和第 3 章后端统一响应保持一致。

```TypeScript
type ApiStatusData = {
  service: string;
  environment: string;
  status: string;
  version: string;
};

type ApiResponse<T> = {
  code: number;
  message: string;
  data: T | null;
};
```

​        然后请求 API：

```TypeScript
useEffect(() => {
  let ignore = false;

  async function loadStatus() {
    try {
      const response = await fetch("/api/status");
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as ApiResponse<ApiStatusData>;
      if (!payload.data) {
        throw new Error(payload.message);
      }
      if (!ignore) {
        setStatus({ type: "ready", data: payload.data });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      if (!ignore) {
        setStatus({ type: "error", message });
      }
    }
  }

  loadStatus();

  return () => {
    ignore = true;
  };
}, []);
```

​        这里使用 `ignore` 是为了避免组件卸载后继续更新状态。状态本身也不是简单的布尔值，而是分成 `loading`、`ready` 和 `error` 三种形态。这样页面可以在检测中、检测成功和检测失败时显示不同提示，用户不会看到一个没有解释的空白区域。
​        页面结构可以理解成一个工作台雏形：

```Plain
左侧导航
  |
  +-- 工作台
  +-- 会话
  +-- 文件
  +-- 沙箱
  +-- 设置

主内容
  |
  +-- 顶部状态
  +-- API 状态卡片
  +-- 后续能力卡片
  +-- 任务流预览
```

​        本阶段先把这些区域做出来，后续章节会逐步把静态区域替换成真实功能。左侧导航现在只是模块入口的样子，状态卡片现在只展示后端健康信息，任务流预览也只是占位；但这些区域的存在，会让读者从一开始就看到最终产品的空间布局。

#### 4.2.7.8 加入 Dockerfile

​        前端能本地运行还不够，教程项目最终要能通过 Docker Compose 一起启动，所以还需要给 UI 加入 Dockerfile。先在 `ui/` 下创建 `.dockerignore`，避免把本地依赖和构建产物送进 Docker 构建上下文。

```Plain
node_modules
.next
out
dist
build
*.log
```

​        这些文件都是本地依赖或构建产物，不应该进入 Docker 构建上下文。再创建 `ui/Dockerfile`：

```Dockerfile
FROM node:24-alpine AS deps

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:24-alpine AS builder

WORKDIR /app

RUN corepack enable

ARG API_PROXY_URL=http://localhost:8000/api/:path*
ENV API_PROXY_URL=$API_PROXY_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN pnpm build

FROM node:24-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -S nextjs && adduser -S nextjs -G nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
```

​        这个 Dockerfile 分成三段。`deps` 阶段只安装依赖，`builder` 阶段复制源码并执行 `pnpm build`，`runner` 阶段只运行构建产物。多阶段构建的好处，是最终运行镜像不需要带上完整源码、开发依赖和构建缓存，镜像会更干净。
​        `ARG API_PROXY_URL` 是构建参数。Next.js 的 rewrite 会在构建时读取这个值，所以 Docker Compose 运行时需要在构建阶段把 API 地址传进去。这里也是很多前端容器化项目容易踩坑的地方：有些配置是运行时读取，有些配置在构建时就已经固化。文档把这一点写清楚，后面排查代理问题时会轻松很多。

#### 4.2.7.9 把 UI 加入 Docker Compose

​        UI 镜像可以构建之后，还要把它接入根目录 `docker-compose.yml`。在 `services` 下新增 `ui` 服务，让它和 `api`、`postgres`、`redis` 处在同一个 Compose 工程中。

```YAML
  ui:
    build:
      context: ./ui
      args:
        API_PROXY_URL: ${UI_API_PROXY_URL:-http://api:8000/api/:path*}
    container_name: atlas-ui
    restart: unless-stopped
    environment:
      API_PROXY_URL: ${UI_API_PROXY_URL:-http://api:8000/api/:path*}
      NEXT_TELEMETRY_DISABLED: 1
    ports:
      - "${UI_PORT:-3000}:3000"
    networks:
      - atlas-network
    depends_on:
      - api
```

​        这里有几个细节需要连起来看。`UI_PORT` 控制宿主机访问 UI 的端口；`build.args.API_PROXY_URL` 控制 Next.js 构建时写入的 API 代理地址；`environment.API_PROXY_URL` 保留运行时环境变量，方便后续扩展；`depends_on` 表示 UI 会在 API 服务创建后启动；`ui` 和 `api` 都在 `atlas-network` 中，所以容器里可以通过 `api` 这个服务名访问后端。容器中的 `localhost` 指向自己，不是另一个服务，这一点一定要记住。

#### 4.2.7.10 更新环境变量模板

​        最后更新 `.env.example`，把 UI 端口和 UI 访问 API 的代理地址写进模板。

```Plain
UI_PORT=3000
UI_API_PROXY_URL=http://api:8000/api/:path*
```

​        本地开发时，如果直接 `pnpm dev`，默认代理地址是：

```Plain
http://localhost:8000/api/:path*
```

​        Docker Compose 运行时，代理地址是：

```Plain
http://api:8000/api/:path*
```

​        这是因为容器之间不能用宿主机的 `localhost` 互相访问。`api` 是 Compose 网络里的服务名，UI 容器通过这个名字找到后端容器。理解这个差异，后面处理 Nginx、Sandbox 和更多服务之间的访问关系时会少很多困惑。

### 4.2.8 关键理解

​        本阶段最重要的是理解“前端请求自己的 `/api`，再由 Next.js 转发到后端”。浏览器实际请求的是 UI 所在站点：

```Plain
http://localhost:3000/api/status
```

​        Next.js 转发到：

```Plain
http://localhost:8000/api/status
```

​        Docker Compose 里则转发到容器网络中的 API 服务：

```Plain
http://api:8000/api/status
```

​        这样做有两个好处。第一，浏览器不需要知道后端真实地址，页面代码也不需要在不同环境里改来改去。第二，后续本章第二阶段加入 Nginx 时，请求路径仍然可以保持 `/api/status`。换句话说，用户和前端代码看到的是稳定路径，环境差异被藏在配置层和网关层。
​        还有一个重要点：本阶段做的是“应用工作台”，不是宣传页面。所以界面优先展示系统状态、模块入口和后续任务流，而不是大幅营销文案。一个 Agent 产品真正要被反复使用，第一屏应该让用户知道系统现在能做什么、哪些服务正常、任务会如何流转，而不是先讲一段空泛愿景。

### 4.2.9 技术难点与亮点

​        本阶段的技术难点集中在“前端工程化”和“环境差异”上。`layout.tsx` 和 `page.tsx` 是 App Router 的两个核心入口，前者负责全局布局，后者负责当前路由页面。因为页面需要在浏览器里使用 `useEffect` 发起请求，所以文件顶部必须声明 `"use client"`。如果没有这个声明，React Hook 和浏览器请求逻辑就不能按客户端组件的方式运行。
​        另一个难点是 `fetch("/api/status")` 为什么能访问后端。它不是浏览器直接请求 `http://localhost:8000`，而是先请求 Next.js 自己的 `/api/status`，再通过 rewrite 转发到后端。到了 Docker Compose 里，后端地址又从 `localhost:8000` 变成 `api:8000`。这不是代码随便换地址，而是本地环境和容器网络的访问模型不同。
​        本阶段的亮点，是前端从出现的第 1 章起就接入真实后端状态，而不是做一个纯静态页面。UI 采用工作台结构，为会话、文件、沙箱和设置预留位置；Next.js rewrite 隔离后端真实地址；Dockerfile 使用多阶段构建，让运行镜像更干净；页面状态也包含 loading、ready、error 三种情况。这些小设计会让后续功能接入时更顺。

### 4.2.10 面试考点

​        面试里如果聊到这一阶段，重点不会是“Tailwind 的某个类名是什么意思”，而是你是否理解前端应用如何接入后端服务。你需要能说清楚 `layout.tsx` 和 `page.tsx` 的职责，为什么这个页面必须是客户端组件，为什么前端请求 `/api/status` 而不是直接写死 `http://localhost:8000/api/status`，Next.js rewrite 和后端 CORS 分别解决什么问题，Docker 多阶段构建为什么能让镜像更干净，以及为什么 UI 容器里访问后端要使用服务名 `api`。
​        这些问题背后考察的是工程链路。一个页面能显示出来只是第一层，真正能说明能力的是：你知道请求从浏览器出发后经过了哪里，知道它在本地和容器里为什么走不同地址，也知道为什么要提前把这种差异收进配置。

### 4.2.11 运行验证

​        本阶段验证要覆盖两条线：本地前端构建能不能通过，前后端联调能不能拿到状态；Docker Compose 能不能把 UI 服务加入整体工程，并通过容器网络访问 API。下面命令默认在项目根目录执行：

```Bash
pwd
```

​        预期目录类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

#### 4.2.11.1 安装前端依赖

​        先进入 UI 目录安装依赖。第一次安装会下载 Next.js、React、Tailwind、TypeScript 和图标库，耗时主要取决于网络和包缓存。

```Bash
cd ui
```

​        安装依赖：

```Bash
pnpm install
```

​        预期会生成：

```Plain
pnpm-lock.yaml
node_modules/
```

​        `node_modules/` 不会提交到仓库，真正需要提交的是 `package.json` 和 `pnpm-lock.yaml`。前者说明依赖范围，后者锁定安装结果。

#### 4.2.11.2 构建前端

​        依赖安装后执行构建。构建可以提前暴露 TypeScript、Next.js 配置和页面代码里的问题。

```Bash
pnpm build
```

​        预期看到：

```Plain
Compiled successfully
```

​        构建产物会写入 `ui/.next`，这个目录也不会提交到仓库。它属于本地构建结果，Dockerfile 会在镜像构建阶段重新生成。

#### 4.2.11.3 本地联调 API 和 UI

​        接下来做本地联调。先启动 API。如果本机 `8000` 端口可用：

```Bash
cd ../api
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

​        如果本机 `8000` 已经被占用，可以使用 `18000`：

```Bash
cd ../api
uv run uvicorn app.main:app --host 127.0.0.1 --port 18000
```

​        然后打开另一个终端启动 UI。API 在 `8000` 时：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/ui
pnpm dev
```

​        API 在 `18000` 时：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents/ui
API_PROXY_URL=http://localhost:18000/api/:path* pnpm dev
```

​        浏览器访问：

```Plain
http://localhost:3000
```

​        页面右上角应该显示：

```Plain
API 正常
```

​        API 状态卡片里应该能看到：

```Plain
服务名称：AtlasAgent API
运行环境：development
服务状态：ok
版本：0.1.0
```

#### 4.2.11.4 检查 Compose 配置

​        本地联调通过后，回到项目根目录检查 Compose 配置，确认 `ui` 服务已经被纳入整体工程。

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        执行：

```Bash
docker compose config
```

​        预期输出里能看到 `ui` 服务：

```Plain
services:
  ui:
    container_name: atlas-ui
```

#### 4.2.11.5 Docker Compose 运行

​        第一次完整启动，或者 API、UI 的 Dockerfile 有改动时，执行：

```Bash
docker compose up -d --build
```

​        这里的 `--build` 表示启动前先构建镜像。它会检查需要构建的服务，所以可能会同时构建 `api` 和 `ui`。

​        访问：

```Plain
http://localhost:3000
```

​        如果本机 `3000` 端口被占用，可以临时改端口：

```Bash
UI_PORT=13000 docker compose up -d
```

​        然后访问：

```Plain
http://localhost:13000
```

​        这里没有加 `--build`，因为只是改宿主机端口，不需要重新构建镜像。如果只改了 UI 代码，只想重新构建 UI 服务，可以执行：

```Bash
docker compose build ui
UI_PORT=13000 docker compose up -d ui
```

​        这样可以减少不必要的镜像构建时间。停止服务：

```Bash
docker compose down
```

### 4.2.12 阶段小结

​        本阶段完成了 AtlasAgent 的第一个前端闭环。我们创建了 Next.js 前端项目，配置了 TypeScript、Tailwind CSS 和 App Router，实现了工作台首页，让页面可以读取 `/api/status`，再通过 Next.js rewrite 隔离后端真实地址。随后又编写 UI Dockerfile，把 UI 服务加入 Docker Compose，并验证了本地构建、前后端联调和 Compose 配置。
​        从这一阶段开始，项目不再只是后端接口，而是有了可以打开和观察的浏览器界面。它还很小，但已经具备一个工作台产品的基本轮廓：左侧有模块入口，顶部有系统状态，中间能看到后端服务是否正常，页面也为后续任务流和工具能力留出了空间。

## 4.3 第二阶段：Nginx 网关贯通

### 4.3.1 本阶段目标

​        本章第一阶段完成之后，项目已经有了前端页面，也能让页面读取后端状态。但这个阶段还有一个明显问题：浏览器访问 UI 时记住的是前端端口，调试 API 时又要记住后端端口。项目小的时候这还能接受，等后面继续加入沙箱、文件访问、SSE、WebSocket 和 VNC，入口就会越来越多，开发和部署都会变得混乱。
​        本阶段要做的事情，是给 AtlasAgent 加一个统一网关。读者会理解为什么真实系统通常不会把每个服务都直接暴露给浏览器，会学习 Nginx 反向代理的基本工作方式，也会用 Docker Compose 同时启动 Nginx、UI 和 API。完成后，前端页面和后端接口都可以通过同一个端口访问，读者也要能区分宿主机访问地址、Docker Compose 服务名和容器内部端口。这个区分非常重要，很多容器联调问题都不是业务代码错了，而是地址写错了。

### 4.3.2 最终效果

​        本阶段结束后，项目会新增一个 Nginx 网关服务。浏览器不再直接访问 UI 容器，也不再直接访问 API 容器，而是统一访问 Nginx 暴露出来的端口。

```Plain
http://localhost:8088
```

​        这个地址会显示本章第一阶段完成的前端工作台页面。继续访问：

```Plain
http://localhost:8088/api/status
```

​        会看到后端 API 的统一响应：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "service": "AtlasAgent API",
    "environment": "development",
    "status": "ok",
    "version": "0.1.0"
  }
}
```

​        这时请求链路已经不再是“浏览器分别找 UI 和 API”，而是变成“浏览器只找 Nginx，Nginx 按路径找后面的服务”。

```Plain
浏览器
  |
  |  http://localhost:8088
  v
Nginx 网关
  |
  +-- /      -> Next.js UI
  |
  +-- /api  -> FastAPI API
```

### 4.3.3 本阶段要解决的问题

​        本章第一阶段已经完成了前端页面，也能通过 `/api/status` 读取后端状态。但那仍然更像开发阶段的联调方式：UI 有自己的端口，API 也有自己的端口。后续如果再加入沙箱、文件服务、VNC 远程桌面、SSE 事件流和 WebSocket，入口会越来越散。

```Plain
http://localhost:3000       前端页面
http://localhost:8000/api   后端 API
后续还会有沙箱、VNC、文件访问等入口
```

​        真实系统通常会提供一个统一入口。浏览器只访问网关，网关再根据路径把请求转发到不同服务。页面请求走 `/`，API 请求走 `/api`，后续文件、SSE、VNC 也可以继续挂到清晰的路径下。这样用户只需要记住 `http://localhost:8088`，系统内部有几个容器、每个容器监听什么端口，都不应该成为浏览器侧需要关心的事情。

### 4.3.4 本阶段技术方案

​        本阶段选择 Nginx 作为网关。继续直接访问 UI 和 API 各自的端口当然最简单，本章第一阶段使用的 Next.js rewrite 也能解决前端开发阶段的 API 转发。但这两种方式都不是完整系统的统一入口。Next.js rewrite 更像是前端服务内部的一层便利代理，而 Nginx 才更接近真实部署时摆在最前面的网关。
​        选择 Nginx 的原因很直接：它是非常常见的反向代理组件，可以独立运行在 Docker Compose 中，也方便后续继续扩展 SSE、WebSocket、VNC、静态文件访问和 HTTPS。更重要的是，从这一阶段开始，浏览器访问路径会更接近真实部署形态。用户打开的是网关地址，服务之间通过 Docker 网络互相访问。
​        本阶段会新增 `nginx/default.conf`，在 Docker Compose 中加入 `nginx` 服务，把 `/` 代理到 `ui:3000`，把 `/api` 和 `/api/` 代理到 `api:8000`。同时，UI 和 API 不再通过 `ports` 暴露给宿主机，而是使用 `expose` 在 Docker 网络内部开放端口。这样宿主机只需要暴露一个 `8088`，项目入口更干净，也能减少本机端口冲突。
​        本阶段暂时不配置 HTTPS、不绑定域名、不处理 SSE 长连接，也不处理 WebSocket、VNC 和上传文件静态访问。这些能力都会在后续章节根据真实需要加入。先把最基础的网关链路跑通，读者才能看清 Nginx 在系统里的位置。

### 4.3.5 新增和修改的文件

​        本阶段改动的文件集中在网关层和运行编排层。`nginx/default.conf` 是真正的代理规则，`docker-compose.yml` 决定 Nginx、UI 和 API 在容器网络里如何连接，`.env.example` 则记录网关端口和 CORS 来源。读者可以把这一阶段看成“把已有前后端服务收进统一入口”的章节。

```Plain
.env.example
README.md
docker-compose.yml
nginx/README.md
nginx/default.conf
```

### 4.3.6 开始前理解：反向代理是什么

​        在进入配置之前，先把反向代理这件事说清楚。普通请求是浏览器直接访问服务：

```Plain
浏览器 -> UI
浏览器 -> API
```

​        反向代理则是在浏览器和服务之间加一个入口：

```Plain
浏览器 -> Nginx -> UI
浏览器 -> Nginx -> API
```

​        浏览器只知道 Nginx 的地址，不需要知道后面有几个服务，也不需要知道每个服务的真实端口。在本阶段中，三个地址各有含义：

```Plain
localhost:8088 是宿主机访问 Nginx 的端口
ui:3000        是 Nginx 容器访问 UI 容器的地址
api:8000       是 Nginx 容器访问 API 容器的地址
```

​        `ui` 和 `api` 不是公网域名，也不是本机目录，它们是 Docker Compose 服务名。只要服务在同一个 Docker 网络里，就可以通过服务名互相访问。很多初学者会把容器内访问地址写成 `localhost:3000` 或 `localhost:8000`，这通常会出错，因为容器里的 `localhost` 指向当前容器自己，而不是 Compose 里的其他服务。

### 4.3.7 实施步骤
#### 4.3.7.1 编写 Nginx 配置

​        先在 `nginx/` 目录下创建 `default.conf`。这个文件定义 Nginx 接到请求后应该转发给谁。

```Nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 20m;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    location = /api {
        proxy_pass http://api:8000;
    }

    location /api/ {
        proxy_pass http://api:8000;
    }

    location / {
        proxy_pass http://ui:3000;
    }
}
```

​        先看最外层：

```Nginx
server {
    listen 80;
    server_name _;
}
```

​        Nginx 容器内监听 `80` 端口。后面会在 Docker Compose 中把宿主机的 `8088` 映射到容器的 `80`，所以浏览器访问 `localhost:8088`，最终会进入 Nginx 容器的 80 端口。`server_name _;` 表示这里不绑定具体域名，本地开发访问 `localhost` 也能命中这个配置。
​        再看请求头：

```Nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

​        这些配置会把原始请求信息传给后端服务。后续如果要记录访问 IP、生成完整链接、判断请求协议，就会用到这些头。现在看起来用处不大，但网关层最好从一开始就保留这些基础信息。
​        最后看代理规则：

```Nginx
location = /api {
    proxy_pass http://api:8000;
}

location /api/ {
    proxy_pass http://api:8000;
}

location / {
    proxy_pass http://ui:3000;
}
```

​        这三段分别处理 `/api`、`/api/status` 这类 API 请求，以及 `/`、`/_next/static/...` 这类前端页面和静态资源请求。这里 `proxy_pass http://api:8000;` 后面没有额外拼 `/api/`，是为了保留原始路径。浏览器请求 `/api/status`，API 服务收到的仍然是 `/api/status`。如果写成 `proxy_pass http://api:8000/api/;`，路径很容易被拼错，后续排查会比较麻烦。

#### 4.3.7.2 把 Nginx 加入 Docker Compose

​        接着打开根目录 `docker-compose.yml`，在 `services` 下加入 `nginx`。它是本阶段唯一暴露给宿主机的服务。

```YAML
services:
  nginx:
    image: nginx:1.27-alpine
    container_name: atlas-nginx
    restart: unless-stopped
    ports:
      - "${NGINX_PORT:-8088}:80"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - atlas-network
    depends_on:
      - ui
      - api
```

​        逐项理解这段配置。`image` 使用官方 Nginx Alpine 镜像：

```YAML
image: nginx:1.27-alpine
```

​        `ports` 负责端口映射：

```YAML
ports:
  - "${NGINX_PORT:-8088}:80"
```

​        左边的 `8088` 是宿主机端口，右边的 `80` 是容器内端口。所以浏览器访问：

```Plain
http://localhost:8088
```

​        实际进入的是 Nginx 容器内的：

```Plain
http://atlas-nginx:80
```

​        本章第一阶段中，UI 和 API 曾经通过 `ports` 暴露给宿主机。本阶段有了 Nginx 统一入口后，就要把 UI 和 API 改成只在 Docker 网络内开放。UI 服务使用：

```YAML
expose:
  - "3000"
```

​        API 服务使用：

```YAML
expose:
  - "8000"
```

​        `expose` 不会占用宿主机端口，只表示容器网络里的其他服务可以访问这个端口。所以本机即使已经有本地前端服务占用了 `3000`，也不会影响本阶段的容器启动。这一点正是统一网关带来的实际好处：宿主机端口更少，冲突也更少。
​        `volumes` 把本地配置挂载进容器：

```YAML
volumes:
  - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
```

​        `ro` 表示只读挂载。Nginx 容器可以读取配置，但不会修改项目里的配置文件。`networks` 让 Nginx 加入项目网络：

```YAML
networks:
  - atlas-network
```

​        加入同一个网络后，Nginx 才能访问：

```Plain
http://ui:3000
http://api:8000
```

​        `depends_on` 表示启动顺序：

```YAML
depends_on:
  - ui
  - api
```

​        它表示先创建 UI 和 API，再创建 Nginx。注意，`depends_on` 不等于等待服务完全可用。如果刚启动的一瞬间页面打不开，可以等几秒钟再刷新。后续如果需要更严格的启动约束，可以结合健康检查继续改进，但本阶段先保持配置简单。

#### 4.3.7.3 确认环境变量

​        第 1 章已经在 `.env.example` 中预留了：

```Plain
NGINX_PORT=8088
```

​        如果本机 `8088` 端口没有被占用，不需要改。如果 `8088` 被占用，可以在启动时临时换端口：

```Bash
NGINX_PORT=18088 docker compose up -d --no-build nginx
```

​        访问地址也对应变成：

```Plain
http://localhost:18088
```

#### 4.3.7.4 更新 Nginx 目录说明

​        打开 `nginx/README.md`，写入当前网关规则：

```Plain
/      -> ui:3000
/api   -> api:8000
/api/* -> api:8000
```

​        这份 README 不是运行必需文件，但它能让后续维护时快速知道 Nginx 现在承担哪些职责。随着 SSE、VNC、文件访问和 HTTPS 加入，这个目录会越来越重要。

#### 4.3.7.5 更新环境变量模板

​        打开 `.env.example`，确认保留：

```Plain
NGINX_PORT=8088
UI_API_PROXY_URL=http://api:8000/api/:path*
```

​        本阶段之后，Docker Compose 默认只把 Nginx 暴露给宿主机，所以不再需要 `UI_PORT` 和 `API_PORT` 控制 UI、API 的宿主机直连端口。同时把 CORS 来源补充为：

```Plain
CORS_ALLOW_ORIGINS=["http://localhost:8088","http://127.0.0.1:8088","http://localhost:3000","http://127.0.0.1:3000"]
```

​        `8088` 是网关访问地址，`3000` 保留给本地前端开发。这样无论通过 Nginx 访问，还是本地直接运行 UI 调试，后端 CORS 都能识别合法来源。

### 4.3.8 关键理解

​        本阶段最重要的是理解三种地址：

```Plain
http://localhost:8088  浏览器访问 Nginx
http://ui:3000         Nginx 容器访问 UI 容器
http://api:8000        Nginx 容器访问 API 容器
```

​        不要在容器之间写：

```Plain
http://localhost:3000
http://localhost:8000
```

​        因为在容器内，`localhost` 永远指向当前容器自己。Nginx 容器里的 `localhost:8000` 指的是 Nginx 容器自己，不是 API 容器。这个细节一旦理解清楚，很多“明明服务启动了但访问不到”的问题就能快速定位。
​        第二个重点是路径保留。浏览器请求：

```Plain
/api/status
```

​        Nginx 转发给 API 后，API 仍然应该收到：

```Plain
/api/status
```

​        所以本阶段的 API 代理写成：

```Nginx
proxy_pass http://api:8000;
```

​        而不是：

```Nginx
proxy_pass http://api:8000/api/;
```

​        第三个重点是 Nginx 和 Next.js rewrite 的关系。本章第一阶段的 Next.js rewrite 仍然保留，它用于直接访问 UI 端口时转发 API。本阶段新增的 Nginx 用于统一入口：

```Plain
浏览器 -> Nginx -> UI
浏览器 -> Nginx -> API
```

​        两者不冲突。后续通过网关访问时，浏览器请求 `/api/status` 会优先被 Nginx 转发到 API，不需要进入 UI 的 rewrite。直接访问 UI 端口做前端开发时，rewrite 仍然可以继续兜住 API 请求。

### 4.3.9 技术难点与亮点

​        本阶段的技术难点主要是地址和路径。宿主机端口、容器端口、Compose 服务名、Nginx 代理路径，这几个概念混在一起时很容易出错。`localhost:8088` 是浏览器访问宿主机，`ui:3000` 是 Nginx 容器访问 UI 容器，`api:8000` 是 Nginx 容器访问 API 容器。它们看起来都是地址，但所处网络完全不同。
​        `proxy_pass` 后面是否带路径，也是 Nginx 配置里很容易踩坑的地方。本阶段故意写成 `proxy_pass http://api:8000;`，就是为了让 `/api/status` 原样进入 FastAPI。如果多拼一段路径，API 收到的路径可能变成不符合预期的形式。
​        本阶段的项目亮点，是前后端开始拥有统一访问入口。UI 和 API 的真实地址被网关隐藏起来，浏览器只看到一个更接近真实部署的入口。后续 SSE、WebSocket、VNC、文件访问都可以继续在 Nginx 层扩展，而不是让浏览器同时记住一堆端口。

### 4.3.10 面试考点

​        面试聊到这一阶段时，故障排查会围绕反向代理和容器网络展开。你需要能解释 Nginx 反向代理和正向代理有什么区别，为什么容器之间不能使用 `localhost` 互相访问，Docker Compose 服务名为什么可以作为网络地址，`proxy_pass http://api:8000;` 和 `proxy_pass http://api:8000/api/;` 在路径处理上有什么不同，以及 `depends_on` 为什么只能控制创建顺序，不能保证服务已经健康。
​        如果能把这些问题讲清楚，说明你不是只会复制一段 Nginx 配置，而是真的理解请求从浏览器进入网关、再进入后端服务的完整路径。

### 4.3.11 运行验证

​        本阶段验证要看两条链路：`/api/status` 能不能通过 Nginx 转到 API，`/` 能不能通过 Nginx 转到 UI。下面命令默认在项目根目录执行：

```Bash
pwd
```

​        预期目录类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

#### 4.3.11.1 检查 Compose 配置

​        先检查 Compose 配置，确认 `nginx` 服务已经被解析出来，端口映射也符合预期。

```Bash
docker compose config
```

​        预期输出里能看到 `nginx` 服务：

```Plain
services:
  nginx:
    container_name: atlas-nginx
```

​        还应该能看到端口映射：

```Plain
published: "8088"
target: 80
```

#### 4.3.11.2 启动服务

​        如果已经完成本章第一阶段，并且本机已经构建过 API 和 UI 镜像，本阶段只新增 Nginx 服务，不需要重新构建 API 和 UI。执行：

```Bash
docker compose up -d --no-build nginx
```

​        这条命令会启动 `nginx`，并自动启动它依赖的 `ui` 和 `api`。如果这是第一次运行 Docker Compose，或者本机还没有 API、UI 镜像，可以执行完整构建：

```Bash
docker compose up -d --build
```

​        完整构建可能会拉取 Nginx、Node、Python、PostgreSQL、Redis、uv 等镜像。网络慢时需要等待一会儿。启动完成后执行：

```Bash
docker compose ps
```

​        预期能看到这些服务：

```Plain
atlas-nginx
atlas-ui
atlas-api
atlas-postgres
atlas-redis
```

#### 4.3.11.3 验证 API 代理

​        先验证 API 代理。这个请求从宿主机进入 Nginx，再由 Nginx 转给 API 容器。

```Bash
curl http://localhost:8088/api/status
```

​        预期返回：

```JSON
{"code":200,"message":"success","data":{"service":"AtlasAgent API","environment":"development","status":"ok","version":"0.1.0"}}
```

​        如果这个接口正常，说明：

```Plain
浏览器或 curl -> Nginx -> API
```

​        这条链路已经打通。

#### 4.3.11.4 验证页面代理

​        再验证页面代理。浏览器访问：

```Plain
http://localhost:8088
```

​        页面应该显示本章第一阶段完成的工作台，右上角应该显示：

```Plain
API 正常
```

​        如果页面能打开，但 API 显示异常，优先检查：

```Bash
curl http://localhost:8088/api/status
docker compose logs --tail=80 nginx
docker compose logs --tail=80 api
```

#### 4.3.11.5 更换 Nginx 端口

​        如果本机 `8088` 端口被占用，可以执行：

```Bash
NGINX_PORT=18088 docker compose up -d --no-build nginx
```

​        然后访问：

```Plain
http://localhost:18088
```

​        停止服务：

```Bash
docker compose down
```

### 4.3.12 阶段小结

​        本阶段完成了 AtlasAgent 的统一网关入口。我们新增了 Nginx 配置文件，在 Docker Compose 中加入 Nginx 服务，把 `/` 代理到 UI，把 `/api` 代理到 API，并通过 `http://localhost:8088` 同时验证了前端页面和后端状态接口。与此同时，UI 和 API 从宿主机直连端口改成 Docker 网络内部开放端口，系统入口变得更收敛。
​        从这一阶段开始，项目具备了更接近真实部署的访问方式。后续新增会话、聊天、文件、SSE、沙箱和 VNC 时，都可以继续围绕这个统一入口扩展。Nginx 不只是多启动了一个容器，它开始承担整个系统入口层的职责。

## 4.4 本章小结

​        完成“前端 UI 最小服务初成”和“Nginx 网关贯通”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第三章. 后端 API 与通用模块奠基](03-后端%20API%20与通用模块奠基.md) · [返回目录](../README.md) · [第五章. 数据库、迁移与会话模型立制 →](05-数据库、迁移与会话模型立制.md)
