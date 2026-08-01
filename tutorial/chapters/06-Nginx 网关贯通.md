# 第六章. Nginx 网关贯通

## 6.1 本章目标

​        第 05 章完成之后，项目已经有了前端页面，也能让页面读取后端状态。但这个阶段还有一个明显问题：浏览器访问 UI 时记住的是前端端口，调试 API 时又要记住后端端口。项目小的时候这还能接受，等后面继续加入沙箱、文件访问、SSE、WebSocket 和 VNC，入口就会越来越多，开发和部署都会变得混乱。
​        本章要做的事情，是给 AtlasAgent 加一个统一网关。读者会理解为什么真实系统通常不会把每个服务都直接暴露给浏览器，会学习 Nginx 反向代理的基本工作方式，也会用 Docker Compose 同时启动 Nginx、UI 和 API。完成后，前端页面和后端接口都可以通过同一个端口访问，读者也要能区分宿主机访问地址、Docker Compose 服务名和容器内部端口。这个区分非常重要，很多容器联调问题都不是业务代码错了，而是地址写错了。

## 6.2 最终效果

​        本章结束后，项目会新增一个 Nginx 网关服务。浏览器不再直接访问 UI 容器，也不再直接访问 API 容器，而是统一访问 Nginx 暴露出来的端口。

```Plain
http://localhost:8088
```

​        这个地址会显示第 05 章完成的前端工作台页面。继续访问：

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

## 6.3 本章要解决的问题

​        第 05 章已经完成了前端页面，也能通过 `/api/status` 读取后端状态。但那仍然更像开发阶段的联调方式：UI 有自己的端口，API 也有自己的端口。后续如果再加入沙箱、文件服务、VNC 远程桌面、SSE 事件流和 WebSocket，入口会越来越散。

```Plain
http://localhost:3000       前端页面
http://localhost:8000/api   后端 API
后续还会有沙箱、VNC、文件访问等入口
```

​        真实系统通常会提供一个统一入口。浏览器只访问网关，网关再根据路径把请求转发到不同服务。页面请求走 `/`，API 请求走 `/api`，后续文件、SSE、VNC 也可以继续挂到清晰的路径下。这样用户只需要记住 `http://localhost:8088`，系统内部有几个容器、每个容器监听什么端口，都不应该成为浏览器侧需要关心的事情。

## 6.4 本章技术方案

​        本章选择 Nginx 作为网关。继续直接访问 UI 和 API 各自的端口当然最简单，第 05 章使用的 Next.js rewrite 也能解决前端开发阶段的 API 转发。但这两种方式都不是完整系统的统一入口。Next.js rewrite 更像是前端服务内部的一层便利代理，而 Nginx 才更接近真实部署时摆在最前面的网关。
​        选择 Nginx 的原因很直接：它是非常常见的反向代理组件，可以独立运行在 Docker Compose 中，也方便后续继续扩展 SSE、WebSocket、VNC、静态文件访问和 HTTPS。更重要的是，从这一章开始，浏览器访问路径会更接近真实部署形态。用户打开的是网关地址，服务之间通过 Docker 网络互相访问。
​        本章会新增 `nginx/default.conf`，在 Docker Compose 中加入 `nginx` 服务，把 `/` 代理到 `ui:3000`，把 `/api` 和 `/api/` 代理到 `api:8000`。同时，UI 和 API 不再通过 `ports` 暴露给宿主机，而是使用 `expose` 在 Docker 网络内部开放端口。这样宿主机只需要暴露一个 `8088`，项目入口更干净，也能减少本机端口冲突。
​        本章暂时不配置 HTTPS、不绑定域名、不处理 SSE 长连接，也不处理 WebSocket、VNC 和上传文件静态访问。这些能力都会在后续章节根据真实需要加入。先把最基础的网关链路跑通，读者才能看清 Nginx 在系统里的位置。

## 6.5 新增和修改的文件

