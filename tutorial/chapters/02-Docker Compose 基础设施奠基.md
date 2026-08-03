# 第二章. Docker Compose 基础设施奠基

**本章目标**

​        学完本章后，你将能够：

​        换句话说，第一，看懂 `docker-compose.yml` 的基本 YAML 层级；第二，使用 Docker Compose 启动 PostgreSQL 和 Redis；第三，理解 `services`、`environment`、`volumes`、`networks`、`healthcheck` 的作用；第四，知道容器之间为什么要通过服务名通信；第五，使用命令验证 PostgreSQL 和 Redis 是否正常运行。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 2.1 最终效果

​        本章结束后，项目根目录会新增 `docker-compose.yml`，并且可以通过一条命令启动两个基础设施服务：

```Plain
postgres  PostgreSQL 业务数据库
redis     Redis 缓存和消息队列基础
```

​        启动后可以看到两个容器：

```Plain
atlas-postgres
atlas-redis
```

​        本章只处理数据库和缓存，不创建 API、UI、Sandbox 或 Nginx 服务。后续章节会在这个基础上继续接入其他服务。

## 2.2 本章要解决的问题

​        AtlasAgent 后面会有会话、任务事件、文件记录、智能体执行状态等数据。这些数据需要稳定保存，所以需要 PostgreSQL。

​        后台任务、状态缓存、事件流这类能力需要一个轻量的内存型服务，所以需要 Redis。

​        如果直接在每台电脑上手动安装 PostgreSQL 和 Redis，版本、端口、账号和数据目录都可能不一样。Docker Compose 可以把这些运行环境写进一份配置文件里，让项目用统一命令启动。

​        本章会完成三件事：

​        从实现顺序看，第一，编写 `docker-compose.yml`；第二，更新 `.env.example` 中的数据库和 Redis 配置；第三，用 Docker Compose 命令检查和启动服务。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

## 2.3 本章技术方案

​        本章选择用 Docker Compose 管理 PostgreSQL 和 Redis。

​        可选方案有三种：

​        放到工程语境里看，第一，直接在电脑上安装 PostgreSQL 和 Redis；第二，使用云数据库和云 Redis；第三，使用 Docker Compose 在本机启动容器。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本项目选择第三种。原因是开发阶段更需要稳定、可复现的环境。只要本机安装了 Docker，不同电脑就可以用同一份 `docker-compose.yml` 启动相同版本的 PostgreSQL 和 Redis。

​        本章暂时不把 API、UI、Sandbox 和 Nginx 加进 Compose。这样可以先把基础设施讲清楚，避免数据库、缓存、后端框架和前端框架同时出现。

​        本章的 Compose 设计包含四个重点：

​        展开来看，第一，使用 `services` 定义 `postgres` 和 `redis` 两个服务；第二，使用 `volumes` 保存数据库和 Redis 数据；第三，使用 `networks` 创建统一的容器网络；第四，使用 `healthcheck` 判断服务是否真正可用。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        第 3 章会在这个基础上加入 FastAPI 服务，并让 API 容器和数据库、Redis 处在同一个网络里。

## 2.4 新增和修改的文件

```Plain
docker-compose.yml
.env.example
README.md
```

## 2.5 开始前检查：确认 Docker 可用

​        本章第一次使用 Docker 和 Docker Compose。Docker 负责运行容器，Docker Compose 负责按照 `docker-compose.yml` 同时管理多个容器。

​        先在终端执行：

```Bash
docker --version
```

​        正常情况下会看到类似输出：

```Plain
Docker version 27.0.0, build ...
```

​        继续执行：

```Bash
docker compose version
```

​        正常情况下会看到类似输出：

```Plain
Docker Compose version v2.29.0
```

​        如果提示 `command not found`，说明本机还没有安装 Docker，先安装 Docker Desktop。

​        如果能看到版本号，但后面启动服务时报错，需要确认 Docker Desktop 已经打开，并且 Docker Engine 正在运行。

