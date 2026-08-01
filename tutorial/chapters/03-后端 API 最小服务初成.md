# 第三章. 后端 API 最小服务初成

## 3.1 本章目标

​        从这一章开始，项目不再只是目录和基础设施，而是第一次拥有一个真正能被访问的后端入口。笔者希望读者在这一章里先建立一种工程直觉：一个后端服务并不是从复杂业务开始的，它首先要能稳定启动，要能读到自己的配置，要能把路由挂到统一入口下面，还要能提供一个最小但可靠的状态检查接口。只有这个入口站稳了，后面的数据库、会话、流式事件、Agent 调度和工具系统才有地方接入。

​        本章的目标不是一次性把 API 做完整，而是把 FastAPI 服务的骨架搭出来。你会看到 `create_app()` 如何创建应用，`api_router` 如何成为所有业务路由的汇总入口，`StatusResponse` 如何约束接口返回结构，以及 `/api/status` 如何把配置里的服务名、环境名和版本号返回给调用方。读完这一章后，读者应该能说清楚一个最小 API 服务从配置、应用入口、路由注册到接口响应之间的完整链路。

## 3.2 最终效果

​        本章结束后，项目会新增一个可以运行的后端 API 服务。

​        本地启动后访问：

```Plain
http://localhost:8000/api/status
```

​        预期返回：

```JSON
{
  "service": "AtlasAgent API",
  "environment": "development",
  "status": "ok",
  "version": "0.1.0"
}
```

​        使用 Docker Compose 启动后，会看到三个服务：

```Plain
atlas-api
atlas-postgres
atlas-redis
```

​        这里需要注意一个边界：本章虽然已经把 `api` 服务放进了 Docker Compose，并且让它和 `postgres`、`redis` 处在同一个 Docker 网络中，但 API 暂时不会主动连接这两个服务。第 02 章准备的是基础设施，第 03 章要做的是应用入口。笔者刻意把这两件事拆开，是为了让读者先看清“服务能跑起来”这件事本身，避免一开始就被数据库连接、迁移、异常处理和跨域配置混在一起。

## 3.3 本章要解决的问题

​        第 02 章已经准备好了 PostgreSQL、Redis、Docker 网络和数据卷。现在项目有了基础设施，但还没有任何对外提供能力的后端服务。

​        这会带来一个问题：后续前端、任务系统、Agent 执行器都需要通过 API 和系统交互。如果没有一个最小 API 入口，后面的功能就没有统一接入点。

​        所以本章先实现一个很小的后端闭环：

```Plain
浏览器或 curl
  |
  v
FastAPI
  |
  v
/api/status
```

​        这个接口暂时不做复杂业务，只回答一个问题：后端服务是否正常运行。

## 3.4 本章技术方案

​        本章选择 FastAPI 作为后端框架。

​        如果只是为了返回一个 JSON，Python 标准库或者 Flask 都能完成任务。但 AtlasAgent 后续不是一个普通的 CRUD 服务，它要持续推送 Agent 执行事件，要查询后台任务状态，要调用 Sandbox、浏览器、Shell、搜索和 MCP 等外部能力，还会在前端保持长时间的交互状态。FastAPI 对异步接口、Pydantic 数据模型和接口文档的支持比较自然，用它作为后端入口，后面扩展 SSE、后台任务和工具调用时会更顺。

​        这一章的技术方案可以理解为四层小闭环。最底层是配置模块，`Settings` 从环境变量和 `.env` 中读取服务名、环境名、版本号和 API 前缀。再往上是应用入口，`create_app()` 创建 FastAPI 实例，并把统一路由挂到 `settings.api_prefix` 下面。第三层是路由，`api_router` 汇总具体业务路由，当前只挂载 `status.router`。最外层是 Docker Compose，它负责把 API 构建成容器，并通过健康检查持续访问 `/api/status`，确认服务真的能响应。

​        本章也故意保留了一些空白。API 暂时不连接 PostgreSQL，不连接 Redis，不写数据库模型和迁移，也不做统一响应封装、统一异常处理和 CORS 配置。这不是遗漏，而是节奏控制。工程教程最怕一章塞进太多概念，读者看似复制了代码，实际上并不知道每一层为什么存在。第 03 章只解决“后端服务能启动、能读配置、能返回状态”这一件事，后面的复杂能力会沿着这个入口逐步长出来。