​        第 6 章改动的文件集中在网关层和运行编排层。`nginx/default.conf` 是真正的代理规则，`docker-compose.yml` 决定 Nginx、UI 和 API 在容器网络里如何连接，`.env.example` 则记录网关端口和 CORS 来源。读者可以把这一章看成“把已有前后端服务收进统一入口”的章节。

```Plain
.env.example
README.md
docker-compose.yml
nginx/README.md
nginx/default.conf
```

## 6.6 开始前理解：反向代理是什么

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

​        浏览器只知道 Nginx 的地址，不需要知道后面有几个服务，也不需要知道每个服务的真实端口。在本章中，三个地址各有含义：

```Plain
localhost:8088 是宿主机访问 Nginx 的端口
ui:3000        是 Nginx 容器访问 UI 容器的地址
api:8000       是 Nginx 容器访问 API 容器的地址
```

​        `ui` 和 `api` 不是公网域名，也不是本机目录，它们是 Docker Compose 服务名。只要服务在同一个 Docker 网络里，就可以通过服务名互相访问。很多初学者会把容器内访问地址写成 `localhost:3000` 或 `localhost:8000`，这通常会出错，因为容器里的 `localhost` 指向当前容器自己，而不是 Compose 里的其他服务。

## 6.7 实施步骤
### 6.7.1 编写 Nginx 配置

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

### 6.7.2 把 Nginx 加入 Docker Compose

​        接着打开根目录 `docker-compose.yml`，在 `services` 下加入 `nginx`。它是本章唯一暴露给宿主机的服务。

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

​        第 05 章中，UI 和 API 曾经通过 `ports` 暴露给宿主机。本章有了 Nginx 统一入口后，就要把 UI 和 API 改成只在 Docker 网络内开放。UI 服务使用：

```YAML
expose:
  - "3000"
```

​        API 服务使用：

```YAML
expose:
  - "8000"
```

​        `expose` 不会占用宿主机端口，只表示容器网络里的其他服务可以访问这个端口。所以本机即使已经有本地前端服务占用了 `3000`，也不会影响本章的容器启动。这一点正是统一网关带来的实际好处：宿主机端口更少，冲突也更少。
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

​        它表示先创建 UI 和 API，再创建 Nginx。注意，`depends_on` 不等于等待服务完全可用。如果刚启动的一瞬间页面打不开，可以等几秒钟再刷新。后续如果需要更严格的启动约束，可以结合健康检查继续改进，但本章先保持配置简单。

### 6.7.3 确认环境变量

​        第 01 章已经在 `.env.example` 中预留了：

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

### 6.7.4 更新 Nginx 目录说明

​        打开 `nginx/README.md`，写入当前网关规则：

```Plain
/      -> ui:3000
/api   -> api:8000
/api/* -> api:8000
```

​        这份 README 不是运行必需文件，但它能让后续维护时快速知道 Nginx 现在承担哪些职责。随着 SSE、VNC、文件访问和 HTTPS 加入，这个目录会越来越重要。

### 6.7.5 更新环境变量模板

​        打开 `.env.example`，确认保留：

```Plain
NGINX_PORT=8088
UI_API_PROXY_URL=http://api:8000/api/:path*
```

​        第 06 章之后，Docker Compose 默认只把 Nginx 暴露给宿主机，所以不再需要 `UI_PORT` 和 `API_PORT` 控制 UI、API 的宿主机直连端口。同时把 CORS 来源补充为：

```Plain
CORS_ALLOW_ORIGINS=["http://localhost:8088","http://127.0.0.1:8088","http://localhost:3000","http://127.0.0.1:3000"]
```

​        `8088` 是网关访问地址，`3000` 保留给本地前端开发。这样无论通过 Nginx 访问，还是本地直接运行 UI 调试，后端 CORS 都能识别合法来源。

## 6.8 关键理解

​        本章最重要的是理解三种地址：

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

​        所以本章的 API 代理写成：

```Nginx
proxy_pass http://api:8000;
```

​        而不是：

```Nginx
proxy_pass http://api:8000/api/;
```

​        第三个重点是 Nginx 和 Next.js rewrite 的关系。第 05 章的 Next.js rewrite 仍然保留，它用于直接访问 UI 端口时转发 API。本章新增的 Nginx 用于统一入口：

