# 第六十七章. Docker 私有化部署与内网交付

## 67.1 本章目标

​        完成本章后，你将能够：

​        放到工程语境里看，第一，理解第 46 章和私有化部署的区别；第二，在服务器上准备 AtlasAgent 运行环境；第三，构建并标记 API、UI、Sandbox 镜像；第四，把镜像推送到私有镜像仓库；第五，在目标服务器拉取镜像并启动服务；第六，初始化数据库、上传目录和运行时配置；第七，验证 Nginx 网关、API、Sandbox、VNC 和前端页面；第八，理解升级、回滚、备份和常见故障排查路径。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 67.2 最终效果

​        本章结束后，你可以把 AtlasAgent 从本机开发环境交付到一台内网服务器或私有服务器。

​        交付形态如下：

```Plain
开发机
  |
  | docker build / docker tag / docker push
  v
私有镜像仓库
  |
  | docker pull
  v
部署服务器
  |
  +-- Nginx
  +-- UI
  +-- API
  +-- Sandbox
  +-- PostgreSQL
  +-- Redis
  +-- 数据卷
```

​        部署完成后，用户访问：

```Plain
http://服务器IP:8088
```

​        即可打开 AtlasAgent 工作台。

## 67.3 本章和第 46 章的区别

​        第 46 章解决的是：

```Plain
在当前开发机上，用 Docker Compose 更稳定地启动完整项目。
```

​        本章解决的是：

```Plain
把项目作为一个可交付系统，部署到另一台服务器或内网环境。
```

​        两者重点不同：

```Plain
第 46 章：本地生产化启动
第 67 章：私有化部署交付
```

​        本章会额外关注：

​        展开来看，第一，私有镜像仓库；第二，服务器 `.env` 配置；第三，数据卷初始化；第四，runtime-config 初始化；第五，镜像版本标记；第六，升级和回滚；第七，备份和恢复；第八，内网环境常见问题。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 67.4 本章要解决的问题

​        课程项目在本机能跑，不代表可以直接交付给别人使用。

​        真实私有化部署经常会遇到这些问题：

​        具体来说，第一，服务器不能访问 GitHub Container Registry；第二，服务器不能直接拉 Docker Hub 镜像；第三，`.env` 没有按服务器环境配置；第四，数据库卷是空的，还没有迁移；第五，`runtime-config` 卷是空的，API 找不到 `llm.yaml`、`mcp.yaml`、`a2a.yaml`；第六，Nginx 已启动，但 API 还没健康，页面出现 502；第七，Sandbox 镜像很大，构建和拉取都慢；第八，升级后想回滚，但没有镜像版本和数据备份。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章把这些问题整理成一套可执行流程。

## 67.5 本章技术方案

​        本章使用 Docker Compose 做单机私有化部署。

​        整体流程是：

```Plain
1. 开发机构建镜像
2. 镜像打 tag
3. 推送到私有镜像仓库
4. 服务器准备 .env
5. 服务器拉取镜像
6. 初始化 runtime-config
7. 启动服务
8. 执行数据库迁移
9. 验证访问入口
10. 记录备份、升级和回滚方法
```

​        本章暂时不做这些内容：

​        换句话说，第一，不做 Kubernetes 部署；第二，不做 Helm Chart；第三，不做多节点高可用；第四，不做云厂商托管数据库；第五，不做完整权限、审计和计费系统。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些属于生产平台化阶段。本章目标是让项目具备清晰的 Docker 私有化交付路径。

## 67.6 新增和修改的文件

```Plain
docs/course/chapters/67-docker-private-deployment.md
docs/course/outline.md
docs/course/branch-plan.md
docs/course/coverage-matrix.md
scripts/seed-runtime-config.sh
```

## 67.7 实施步骤
### 67.7.1 准备服务器

​        部署服务器至少需要安装：

```Plain
Docker
Docker Compose Plugin
```

​        在服务器上检查：

```Bash
docker version
docker compose version
```

​        建议服务器配置：

```Plain
CPU：至少 4 核
内存：至少 8 GB
磁盘：至少 50 GB 可用空间
系统：Linux x86_64 或 arm64
```

​        如果要运行 Sandbox、Playwright、VNC 和浏览器截图，内存越充足越好。