## 2.6 实施步骤

### 2.6.1 理解 YAML 的缩进规则

​        `docker-compose.yml` 使用 YAML 格式。YAML 最重要的规则是：用缩进表示层级。

​        先看一个最小例子：

```YAML
services:
  postgres:
    image: postgres:16-alpine
```

​        它的层级关系是：

```Plain
services
└── postgres
    └── image = postgres:16-alpine
```

​        这里有三层：

​        具体来说，第一，`services` 是第一层，表示所有服务都写在这里；第二，`postgres` 是第二层，表示其中一个服务叫 `postgres`；第三，`image` 是第三层，表示这个服务使用哪个 Docker 镜像。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        写 YAML 时注意这几点：

​        换句话说，第一，同一层级缩进必须一致；第二，本项目统一使用两个空格缩进；第三，不要用 Tab 缩进；第四，`key: value` 表示一个配置项；第五，`- item` 表示列表项。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        例如：

```YAML
networks:
  - atlas-network
```

​        这里的 `- atlas-network` 表示 `networks` 下面有一个列表项。

​        再看一个容易写错的例子：

```YAML
services:
  postgres:
  image: postgres:16-alpine
```

​        这段是错的。`image` 和 `postgres` 缩进一样，Docker Compose 会认为它们是同一层。正确写法应该是：

```YAML
services:
  postgres:
    image: postgres:16-alpine
```

​        后面写 Compose 文件时，优先检查缩进。

### 2.6.2 创建 Compose 文件的顶层结构

​        在项目根目录创建 `docker-compose.yml`。

​        项目根目录指包含 `README.md`、`.env.example`、`backend/api/`、`frontend/web/` 的目录。本项目中路径类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

​        先写入三个顶层字段：

```YAML
services:

volumes:

networks:
```

​        这三个字段的作用分别是：

​        从实现顺序看，第一，`services`：定义要启动的容器服务；第二，`volumes`：定义要持久保存的数据卷；第三，`networks`：定义容器之间通信使用的网络。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本章会在 `services` 里放入 `postgres` 和 `redis` 两个服务。

​        此时先不用运行命令，因为文件还没有写完。

### 2.6.3 编写 PostgreSQL 服务基础配置

​        先在 `services` 下面添加 `postgres` 服务：

```YAML
services:
  postgres:
    image: postgres:16-alpine
    container_name: atlas-postgres
    restart: unless-stopped
```

​        这段代码要放在 `docker-compose.yml` 的 `services:` 下面。

​        每一行的含义是：

​        放到工程语境里看，第一，`postgres`：Compose 服务名。后续其他容器连接数据库时，会使用这个名字；第二，`image`：指定 Docker 镜像，这里使用 PostgreSQL 16 的 Alpine 轻量版本；第三，`container_name`：指定容器名称，方便执行 `docker ps` 或查看日志；第四，`restart`：重启策略。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        `restart: unless-stopped` 表示：除非手动停止，否则容器异常退出后 Docker 会尝试重新启动。

​        这一段写完后，先检查缩进是否是下面这样：

```Plain
services:
  postgres:
    image:
    container_name:
    restart:
```

​        `image`、`container_name`、`restart` 必须比 `postgres` 多缩进两个空格。

### 2.6.4 配置 PostgreSQL 的账号和数据库

​        PostgreSQL 第一次启动时，需要创建默认用户、密码和数据库。

​        继续在 `postgres` 服务下面添加 `environment`：

```YAML
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-atlas_agents}
```

​        注意这段代码要和 `image`、`container_name`、`restart` 保持同一层级。

​        缩进关系是：

```Plain
services
  postgres
    environment
      POSTGRES_USER
      POSTGRES_PASSWORD
      POSTGRES_DB
```

​        `${POSTGRES_USER:-postgres}` 是 Docker Compose 支持的环境变量写法。

​        它表示：