```Plain
浏览器 -> Nginx -> UI
浏览器 -> Nginx -> API
```

​        两者不冲突。后续通过网关访问时，浏览器请求 `/api/status` 会优先被 Nginx 转发到 API，不需要进入 UI 的 rewrite。直接访问 UI 端口做前端开发时，rewrite 仍然可以继续兜住 API 请求。

## 6.9 技术难点与亮点

​        本章的技术难点主要是地址和路径。宿主机端口、容器端口、Compose 服务名、Nginx 代理路径，这几个概念混在一起时很容易出错。`localhost:8088` 是浏览器访问宿主机，`ui:3000` 是 Nginx 容器访问 UI 容器，`api:8000` 是 Nginx 容器访问 API 容器。它们看起来都是地址，但所处网络完全不同。
​        `proxy_pass` 后面是否带路径，也是 Nginx 配置里很容易踩坑的地方。本章故意写成 `proxy_pass http://api:8000;`，就是为了让 `/api/status` 原样进入 FastAPI。如果多拼一段路径，API 收到的路径可能变成不符合预期的形式。
​        本章的项目亮点，是前后端开始拥有统一访问入口。UI 和 API 的真实地址被网关隐藏起来，浏览器只看到一个更接近真实部署的入口。后续 SSE、WebSocket、VNC、文件访问都可以继续在 Nginx 层扩展，而不是让浏览器同时记住一堆端口。

## 6.10 面试考点

​        面试聊到这一章时，常见问题会围绕反向代理和容器网络展开。你需要能解释 Nginx 反向代理和正向代理有什么区别，为什么容器之间不能使用 `localhost` 互相访问，Docker Compose 服务名为什么可以作为网络地址，`proxy_pass http://api:8000;` 和 `proxy_pass http://api:8000/api/;` 在路径处理上有什么不同，以及 `depends_on` 为什么只能控制创建顺序，不能保证服务已经健康。
​        如果能把这些问题讲清楚，说明你不是只会复制一段 Nginx 配置，而是真的理解请求从浏览器进入网关、再进入后端服务的完整路径。

## 6.11 运行验证

​        本章验证要看两条链路：`/api/status` 能不能通过 Nginx 转到 API，`/` 能不能通过 Nginx 转到 UI。下面命令默认在项目根目录执行：

```Bash
pwd
```

​        预期目录类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

### 6.11.1 检查 Compose 配置

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

### 6.11.2 启动服务

​        如果已经完成第 05 章，并且本机已经构建过 API 和 UI 镜像，本章只新增 Nginx 服务，不需要重新构建 API 和 UI。执行：

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

### 6.11.3 验证 API 代理

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

### 6.11.4 验证页面代理

​        再验证页面代理。浏览器访问：

```Plain
http://localhost:8088
```

​        页面应该显示第 05 章完成的工作台，右上角应该显示：

```Plain
API 正常
```

​        如果页面能打开，但 API 显示异常，优先检查：

```Bash
curl http://localhost:8088/api/status
docker compose logs --tail=80 nginx
docker compose logs --tail=80 api
```

### 6.11.5 更换 Nginx 端口

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

## 6.12 常见问题

### 6.12.1 访问 `http://localhost:8088` 提示连接失败怎么办

​        先执行 `docker compose ps`，确认 `atlas-nginx` 是否已经启动，再确认 `8088` 端口是否被占用。如果 Nginx 容器没有启动，浏览器当然连不上；如果宿主机端口被其他程序占用，Compose 也无法把 Nginx 暴露出来。

### 6.12.2 清理端口后仍然访问异常怎么办

​        如果清理端口后仍然访问异常，或者 `docker compose ps` 里 `atlas-nginx` 只显示 `80/tcp`，通常是前一次端口冲突留下的容器没有按新端口映射重建。执行 `docker compose up -d --no-build --force-recreate nginx`，让 Nginx 容器重新应用 Compose 配置。重新执行 `docker compose ps`，应该看到 `0.0.0.0:8088->80/tcp`。