### 67.7.2 准备生产环境变量

​        在服务器项目目录中准备 `.env`。

​        可以从 `.env.example` 复制：

```Bash
cp .env.example .env
```

​        重点检查这些变量：

```Plain
NGINX_PORT=8088
API_ENV=production
DATABASE_URL=postgresql+asyncpg://postgres:强密码@postgres:5432/atlas_agents
REDIS_URL=redis://redis:6379/0
LLM_API_KEY=你的模型密钥
BING_SEARCH_API_KEY=可选的 Bing 官方 API Key
```

​        生产环境不要继续使用默认数据库密码。

​        如果暂时只是内网演示，可以先保留 `8088` 端口；如果要绑定域名和 HTTPS，需要在 Nginx 外层继续接入证书、负载均衡或网关。

### 67.7.3 构建镜像

​        在开发机项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build api ui sandbox
```

​        如果 Sandbox 改动较大，建议单独构建并显示详细日志：

```Bash
docker compose build --progress=plain sandbox
```

#### 67.7.3.1 为什么 Sandbox 构建更慢

​        Sandbox 镜像需要安装：

​        从实现顺序看，第一，Python 依赖；第二，Playwright；第三，Chromium；第四，Xvfb；第五，x11vnc；第六，websockify。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        这些内容比普通 API 镜像大很多。

​        如果网络不稳定，优先确认 Docker 能访问基础镜像源、Python 包源和系统 apt 源。

### 67.7.4 给镜像打版本 tag

​        假设你的私有镜像仓库地址是：

```Plain
registry.example.com/atlas-agents
```

​        版本号使用：

```Plain
v1.0.0
```

​        给镜像打 tag：

```Bash
docker tag atlas-agents-api registry.example.com/atlas-agents/api:v1.0.0
docker tag atlas-agents-ui registry.example.com/atlas-agents/ui:v1.0.0
docker tag atlas-agents-sandbox registry.example.com/atlas-agents/sandbox:v1.0.0
```

#### 67.7.4.1 为什么要打版本 tag

​        不要只使用 `latest`。

​        `latest` 看起来方便，但出了问题很难知道当前服务器跑的是哪一版。

​        使用明确版本号后：

```Plain
升级：从 v1.0.0 切到 v1.1.0
回滚：从 v1.1.0 切回 v1.0.0
```

​        排查问题会清晰很多。

### 67.7.5 推送到私有镜像仓库

​        登录镜像仓库：

```Bash
docker login registry.example.com
```

​        推送镜像：

```Bash
docker push registry.example.com/atlas-agents/api:v1.0.0
docker push registry.example.com/atlas-agents/ui:v1.0.0
docker push registry.example.com/atlas-agents/sandbox:v1.0.0
```

​        如果服务器不能访问 Docker Hub 或 GitHub Container Registry，私有镜像仓库就是最稳的交付方式。

### 67.7.6 在服务器使用镜像

​        服务器上的 Compose 文件可以继续使用 `build`，也可以改成 `image`。

​        私有化部署推荐使用 `image`：

```YAML
services:
  api:
    image: registry.example.com/atlas-agents/api:v1.0.0

  ui:
    image: registry.example.com/atlas-agents/ui:v1.0.0

  sandbox:
    image: registry.example.com/atlas-agents/sandbox:v1.0.0