​        本章新增的运行关系如下：

```Plain
浏览器 / curl
  |
  |  GET http://localhost:8000/api/status
  v
atlas-api
  |
  +-- 与 postgres、redis 在同一个 Docker 网络
```

​        注意：本章 API 只是加入同一个网络，还不会主动连接 `postgres` 和 `redis`。

## 3.5 新增和修改的文件

​        本章新增文件看起来不少，但它们并不是零散堆出来的。`api/app/core/config.py` 负责配置，`api/app/main.py` 负责应用创建，`api/app/api/router.py` 负责汇总路由，`api/app/api/routes/status.py` 负责具体接口，`api/app/schemas/status.py` 负责响应结构。除此之外，`Dockerfile`、`pyproject.toml` 和 `uv.lock` 让 API 服务可以被本地运行，也可以被 Docker Compose 构建和启动。

```Plain
.env.example
README.md
docker-compose.yml
api/README.md
api/Dockerfile
api/pyproject.toml
api/uv.lock
api/app/__init__.py
api/app/main.py
api/app/api/__init__.py
api/app/api/router.py
api/app/api/routes/__init__.py
api/app/api/routes/status.py
api/app/core/__init__.py
api/app/core/config.py
api/app/schemas/__init__.py
api/app/schemas/status.py
```

## 3.6 开始前检查：确认 Python 可用

​        本章第一次使用 Python 后端环境。

​        先在终端执行下面的命令，确认当前机器上是否已经有可用的 Python 解释器。这里检查的不是“有没有 Python”这么简单，而是确认后续依赖安装、FastAPI 启动和容器构建使用的语言版本不会太旧。

```Bash
python3 --version
```

​        正常情况下会看到类似输出：

```Plain
Python 3.11.15
```

​        本项目后端要求 Python 版本不低于 `3.11`。

​        如果 `python3` 显示的是 `3.11` 或更高版本，后续可以直接使用 `python3`。如果它指向的是更老的版本，也不要急着改系统默认 Python，可以继续检查本机是否已经安装了 `python3.11`：

```Bash
python3.11 --version
```

​        如果本机没有 Python 3.11 或更新版本，先安装 Python。macOS 可以使用官网安装包，也可以使用 `pyenv` 管理多个 Python 版本。

​        接下来确认 `uv` 可用。笔者在这个项目里选择 `uv`，主要是因为它能同时处理虚拟环境、依赖同步和锁文件，速度也比较快。对于课程项目来说，工具越稳定，越能把注意力留给架构本身。

```Bash
uv --version
```

​        正常情况下会看到类似输出：

```Plain
uv 0.11.15
```

​        `uv` 是一个 Python 项目和依赖管理工具。本章用它创建虚拟环境、安装依赖、锁定版本并运行 FastAPI。

​        如果提示 `command not found: uv`，说明本机还没有安装 `uv`。macOS 可以先执行：

```Bash
brew install uv
```

​        安装完成后重新执行 `uv --version`。

## 3.7 实施步骤

### 3.7.1 准备配置入口

​        后端服务启动时首先需要知道自己是谁。`api/app/core/config.py` 中的 `Settings` 就承担了这个职责。它不是业务代码，却会影响整个服务的行为：`api_app_name` 决定接口返回的服务名，`api_env` 标记当前运行环境，`api_version` 记录版本号，`api_prefix` 则决定所有 API 路由挂在哪个前缀下面。

​        这一层看起来很薄，但它是后续工程治理的起点。只要配置集中在一个地方，Docker Compose、`.env`、本地开发和生产部署就能使用同一套入口。源码里用 `@lru_cache` 包住 `get_settings()`，也是为了避免每次读取配置都重复构造对象。对现在这一章来说，这只是一个小优化；等到后面配置项逐渐增多，它会让应用的配置行为更稳定。

### 3.7.2 创建 FastAPI 应用

