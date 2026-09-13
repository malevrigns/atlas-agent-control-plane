# 第四章. 前端 UI 与 Nginx 网关贯通

第三章让控制平面会喘气了：`curl http://127.0.0.1:8000/api/status` 能拿到信封。用户不会开终端看 JSON。这一章把浏览器接到同一条路上，再用 Nginx 把「打开一个网址」收成一个入口。

前端在 `frontend/web`，仍然是 TypeScript。网关配置在 `nginx/default.conf`。API 继续是 `backend/api-ts`。

![工作台第一次出现在屏幕上](../assets/ch04-workbench.jpg)

## 浏览器里要有一块地方能长大

AtlasAgent 后面要同时放下会话列表、输入框、计划卡片、工具输出、文件预览、VNC。如果现在只做一张宣传页，过几章就得拆布局。首页从一开始就按工作台来：左侧导航，中间对话，右侧预览，顶上有 API 是否还活着的标记。这一章不实现聊天，只证明页面能起来，并且能读到第 3 章那个 status。

本地开发时浏览器打的是 `http://localhost:3000`。页面里的 `fetch("/api/status")` 是同源路径，并不直连 8000。Next 用 rewrite 把 `/api/*` 转到 Hono。这样前端代码里永远写 `/api/...`，开发走 Next，生产走 Nginx，路径不用改。

```ts
// frontend/web/next.config.ts
const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          process.env.API_PROXY_URL ?? "http://localhost:8000/api/:path*",
      },
      {
        source: "/sandbox-api/:path*",
        destination:
          process.env.SANDBOX_PROXY_URL ??
          "http://localhost:8100/api/:path*",
      },
    ];
  },
};
```

Docker 里 UI 容器拿到的 `API_PROXY_URL` 是 `http://api:8000/api/:path*`，因为容器之间用 Compose 服务名通信，不是 localhost。这一点漏了，页面会在容器里请求自己，status 永远转圈。

有一类请求 rewrite 处理不好：SSE。Next 开发服务器会把上游流缓冲，逐字回答变成「憋很久然后一次性弹出」。流式接口后来改走 App Router 的 `app/api/sessions/[sessionId]/messages/stream/route.ts`，把后端流原样 pipe 出去，cookie 仍走同源。这一章先知道有这个坑，真正写对话时再接那条路由。

## 页面怎样读信封

`frontend/web/app/lib/api.ts` 假定每个 JSON 都长成第 3 章定的样子。`code >= 400` 或 HTTP 不成功，就抽 `error.user_message`。`data` 为空当错误。204 是删除和 `auth/check` 那种没有身体的成功。

首页启动时打 `/api/status/database` 判断要不要弹出 API Key 门。401 才锁住；后端挂了反而放行到工作台，让你看到「API 异常」而不是误以为密钥错了。这是产品上的选择，不是协议要求。

本地把两件事一起跑：

```bash
# 终端 1
cd backend/api-ts
pnpm dev

# 终端 2
cd frontend/web
pnpm install
pnpm dev
```

浏览器打开 `http://localhost:3000`。右上角应变成 API 正常。如果转圈或报错，先看 API 终端有没有请求进来，再看浏览器网络面板里 `/api/status` 是 200 还是被 rewrite 打到了空处。

## 一个端口，而不是三个

开发可以记 3000 和 8000。交给别人用时，让人开两个端口、处理 CORS、自己拼路径，是在转嫁复杂度。Nginx 听 `127.0.0.1:8088`，把 `/` 转给 UI，把 `/api/` 转给 Hono，把 `/sandbox-api/` 转给沙箱，把 `/sandbox-vnc/` 转给 websockify。浏览器只记住一个网址。

![网关把几根线收成一口](../assets/ch04-gateway.jpg)

`nginx/default.conf` 里和 API 有关的几段是这样的。SSE 必须关掉缓冲，否则第 7 章的事件流会在网关里攒着，前端以为后端卡死。

```nginx
location /api/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header X-Accel-Buffering no;
    proxy_pass http://api:8000;
}

location / {
    proxy_pass http://ui:3000;
}
```

`proxy_read_timeout` 拉到 3600 秒，因为一次 Agent 跑完可能很久。`client_max_body_size 20m` 给文件上传留余量。网关只绑回环地址，Compose 里是 `${NGINX_HOST:-127.0.0.1}:${NGINX_PORT:-8088}:80`，避免笔记本一启动就把工作台暴露到局域网。

登录之后，静态上传和 VNC 不能再裸奔。Nginx 用内部子请求问控制平面「这张 cookie 还有效吗」：

```nginx
location = /_atlas_auth {
    internal;
    proxy_pass http://api:8000/api/auth/check;
    proxy_pass_request_body off;
    proxy_set_header Cookie $http_cookie;
    proxy_set_header X-Atlas-API-Key $http_x_atlas_api_key;
}

location /sandbox-vnc/ {
    auth_request /_atlas_auth;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_pass http://sandbox:6080/;
}
```

`/api/auth/check` 必须返回 **204**，不能带 JSON 身体。auth_request 只认 2xx。第 3 章的 Hono 路由已经按这个契约写了。改成 200 加 `{ ok: true }` 看起来更完整，网关会认为鉴权失败。

## 一次只验证一件事

开发期用两个终端就够。要确认「别人只开 8088 也能用」，在仓库根目录：

```bash
cp .env.example .env
BUILD=true ./scripts/start.sh
```

Windows 用 `$env:BUILD="true"; ./scripts/start.ps1`。脚本会生成 `ATLAS_API_KEY` 并打印出来。打开 `http://localhost:8088`，把 Key 填进门。然后：

```bash
curl http://localhost:8088/api/status
```

应和直接打 8000 时同一份信封。Compose 里 `api` 构建的是 `backend/api-ts`，`ui` 构建的是 `frontend/web`，健康检查失败时 Nginx 不会起来，这是故意的：入口活着却没有后端，比报错更难查。

这一章没有实现对话，也没有把沙箱嵌进页面。布局和网关在，数据还是空的。下一章开始往 SQLite 里写会话。那时候前端已经有地方把列表挂上去，不必再为「页面从哪来」吵架。

---

[← 第三章. 后端 API 与通用模块奠基](03-后端%20API%20与通用模块奠基.md) · [返回目录](../README.md) · [第五章. 数据库、迁移与会话模型立制 →](05-数据库、迁移与会话模型立制.md)