### 6.12.3 提示 `listen tcp 0.0.0.0:3000: bind: address already in use` 怎么办

​        这是宿主机 `3000` 端口已经被其他进程占用。第 06 章之后，UI 服务应该使用 `expose: ["3000"]`，不再使用 `ports: ["3000:3000"]`。先检查 `docker-compose.yml` 是否已经改成 `expose`，再执行 `docker compose up -d --no-build nginx`。如果仍然报错，可以执行 `docker compose config` 查看最终配置里 `ui` 是否还存在 `published: "3000"`。

### 6.12.4 启动时一直卡在 Nginx 镜像拉取怎么办

​        这是 Docker Hub 镜像下载慢或网络超时。可以先单独执行 `docker pull nginx:1.27-alpine`。如果仍然很慢，可以切换网络、配置 Docker 代理，或者稍后重试。配置文件可以先通过 `docker compose config` 检查，等镜像拉取成功后再运行完整验证。

### 6.12.5 构建时 uv 镜像拉取超时怎么办

​        这是 Docker 在构建 API 镜像时，需要从 GitHub Container Registry 拉取 uv 镜像。`TLS handshake timeout` 通常是网络连接超时，不是 Nginx 配置错误。如果第 05 章已经成功构建过 API 和 UI，本章可以先执行 `docker compose up -d --no-build nginx`，避免重新构建 API 镜像。如果本机还没有 API 镜像，可以先单独执行 `docker pull ghcr.io/astral-sh/uv:0.11.15` 验证网络；如果这个命令也超时，可以切换网络、配置 Docker 代理，或者稍后重试。

### 6.12.6 页面正常但 `/api/status` 返回 404 怎么办

​        优先检查 `nginx/default.conf` 中 `proxy_pass` 是否写成了 `http://api:8000;`。如果误加了多余路径，API 收到的路径可能会不符合预期。这个问题通常不是 FastAPI 路由丢了，而是 Nginx 转发后的路径变了。

### 6.12.7 Nginx 日志里出现 `host not found in upstream "api"` 怎么办

​        这说明 Nginx 容器没有在正确的 Docker 网络中，或者 Compose 服务名写错了。检查 `docker-compose.yml` 中 `nginx`、`api` 是否都加入了 `atlas-network`，再确认服务名确实叫 `api`。

### 6.12.8 为什么不再暴露 `3000` 和 `8000` 端口

​        本章已经有 Nginx 统一入口，容器之间可以通过 Docker 网络访问 `ui:3000` 和 `api:8000`。宿主机只暴露 `8088`，可以减少端口冲突，也更接近真实部署方式。开发时如果需要直接运行 UI 或 API，仍然可以在本地单独启动它们。

### 6.12.9 为什么本章不配置 HTTPS

​        HTTPS 需要域名、证书和部署环境配合。本章先完成本地网关链路，生产 Nginx 会在后续章节继续完善。现在如果过早加入证书配置，反而会干扰读者理解反向代理本身。

## 6.13 本章小结

​        本章完成了 AtlasAgent 的统一网关入口。我们新增了 Nginx 配置文件，在 Docker Compose 中加入 Nginx 服务，把 `/` 代理到 UI，把 `/api` 代理到 API，并通过 `http://localhost:8088` 同时验证了前端页面和后端状态接口。与此同时，UI 和 API 从宿主机直连端口改成 Docker 网络内部开放端口，系统入口变得更收敛。
​        从这一章开始，项目具备了更接近真实部署的访问方式。后续新增会话、聊天、文件、SSE、沙箱和 VNC 时，都可以继续围绕这个统一入口扩展。Nginx 不只是多启动了一个容器，它开始承担整个系统入口层的职责。

## 6.14 下一章预告

​        第 07 章会进入数据库、迁移与会话模型，开始把会话数据保存到 PostgreSQL 中。也就是说，项目会从“页面能访问 API”继续推进到“业务数据可以被持久化”。到那时，第 06 章搭好的统一入口仍然会保留，前端和 API 都会继续通过网关协作。