​        `api/app/main.py` 是后端真正的入口。这里没有直接在全局写一堆初始化逻辑，而是先定义 `create_app()`，再通过 `app = create_app()` 暴露给 Uvicorn。这样的写法有一个好处：应用创建过程是一个明确的函数，后续如果要接入异常处理、CORS、中间件、生命周期事件或测试夹具，都可以从这个函数继续扩展。

​        源码里的关键关系很简洁。`FastAPI(title=settings.api_app_name, version=settings.api_version)` 先创建应用实例，随后 `app.include_router(api_router, prefix=settings.api_prefix)` 把统一路由挂到 `/api` 下面。这样一来，具体路由文件只需要关心自己的局部路径，例如 `status.router` 的前缀是 `/status`，最终组合出来的完整路径就是 `/api/status`。

### 3.7.3 定义状态接口

​        `/api/status` 是本章唯一的业务接口。它的作用不是承载复杂业务，而是给人和系统一个确定的信号：服务已经启动，路由已经注册，配置已经读取，响应模型也能正常序列化。很多项目一开始会忽略这个接口，等到联调时才发现前端不知道后端是否可用，容器健康检查也没有稳定入口。

​        在源码中，`status.py` 使用 `APIRouter(prefix="/status", tags=["status"])` 创建路由，并通过 `response_model=StatusResponse` 声明返回结构。`StatusResponse` 只有四个字段：`service`、`environment`、`status` 和 `version`。字段不多，但信息足够。调用者看到它，就能判断当前访问的是哪个服务、运行在什么环境、服务状态是否正常，以及接口版本是多少。

### 3.7.4 接入 Docker Compose

​        本章最后一步是把 API 放进 Compose。`docker-compose.yml` 中新增的 `api` 服务会从 `./api` 构建镜像，把容器命名为 `atlas-api`，并通过 `API_PORT` 映射到宿主机端口。更重要的是，它和 PostgreSQL、Redis 一起加入 `atlas-network`。虽然本章还不连接数据库和 Redis，但网络边界已经提前放好，后续章节只需要在应用层接入即可。

​        Compose 里的健康检查也指向 `/api/status`。这是一处很小但很关键的工程细节：健康检查不能只看进程是否存在，而要看应用是否真的能响应请求。一个 Python 进程活着，并不代表 FastAPI 路由已经可用；只有状态接口返回成功，才能说明这个最小服务闭环真正跑通。

## 3.8 运行验证

​        本章的验证分成本地运行和容器运行两条线。本地运行时，先进入 `api` 目录，使用 `uv` 创建虚拟环境并同步依赖，然后启动 Uvicorn：

```Bash
cd api
uv venv --python 3.11
uv sync
uv run uvicorn app.main:app --reload
```

​        服务启动后访问：

```Bash
curl http://localhost:8000/api/status
```

​        如果返回的 JSON 中包含 `AtlasAgent API`、`development`、`ok` 和 `0.1.0`，说明配置、路由和响应模型已经串起来。本地验证通过后，再回到项目根目录使用 Docker Compose 构建并启动服务：

```Bash
docker compose up -d --build
docker compose ps
```

​        在 Compose 场景下，`atlas-api`、`atlas-postgres` 和 `atlas-redis` 应该都能正常启动。此时再次访问 `/api/status`，如果结果和本地运行一致，就说明 API 同时具备了本地开发和容器运行两种入口。后续章节无论接数据库、接 Redis，还是让前端通过 Nginx 访问 API，都可以建立在这个基础上。

## 3.9 本章小结

​        回过头看，第 03 章完成的事情并不复杂，但它是整个后端工程的第一块承重结构。我们没有急着写数据库，也没有急着把 Agent 逻辑塞进来，而是先把配置、应用入口、路由汇总、响应模型、状态接口和容器运行串成一个最小闭环。

​        这个闭环的价值在于可验证。你可以用浏览器访问它，可以用 `curl` 调用它，也可以让 Docker Compose 的健康检查持续探测它。一个能被稳定验证的最小服务，才适合作为后续复杂系统的起点。下一章会在这个入口之上继续补充通用模块，让 API 的配置、响应、异常和日志变得更像一个可以长期维护的后端服务。