```

​        这样服务器启动时只需要拉镜像，不需要现场构建。

​        如果你希望课程代码仍然保留 `build` 形式，也可以在服务器上临时使用：

```Bash
docker compose pull
docker compose up -d
```

​        核心原则是：生产服务器尽量不要依赖源码构建成功，应该尽量依赖已经验证过的镜像。

### 67.7.7 初始化 runtime-config

​        API 默认从容器内读取：

```Plain
/app/runtime-config/llm.yaml
/app/runtime-config/mcp.yaml
/app/runtime-config/a2a.yaml
```

​        这些文件挂在 Docker volume 中：

```Plain
api_runtime_config
```

​        如果这个 volume 是空的，API 会因为找不到配置文件而启动失败。

​        本章新增脚本：

```Bash
./scripts/seed-runtime-config.sh
```

​        执行：

```Bash
cd /opt/atlas-agents
./scripts/seed-runtime-config.sh
```

​        脚本会把 `api/config` 下的默认配置复制到 `api_runtime_config` 卷中。

​        默认不会覆盖已有文件。如果你确认要重新覆盖，可以执行：

```Bash
OVERWRITE=true ./scripts/seed-runtime-config.sh
```

​        如果你的 Compose 项目名不是默认的 `atlas-agents`，可以显式传入：

```Bash
COMPOSE_PROJECT_NAME=your-project ./scripts/seed-runtime-config.sh
```

​        如果你已经知道运行时配置卷的完整名称，也可以直接指定：

```Bash
RUNTIME_CONFIG_VOLUME=your-project_api_runtime_config ./scripts/seed-runtime-config.sh
```

#### 67.7.7.1 为什么要单独初始化 runtime-config

​        第 62 章已经让页面配置可以写入后端运行时配置。

​        这意味着 `runtime-config` 不再只是镜像里的静态文件，而是部署后的可变配置数据。

​        所以它应该放在 volume 中持久化，而不是每次容器重建都丢失。

### 67.7.8 启动服务

​        在服务器项目根目录执行：

```Bash
docker compose up -d
```

​        查看状态：

```Bash
docker compose ps
```

​        如果是第一次启动，也可以使用项目脚本：

```Bash
BUILD=false ./scripts/start.sh
```

​        如果 API 健康检查失败，优先看日志：

```Bash
docker compose logs --tail=120 api
```

​        常见原因是：

​        放到工程语境里看，第一，`LLM_API_KEY` 未配置；第二，`runtime-config` 没初始化；第三，数据库连接失败；第四，迁移失败。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 67.7.9 执行数据库迁移

​        如果 API 启动脚本已经设置：

```Plain
RUN_MIGRATIONS=true
```

​        容器启动时会自动执行迁移。

​        也可以手动执行：

```Bash
docker compose exec api uv run alembic upgrade head
```

​        检查数据库状态：

```Bash
curl http://服务器IP:8088/api/status/database
```

### 67.7.10 验证访问入口

​        基础接口：

```Bash
curl http://服务器IP:8088/api/status
curl http://服务器IP:8088/api/status/database
curl http://服务器IP:8088/sandbox-api/status
```

​        配置中心：

```Bash
curl http://服务器IP:8088/api/config/llm
curl http://服务器IP:8088/api/mcp/tools
curl http://服务器IP:8088/api/a2a/agents
```

​        最终验收：

```Bash
curl http://服务器IP:8088/api/acceptance/checks
```

​        页面访问：

```Plain
http://服务器IP:8088
```

​        预期：

​        展开来看，第一，页面可以打开；第二，可以创建会话；第三，可以发送任务；第四，可以看到计划、步骤、工具详情和最终回答；第五，设置页能看到 LLM、Search、MCP、A2A、多 Agent 和 Sandbox 配置。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 67.7.11 备份数据

​        至少需要备份：

```Plain
PostgreSQL 数据
api_uploads 卷
api_runtime_config 卷
```

​        备份数据库：

```Bash
docker compose exec postgres pg_dump -U postgres atlas_agents > backup-atlas-agents.sql
```

​        备份上传文件：

```Bash
docker run --rm \
  -v atlas-agents_api_uploads:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine \
  tar czf /backup/api_uploads.tar.gz -C /data .
```

​        备份运行时配置：

```Bash
docker run --rm \
  -v atlas-agents_api_runtime_config:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine \
  tar czf /backup/api_runtime_config.tar.gz -C /data .