​        展开来看，第一，如果当前环境或 `.env` 文件里有 `POSTGRES_USER`，就使用那个值；第二，如果没有，就使用默认值 `postgres`。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        所以这份配置在本地可以直接运行，也可以在部署时通过环境变量覆盖。

​        这里的三个变量会被 PostgreSQL 镜像识别：

​        具体来说，第一，`POSTGRES_USER`：默认用户名；第二，`POSTGRES_PASSWORD`：默认密码；第三，`POSTGRES_DB`：默认创建的数据库名。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        本项目默认数据库名使用 `atlas_agents`。

### 2.6.5 为 PostgreSQL 添加数据卷

​        容器可以删除和重建，但数据库里的数据不能跟着丢。

​        继续在 `postgres` 服务下面添加 `volumes`：

```YAML
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

​        这行挂载规则的格式是：

```Plain
数据卷名称:容器内目录
```

​        对应到本章就是：

```Plain
postgres_data -> /var/lib/postgresql/data
```

​        `/var/lib/postgresql/data` 是 PostgreSQL 在容器里保存数据文件的位置。挂载到 `postgres_data` 后，即使删除并重建 `atlas-postgres` 容器，数据库数据仍然会保留在 Docker 数据卷里。

​        后面还需要在文件底部声明这个数据卷：

```YAML
volumes:
  postgres_data:
```

​        先记住一点：服务里使用过的数据卷，通常要在顶层 `volumes` 里声明。

### 2.6.6 为 PostgreSQL 添加网络

​        后续 API 服务也会运行在容器里。API 容器不能用 `localhost` 连接 PostgreSQL，因为容器里的 `localhost` 指向当前容器自己。

​        更稳定的方式是把服务放到同一个 Docker 网络里，然后通过服务名访问。

​        继续在 `postgres` 服务下面添加：

```YAML
    networks:
      - atlas-network
```

​        这表示 `postgres` 服务会加入 `atlas-network` 网络。

​        后续 API 容器也加入这个网络后，就可以用下面的主机名连接数据库：

```Plain
postgres
```

### 2.6.7 为 PostgreSQL 添加健康检查

​        容器启动不代表数据库已经能接受连接。PostgreSQL 启动时需要初始化数据目录，这个过程可能需要几秒钟。

​        继续在 `postgres` 服务下面添加 `healthcheck`：

```YAML
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-atlas_agents}"]
      interval: 10s
      timeout: 5s
      retries: 5
```

​        `pg_isready` 是 PostgreSQL 自带的连接检查命令。

​        这几行配置表示：

​        换句话说，第一，`test`：执行什么命令来判断服务是否健康；第二，`interval: 10s`：每 10 秒检查一次；第三，`timeout: 5s`：每次检查最多等待 5 秒；第四，`retries: 5`：连续失败 5 次后认为服务不健康。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        后续接入 API 服务时，可以通过健康状态判断数据库是否已经准备好。

​        到这里，`postgres` 服务已经写完。

### 2.6.8 编写 Redis 服务基础配置

​        接下来在 `services` 下添加第二个服务 `redis`。

​        注意：`redis` 和 `postgres` 是同一层级，所以它们缩进一样。

```YAML
  redis:
    image: redis:7-alpine
    container_name: atlas-redis
    restart: unless-stopped
```

​        这段代码仍然放在 `services:` 下面，但不要写进 `postgres` 服务里。

​        正确层级应该是：

```Plain
services
  postgres
    ...
  redis
    image
    container_name
    restart
```

​        Redis 使用 `redis:7-alpine` 镜像。它体积小，启动快，适合开发环境。

### 2.6.9 为 Redis 添加启动参数

​        Redis 默认可以直接启动，但本项目希望它具备基本持久化能力，并限制开发环境的内存使用。

​        继续在 `redis` 服务下面添加：

```YAML
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
```

​        `command` 用来覆盖容器默认启动命令。

​        这里的 `>` 是 YAML 的多行字符串写法。它会把下面多行合并成一条命令，等价于：

```Plain
redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