```

### 67.7.12 升级和回滚

​        升级流程：

```Bash
docker compose pull
docker compose up -d
docker compose exec api uv run alembic upgrade head
docker compose ps
```

​        回滚流程：

```Plain
1. 把 Compose 中的镜像 tag 改回上一版。
2. docker compose pull
3. docker compose up -d
4. 验证 API、页面和核心任务。
```

​        如果新版本执行了不可逆数据库迁移，回滚前必须确认数据库备份可用。

## 67.8 关键理解

​        私有化部署的重点不是“能不能在服务器上 docker compose up”。

​        真正重要的是：

​        具体来说，第一，镜像来源可控；第二，配置可持久化；第三，数据可备份；第四，升级可回滚；第五，故障能定位。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        AtlasAgent 里最容易被忽略的是 `runtime-config`。

​        第 62 章之后，LLM、MCP、A2A 等配置可以通过页面写入运行时配置。如果部署时只关注数据库和上传文件，却忘记 runtime-config，就会出现容器重建后配置丢失或 API 启动失败。

## 67.9 技术难点与亮点

​        技术难点：

​        换句话说，第一，Sandbox 镜像包含浏览器和 VNC 依赖，构建和分发成本更高；第二，私有化部署需要处理镜像、配置、数据卷、迁移和网关；第三，运行时配置既要有默认值，又不能覆盖用户已经保存的配置；第四，回滚不仅是镜像回滚，还要考虑数据库迁移和数据兼容。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        项目亮点：

​        从实现顺序看，第一，使用 Docker Compose 即可完成单机私有化部署；第二，Nginx 统一代理 UI、API、SSE、WebSocket、上传文件和 VNC；第三，`runtime-config` 独立持久化，支持页面配置 LLM、MCP 和 A2A；第四，最终验收清单可以部署后直接执行，方便交付自查。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 67.10 运行验证

​        下面命令默认在项目根目录执行。

### 67.10.1 检查脚本

```Bash
bash -n scripts/seed-runtime-config.sh
```

### 67.10.2 初始化 runtime-config

```Bash
./scripts/seed-runtime-config.sh
```

​        预期输出中能看到：

```Plain
llm.yaml
mcp.yaml
a2a.yaml
```

### 67.10.3 启动服务

```Bash
docker compose up -d
docker compose ps
```

### 67.10.4 验证接口

```Bash
curl http://localhost:8088/api/status
curl http://localhost:8088/api/status/database
curl http://localhost:8088/sandbox-api/status
curl http://localhost:8088/api/acceptance/checks
```

### 67.10.5 验证页面

​        访问：

```Plain
http://localhost:8088
```

​        创建会话并发送任务：

```Plain
搜索最近 AI Agent 领域的热门动态，整理 5 条来源，并给出总结。
```

​        预期：

​        放到工程语境里看，第一，页面自动规划并执行；第二，搜索工具节点可点击；第三，右侧抽屉展示工具详情；第四，最终回答包含总结和引用。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 67.11 常见问题

- 问题：API 容器一直 unhealthy 怎么办？

​        解释：先看 `docker compose logs --tail=120 api`。如果日志里提示找不到 `runtime-config/llm.yaml`、`mcp.yaml` 或 `a2a.yaml`，执行 `./scripts/seed-runtime-config.sh` 后重启 API。

- 问题：服务器不能拉 `ghcr.io/astral-sh/uv` 怎么办？

​        解释：私有化部署推荐在开发机或 CI 构建好镜像，再推送到私有镜像仓库。服务器只拉你的私有镜像，不再现场访问 GHCR。

- 问题：页面打开是 502 怎么办？

​        解释：Nginx 已启动但后端未健康。执行 `docker compose ps`，检查 `api`、`ui`、`sandbox` 是否 healthy，再看对应日志。

- 问题：升级后配置丢失怎么办？

​        解释：检查是否误删了 `api_runtime_config` volume。配置中心保存的是运行时配置，不应该随着容器重建删除。

- 问题：要不要把 PostgreSQL 换成外部数据库？

​        解释：可以。把 `.env` 中的 `DATABASE_URL` 改成外部数据库地址，并确认网络、防火墙和迁移权限即可。

## 67.12 本章小结

​        本章把 AtlasAgent 从“课程项目能跑”推进到“可以私有化交付”：

​        展开来看，第一，梳理了开发机、私有镜像仓库和部署服务器之间的交付链路；第二，说明了镜像构建、打 tag、推送、拉取和启动流程；第三，补齐了 runtime-config 初始化脚本；第四，讲清楚数据卷、备份、升级和回滚；第五，给出了部署后的接口和页面验收方法。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        到这里，AtlasAgent 不仅有完整 Agent 功能和前端体验，也具备了更清晰的私有化部署交付路径。