​        三个参数的含义是：

​        从实现顺序看，第一，`--appendonly yes`：开启 AOF 持久化，让 Redis 写入操作保存到磁盘；第二，`--maxmemory 256mb`：限制 Redis 最多使用 256MB 内存；第三，`--maxmemory-policy allkeys-lru`：内存不足时，优先淘汰较少使用的 key。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

​        开发环境不需要让 Redis 无限占用内存，所以这里先给一个保守配置。

### 2.6.10 为 Redis 添加数据卷、网络和健康检查

​        Redis 的数据目录是 `/data`，所以给它添加数据卷：

```YAML
    volumes:
      - redis_data:/data
```

​        Redis 也要加入同一个网络：

```YAML
    networks:
      - atlas-network
```

​        然后添加健康检查：

```YAML
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

​        `redis-cli ping` 是 Redis 最简单的健康检查命令。正常情况下会返回：

```Plain
PONG
```

​        如果健康检查一直失败，优先查看 Redis 日志。

### 2.6.11 声明数据卷和网络

​        前面的服务已经使用了两个数据卷：

```Plain
postgres_data
redis_data
```

​        也使用了一个网络：

```Plain
atlas-network
```

​        所以需要在文件底部补全顶层 `volumes` 和 `networks`：

```YAML
volumes:
  postgres_data:
  redis_data:

networks:
  atlas-network:
    name: atlas-network
    driver: bridge
```

​        这里的 `driver: bridge` 表示使用 Docker 默认的桥接网络。

​        后续其他服务也会加入 `atlas-network`。只要在同一个网络里，服务之间就可以通过 Compose 服务名访问：

```Plain
postgres
redis
```

​        不要在容器之间使用 `localhost` 表示其他服务。

### 2.6.12 对照完整的 `docker-compose.yml`

​        完成后的 `docker-compose.yml` 应该是下面这样：

```YAML
services:
  postgres:
    image: postgres:16-alpine
    container_name: atlas-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-atlas_agents}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - atlas-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-atlas_agents}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: atlas-redis
    restart: unless-stopped
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - atlas-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:

networks:
  atlas-network:
    name: atlas-network
    driver: bridge
```

​        对照时重点看三件事：

​        放到工程语境里看，第一，`postgres` 和 `redis` 是否都在 `services` 下面；第二，`postgres_data` 和 `redis_data` 是否都在文件底部声明；第三，`atlas-network` 是否在服务里使用，并在文件底部声明。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

### 2.6.13 更新环境变量模板

​        打开 `.env.example`，确认数据库和 Redis 配置如下：

```Plain
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=atlas_agents

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

​        `.env.example` 是环境变量模板，可以提交到仓库。

​        真实项目中常见做法是再创建一个 `.env` 文件，填写本机或服务器的真实配置。但 `.env` 可能包含密码和密钥，不应该提交。

​        本章的 `docker-compose.yml` 已经给 PostgreSQL 设置了默认值，所以即使没有 `.env` 文件，也可以直接运行。

## 2.7 关键理解

​        本章最重要的是理解服务边界，而不是背配置字段。

​        PostgreSQL 负责持久化业务数据。后续会话、事件、文件记录都会写入数据库。

​        Redis 负责缓存和消息流基础能力。后续后台任务和事件推送会用到它。

​        Docker Volume 负责保存容器生命周期之外的数据。容器可以删，数据卷里的数据还在。

​        Docker Network 负责让容器之间通信。后续 API 连接数据库时，主机名会使用 `postgres`，不是 `localhost`。

​        Healthcheck 负责告诉 Docker 当前服务是否真的可用。容器启动和服务可用不是同一件事。

## 2.8 运行验证

​        下面所有命令都在项目根目录执行，也就是包含 `docker-compose.yml` 的目录。

​        先确认当前目录：

```Bash
pwd
```

​        预期输出类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

​        如果当前目录不对，先进入项目目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 2.8.1 检查 Compose 配置

​        执行：

```Bash
docker compose config
```

​        这个命令只检查配置，不会启动容器。

​        正常情况下会输出展开后的 Compose 配置。输出里应该能看到类似内容：

```Plain
services:
  postgres:
    container_name: atlas-postgres
    image: postgres:16-alpine
  redis:
    container_name: atlas-redis
    image: redis:7-alpine
networks:
  atlas-network:
volumes:
  postgres_data:
  redis_data:
```

​        如果这里报错，通常是 YAML 缩进、冒号或列表写法有问题。先回到 `docker-compose.yml` 检查缩进。

### 2.8.2 启动 PostgreSQL 和 Redis

​        执行：

```Bash
docker compose up -d
```

​        `-d` 表示后台运行。

​        第一次执行时，Docker 可能会拉取镜像，输出里可能出现：

```Plain
Pulling postgres ...
Pulling redis ...
Creating network atlas-network ...
Creating volume atlas-agents_postgres_data ...
Creating volume atlas-agents_redis_data ...
Creating atlas-postgres ...
Creating atlas-redis ...
```

​        如果本机已经有镜像，拉取步骤可能不会出现。

​        如果拉取镜像很慢，通常是网络原因，不一定是配置写错。

### 2.8.3 查看容器状态

​        执行：

```Bash
docker compose ps
```

​        预期能看到类似输出：

```Plain
NAME             IMAGE                STATUS
atlas-postgres   postgres:16-alpine   Up ... (healthy)
atlas-redis      redis:7-alpine       Up ... (healthy)
```

​        刚启动时可能看到 `starting`，这是健康检查还没通过。等几秒后再执行一次。

​        如果一直不是 `healthy`，继续看日志。

### 2.8.4 验证 Redis

​        执行：

```Bash
docker compose exec redis redis-cli ping
```

​        预期输出：

```Plain
PONG
```

​        看到 `PONG`，说明 Redis 可以正常响应命令。

### 2.8.5 验证 PostgreSQL

​        执行：

```Bash
docker compose exec postgres pg_isready -U postgres -d atlas_agents
```

​        预期输出类似：

```Plain
/var/run/postgresql:5432 - accepting connections
```

​        看到 `accepting connections`，说明 PostgreSQL 已经可以接收连接。

### 2.8.6 查看日志

​        查看 PostgreSQL 日志：

```Bash
docker compose logs postgres
```

​        查看 Redis 日志：

```Bash
docker compose logs redis
```

​        如果想持续观察日志，可以加 `-f`：

```Bash
docker compose logs -f redis
```

​        日志里如果出现端口、权限、配置解析相关错误，优先检查 `docker-compose.yml` 和 `.env`。

### 2.8.7 停止服务

​        停止并删除容器：

```Bash
docker compose down
```

​        这会删除容器和默认网络，但不会删除数据卷。

​        如果需要连数据卷一起删除，可以执行：

```Bash
docker compose down -v
```

​        注意：`-v` 会删除数据库和 Redis 的持久化数据。平时不要随手使用。

## 2.9 本章小结

​        本章完成了 AtlasAgent 的第一层运行基础：

​        展开来看，第一，添加了 `docker-compose.yml`；第二，配置了 PostgreSQL 和 Redis；第三，配置了 Docker 数据卷和网络；第四，学会了 Compose 文件的基本 YAML 层级；第五，使用命令验证了 Redis 和 PostgreSQL 的可用性；第六，为后续 API 服务连接数据库和 Redis 做好了准备。这些点放在一起看，构成了本章叙述中需要连续理解的一条线索，而不是彼此孤立的项目清单。

---

[← 第一章. 项目伊始](01-项目伊始.md) · [返回目录](../README.md) · [第三章. 后端 API 与通用模块奠基 →](03-后端%20API%20与通用模块奠基.md)
