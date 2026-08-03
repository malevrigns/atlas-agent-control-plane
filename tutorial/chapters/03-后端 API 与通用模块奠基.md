# 第三章. 后端 API 与通用模块奠基

## 3.1 后端 API 最小服务初成

### 3.1.1 本节目标

​        从这一阶段开始，项目不再只是目录和基础设施，而是第一次拥有一个真正能被访问的后端入口。笔者希望读者在这一阶段里先建立一种工程直觉：一个后端服务并不是从复杂业务开始的，它首先要能稳定启动，要能读到自己的配置，要能把路由挂到统一入口下面，还要能提供一个最小但可靠的状态检查接口。只有这个入口站稳了，后面的数据库、会话、流式事件、Agent 调度和工具系统才有地方接入。

​        本节的目标不是一次性把 API 做完整，而是把 FastAPI 服务的骨架搭出来。你会看到 `create_app()` 如何创建应用，`api_router` 如何成为所有业务路由的汇总入口，`StatusResponse` 如何约束接口返回结构，以及 `/api/status` 如何把配置里的服务名、环境名和版本号返回给调用方。读完这一阶段后，读者应该能说清楚一个最小 API 服务从配置、应用入口、路由注册到接口响应之间的完整链路。

### 3.1.2 最终效果

​        本节结束后，项目会新增一个可以运行的后端 API 服务。

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

​        这里需要注意一个边界：本节虽然已经把 `api` 服务放进了 Docker Compose，并且让它和 `postgres`、`redis` 处在同一个 Docker 网络中，但 API 暂时不会主动连接这两个服务。第 2 章准备的是基础设施，本节要做的是应用入口。笔者刻意把这两件事拆开，是为了让读者先看清“服务能跑起来”这件事本身，避免一开始就被数据库连接、迁移、异常处理和跨域配置混在一起。

### 3.1.3 本节要解决的问题

​        第 2 章已经准备好了 PostgreSQL、Redis、Docker 网络和数据卷。现在项目有了基础设施，但还没有任何对外提供能力的后端服务。

​        这会带来一个问题：后续前端、任务系统、Agent 执行器都需要通过 API 和系统交互。如果没有一个最小 API 入口，后面的功能就没有统一接入点。

​        所以本节先实现一个很小的后端闭环：

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

### 3.1.4 本节技术方案

​        本节选择 FastAPI 作为后端框架。

​        如果只是为了返回一个 JSON，Python 标准库或者 Flask 都能完成任务。但 AtlasAgent 后续不是一个普通的 CRUD 服务，它要持续推送 Agent 执行事件，要查询后台任务状态，要调用 Sandbox、浏览器、Shell、搜索和 MCP 等外部能力，还会在前端保持长时间的交互状态。FastAPI 对异步接口、Pydantic 数据模型和接口文档的支持比较自然，用它作为后端入口，后面扩展 SSE、后台任务和工具调用时会更顺。

​        这一阶段的技术方案可以理解为四层小闭环。最底层是配置模块，`Settings` 从环境变量和 `.env` 中读取服务名、环境名、版本号和 API 前缀。再往上是应用入口，`create_app()` 创建 FastAPI 实例，并把统一路由挂到 `settings.api_prefix` 下面。第三层是路由，`api_router` 汇总具体业务路由，当前只挂载 `status.router`。最外层是 Docker Compose，它负责把 API 构建成容器，并通过健康检查持续访问 `/api/status`，确认服务真的能响应。

​        本节也故意保留了一些空白。API 暂时不连接 PostgreSQL，不连接 Redis，不写数据库模型和迁移，也不做统一响应封装、统一异常处理和 CORS 配置。这不是遗漏，而是节奏控制。工程教程最怕一章塞进太多概念，读者看似复制了代码，实际上并不知道每一层为什么存在。本节只解决“后端服务能启动、能读配置、能返回状态”这一件事，后面的复杂能力会沿着这个入口逐步长出来。

​        本节新增的运行关系如下：

```Plain
浏览器 / curl
  |
  |  GET http://localhost:8000/api/status
  v
atlas-api
  |
  +-- 与 postgres、redis 在同一个 Docker 网络
```

​        注意：本节 API 只是加入同一个网络，还不会主动连接 `postgres` 和 `redis`。

### 3.1.5 新增和修改的文件

​        本节新增文件看起来不少，但它们并不是零散堆出来的。`backend/api/app/core/config.py` 负责配置，`backend/api/app/main.py` 负责应用创建，`backend/api/app/api/router.py` 负责汇总路由，`backend/api/app/api/routes/status.py` 负责具体接口，`backend/api/app/schemas/status.py` 负责响应结构。除此之外，`Dockerfile`、`pyproject.toml` 和 `uv.lock` 让 API 服务可以被本地运行，也可以被 Docker Compose 构建和启动。

```Plain
.env.example
README.md
docker-compose.yml
backend/api/README.md
backend/api/Dockerfile
backend/api/pyproject.toml
backend/api/uv.lock
backend/api/app/__init__.py
backend/api/app/main.py
backend/api/app/api/__init__.py
backend/api/app/api/router.py
backend/api/app/api/routes/__init__.py
backend/api/app/api/routes/status.py
backend/api/app/core/__init__.py
backend/api/app/core/config.py
backend/api/app/schemas/__init__.py
backend/api/app/schemas/status.py
```

### 3.1.6 开始前检查：确认 Python 可用

​        本节第一次使用 Python 后端环境。

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

​        `uv` 是一个 Python 项目和依赖管理工具。本节用它创建虚拟环境、安装依赖、锁定版本并运行 FastAPI。

​        如果提示 `command not found: uv`，说明本机还没有安装 `uv`。macOS 可以先执行：

```Bash
brew install uv
```

​        安装完成后重新执行 `uv --version`。

### 3.1.7 实施步骤

#### 3.1.7.1 准备配置入口

​        后端服务启动时首先需要知道自己是谁。`backend/api/app/core/config.py` 中的 `Settings` 就承担了这个职责。它不是业务代码，却会影响整个服务的行为：`api_app_name` 决定接口返回的服务名，`api_env` 标记当前运行环境，`api_version` 记录版本号，`api_prefix` 则决定所有 API 路由挂在哪个前缀下面。

​        这一层看起来很薄，但它是后续工程治理的起点。只要配置集中在一个地方，Docker Compose、`.env`、本地开发和生产部署就能使用同一套入口。源码里用 `@lru_cache` 包住 `get_settings()`，也是为了避免每次读取配置都重复构造对象。对现在这一阶段来说，这只是一个小优化；等到后面配置项逐渐增多，它会让应用的配置行为更稳定。

#### 3.1.7.2 创建 FastAPI 应用

​        `backend/api/app/main.py` 是后端真正的入口。这里没有直接在全局写一堆初始化逻辑，而是先定义 `create_app()`，再通过 `app = create_app()` 暴露给 Uvicorn。这样的写法有一个好处：应用创建过程是一个明确的函数，后续如果要接入异常处理、CORS、中间件、生命周期事件或测试夹具，都可以从这个函数继续扩展。

​        源码里的关键关系很简洁。`FastAPI(title=settings.api_app_name, version=settings.api_version)` 先创建应用实例，随后 `app.include_router(api_router, prefix=settings.api_prefix)` 把统一路由挂到 `/api` 下面。这样一来，具体路由文件只需要关心自己的局部路径，例如 `status.router` 的前缀是 `/status`，最终组合出来的完整路径就是 `/api/status`。

#### 3.1.7.3 定义状态接口

​        `/api/status` 是本节唯一的业务接口。它的作用不是承载复杂业务，而是给人和系统一个确定的信号：服务已经启动，路由已经注册，配置已经读取，响应模型也能正常序列化。很多项目一开始会忽略这个接口，等到联调时才发现前端不知道后端是否可用，容器健康检查也没有稳定入口。

​        在源码中，`status.py` 使用 `APIRouter(prefix="/status", tags=["status"])` 创建路由，并通过 `response_model=StatusResponse` 声明返回结构。`StatusResponse` 只有四个字段：`service`、`environment`、`status` 和 `version`。字段不多，但信息足够。调用者看到它，就能判断当前访问的是哪个服务、运行在什么环境、服务状态是否正常，以及接口版本是多少。

#### 3.1.7.4 接入 Docker Compose

​        本节最后一步是把 API 放进 Compose。`docker-compose.yml` 中新增的 `api` 服务会从 `./backend/api` 构建镜像，把容器命名为 `atlas-api`，并通过 `API_PORT` 映射到宿主机端口。更重要的是，它和 PostgreSQL、Redis 一起加入 `atlas-network`。虽然本节还不连接数据库和 Redis，但网络边界已经提前放好，后续章节只需要在应用层接入即可。

​        Compose 里的健康检查也指向 `/api/status`。这是一处很小但很关键的工程细节：健康检查不能只看进程是否存在，而要看应用是否真的能响应请求。一个 Python 进程活着，并不代表 FastAPI 路由已经可用；只有状态接口返回成功，才能说明这个最小服务闭环真正跑通。

### 3.1.8 运行验证

​        本节的验证分成本地运行和容器运行两条线。本地运行时，先进入 `api` 目录，使用 `uv` 创建虚拟环境并同步依赖，然后启动 Uvicorn：

```Bash
cd backend/api
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

### 3.1.9 小结

​        回过头看，本节完成的事情并不复杂，但它是整个后端工程的第一块承重结构。我们没有急着写数据库，也没有急着把 Agent 逻辑塞进来，而是先把配置、应用入口、路由汇总、响应模型、状态接口和容器运行串成一个最小闭环。

​        这个闭环的价值在于可验证。你可以用浏览器访问它，可以用 `curl` 调用它，也可以让 Docker Compose 的健康检查持续探测它。一个能被稳定验证的最小服务，才适合作为后续复杂系统的起点。本章后文会在这个入口之上继续补充通用模块，让 API 的配置、响应、异常和日志变得更像一个可以长期维护的后端服务。

## 3.2 后端通用模块备料

### 3.2.1 本节目标

​        到前文为止，后端服务已经可以启动，也能通过 `/api/status` 告诉我们“我还活着”。但笔者并不想在这个状态下马上去写会话、文件、任务或 Agent 调度接口。原因很简单：一个能运行的 API，和一个适合持续扩展的 API，中间还隔着一层工程规范。如果没有这层规范，后续接口越写越多，返回格式、异常格式、日志方式和跨域配置都会逐渐散开，最后每个接口都像是从不同项目里搬来的。
​        本节的目标就是在业务代码真正膨胀之前，把后端公共能力先补齐。读完并完成这一阶段之后，读者应该能理解为什么要在业务接口之前完成通用模块，能用 `pydantic-settings` 管理 API、CORS 和日志配置，能把普通返回值包进统一响应结构，也能让 FastAPI 的 404、参数校验错误和业务错误都走同一种输出格式。更重要的是，读者要开始形成一个习惯：不要等重复代码已经铺满项目之后才想起抽象，真正有经验的工程搭建，往往是在重复出现之前先把边界留出来。

### 3.2.2 最终效果

​        前文的 `/api/status` 还很朴素，它直接把业务数据返回给调用方。这个结果对验证服务是否启动已经足够，但它还不是一个成熟后端项目愿意长期维持的接口形态。

```JSON
{
  "service": "AtlasAgent API",
  "environment": "development",
  "status": "ok",
  "version": "0.1.0"
}
```

​        本节会把这个接口升级成统一响应结构。升级之后，真正的状态数据仍然保留，只是被放进 `data` 字段里，外层增加 `code` 和 `message`。这样前端在面对不同接口时，不必先猜每个接口的返回外形，而是可以先读取统一外层，再进入具体业务数据。

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

​        更关键的是，错误也要统一。很多项目只统一了成功响应，却让错误响应继续保持框架默认格式。开发前期这似乎没什么问题，但一旦前端开始处理弹窗、表单错误、登录失效和任务失败，就会被不同形状的错误结构拖住。本节会把不存在的接口也转换成本项目自己的错误结构。

```JSON
{
  "code": 404,
  "message": "Not Found",
  "data": null
}
```

​        到这一阶段结束时，API 不只是“能返回 status”，而是拥有了继续开发业务接口所需的基本秩序：配置从环境中来，响应按统一外壳返回，异常由入口集中接管，日志在错误发生时留下线索，CORS 也提前为第 4 章的前端服务打开开发通道。

### 3.2.3 本节要解决的问题

​        前文创建的是最小 FastAPI 服务，它证明了项目目录、依赖安装、容器启动和路由注册都没有问题。但最小服务有一个典型陷阱：它会让人误以为可以马上开始堆业务。笔者以前也踩过这个坑，最开始为了快，接口怎么方便怎么写；等页面开始接入时才发现，有的接口返回对象，有的接口返回数组，有的错误是 `detail`，有的错误是字符串，有的异常甚至直接把内部栈暴露给调用方。
​        对 AtlasAgent 这种全栈 Agent 工作台来说，这个问题会更早出现。前端不仅要展示聊天内容，还要展示任务状态、工具结果、文件列表、浏览器观察、执行错误和最终回答。如果后端没有统一响应结构，前端就会把大量精力花在“兼容每个接口的特殊返回”上，而不是专注于产品体验。异常处理也是同理。业务异常、404、参数错误和系统错误可以来源不同，但它们最终都应该被翻译成调用方能稳定理解的结构。
​        因此，本节先不急着接数据库，也不急着写真正的 Agent 能力，而是先把通用模块立起来。它看起来没有业务功能那么直观，却决定了后续业务代码能不能保持干净。后面章节写会话、文件、沙箱和多 Agent 编排时，都会直接站在这一阶段搭好的基础上。

### 3.2.4 本节技术方案

​        这一阶段采用“先公共能力，后业务接口”的方案。另一种做法当然也能成立：先继续写业务，等重复逻辑明显出现之后再重构。很多小项目都这么做，因为它能在短时间内看到更多功能。但本教程不是只为了跑出一个演示页面，而是要把一个全栈 Agent 工作台从零搭到可部署、可演示、可继续扩展。既然后续接口数量会快速增加，把响应、异常、日志和 CORS 这些规则提前放好，反而是成本更低的路线。
​        从代码结构上看，本节不会改变 FastAPI 的基本入口，仍然通过 `create_app()` 创建应用。但这个入口不再只是创建应用和注册路由，而是变成后端公共能力的汇合点：启动时先配置日志，再创建 `FastAPI` 实例，然后注册 CORS 中间件、注册异常处理器，最后把 `/api` 路由挂进去。读者可以把它理解成后端服务的“启动骨架”。

```Plain
FastAPI app
  |
  +-- config      读取环境变量
  +-- response    统一响应模型
  +-- exception   统一异常处理
  +-- logging     基础日志
  +-- CORS        允许前端开发地址访问 API
  |
  v
/api/status
```

​        需要注意的是，`docker-compose.yml` 里此时已经保留了 PostgreSQL 和 Redis 服务，但本节的 API 暂时不会连接它们。笔者这里有意把“基础设施准备好”和“业务代码真正依赖它”分成两步。数据库、Redis、Repository、认证和更复杂的日志体系都很重要，但如果现在一次性塞进来，读者很容易看不清每个模块为什么存在。先把 API 自己的公共规范讲明白，再让它逐步接入外部依赖，学习路径会稳得多。

### 3.2.5 新增和修改的文件

​        本节改动的文件不算多，但它们基本覆盖了后端服务的入口、配置、异常、响应模型和运行环境。读者在阅读这些文件时，可以把它们分成两类：一类是“应用启动时要用到的文件”，比如 `main.py`、`config.py`、`logging.py` 和 `handlers.py`；另一类是“接口返回时要用到的文件”，比如 `common.py`、`status.py` 和 `status.py` 路由文件。这样看，文件之间的关系会比单纯记路径更清楚。

```Plain
.env.example
README.md
backend/api/README.md
docker-compose.yml
backend/api/app/main.py
backend/api/app/core/config.py
backend/api/app/core/exceptions.py
backend/api/app/core/handlers.py
backend/api/app/core/logging.py
backend/api/app/api/routes/status.py
backend/api/app/schemas/common.py
backend/api/app/schemas/status.py
pyrightconfig.json
```

### 3.2.6 实施步骤
#### 3.2.6.1 扩展配置模块

​        先打开 `backend/api/app/core/config.py`。前文里，这个文件只负责 API 名称、运行环境、版本号和接口前缀。到了本节，它开始承担更多“运行环境入口”的职责：前端从哪些地址访问后端，是否允许携带凭据，允许哪些请求方法和请求头，日志应该以什么级别输出，都不应该散落在业务代码里，而应该统一从配置层进入应用。

```Python
class Settings(BaseSettings):
    api_app_name: str = "AtlasAgent API"
    api_env: str = "development"
    api_version: str = "0.1.0"
    api_prefix: str = "/api"
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    log_level: str = "INFO"
```

​        这里最值得注意的是 CORS 配置。本节还没有创建 Next.js 服务，但第 4 章的前端默认会运行在 `localhost:3000`。如果现在不提前把这个地址写进允许列表，下一章前端调用后端时就会遇到浏览器跨域拦截。`cors_allow_methods` 和 `cors_allow_headers` 暂时使用 `["*"]`，是为了降低开发阶段的摩擦；真正部署到生产环境时，这些配置仍然可以通过环境变量收紧，而不需要改业务代码。
​        `log_level` 也放在这里，是因为日志级别天然属于环境差异。本地开发时我们可能希望看到更多信息，生产环境则需要更克制的输出。把它写进 `Settings`，后续无论从 `.env`、Docker Compose 还是部署平台注入，都能走同一个读取路径。

#### 3.2.6.2 更新环境变量模板

​        接着打开 `.env.example`。这个文件不是给程序直接运行用的，而是给读者和部署环境看的配置样板。教程项目尤其需要这种模板，因为每一章都会逐渐增加配置项；如果没有一个样板文件，后来者很难知道项目到底需要哪些环境变量。

```Plain
LOG_LEVEL=INFO
CORS_ALLOW_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=["*"]
CORS_ALLOW_HEADERS=["*"]
```

​        这里的列表写成 JSON 数组格式，是为了让 `pydantic-settings` 能把字符串解析成 Python 的 `list[str]`。这一点很容易被忽略。环境变量本质上都是字符串，如果我们随手写成 `http://localhost:3000,http://127.0.0.1:3000`，就还要自己处理分割、空格和转义。现在直接写成 JSON 数组，配置类会帮我们完成类型转换。

```Plain
CORS_ALLOW_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

​        会解析成：

```Python
["http://localhost:3000", "http://127.0.0.1:3000"]
```

#### 3.2.6.3 把配置传入 Docker Compose

​        本地直接运行 API 时，`pydantic-settings` 可以读取 `backend/api/.env`。但容器运行时，配置需要进入容器环境。于是还要打开 `docker-compose.yml`，把新增的日志和 CORS 配置放到 `api.environment` 下。这样无论读者使用本地 `uvicorn`，还是通过 Docker Compose 启动服务，应用看到的配置入口都是一致的。

```YAML
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      CORS_ALLOW_ORIGINS: ${CORS_ALLOW_ORIGINS:-["http://localhost:3000","http://127.0.0.1:3000"]}
      CORS_ALLOW_CREDENTIALS: ${CORS_ALLOW_CREDENTIALS:-true}
      CORS_ALLOW_METHODS: ${CORS_ALLOW_METHODS:-["*"]}
      CORS_ALLOW_HEADERS: ${CORS_ALLOW_HEADERS:-["*"]}
```

​        这里使用 `${变量名:-默认值}` 的写法，是 Docker Compose 常见的默认值机制。读者可以先不创建 `.env` 文件，服务仍然能用默认配置启动；如果后续要改端口、改允许来源或调整日志级别，只需要覆盖环境变量即可。笔者比较看重这一点，因为教程项目如果每换一个环境就要改源代码，后面讲部署时会非常混乱。

#### 3.2.6.4 创建统一响应模型

​        接下来进入响应结构。笔者在 `backend/api/app/schemas/common.py` 中创建 `ApiResponse`，它不是某个具体业务接口的模型，而是所有接口共享的外层包装。之所以把它放在 `schemas/common.py`，是因为它以后会被状态接口、会话接口、文件接口、任务接口和 Agent 接口共同使用。

```Python
from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")

class ApiResponse(BaseModel, Generic[DataT]):
    code: int = 200
    message: str = "success"
    data: DataT | None = None
```

​        这个结构很简单：`code` 表示本项目约定的业务状态，`message` 用来给调用方一个简短说明，`data` 才是真正的业务数据。这里使用 `Generic[DataT]`，是为了让外层结构保持统一，同时不牺牲内部数据的类型表达。状态接口的 `data` 可以是 `StatusData`，后续会话列表的 `data` 可以是 `list[SessionData]`，文件详情的 `data` 又可以是 `FileData`。外层一样，内层各自清楚。

```Python
ApiResponse[StatusData]
```

​        以后会话列表接口可以使用：

```Python
ApiResponse[list[SessionData]]
```

​        这也是 FastAPI 配合 Pydantic 很舒服的地方。我们不需要为了统一返回格式放弃类型，也不需要让前端去猜 `data` 里面到底是什么。只要 `response_model` 写清楚，接口文档和运行时序列化都会跟着稳定下来。

#### 3.2.6.5 调整状态响应模型

​        有了统一外层之后，状态接口自己的模型也要跟着调整。打开 `backend/api/app/schemas/status.py`，把前文里的 `StatusResponse` 改成 `StatusData`。这个改名看似很小，但语义很重要：它不再代表整个 HTTP 响应，而只代表 `data` 字段里的业务内容。

```Python
from pydantic import BaseModel

class StatusData(BaseModel):
    service: str
    environment: str
    status: str
    version: str
```

​        笔者建议读者在这里养成一个命名习惯：外层响应叫 `Response`，内部业务数据叫 `Data` 或更具体的实体名称。这样后续项目一大，看到模型名字就能知道它位于响应结构的哪一层，不需要每次都打开接口代码确认。

#### 3.2.6.6 改造状态接口

​        然后回到状态接口本身。打开 `backend/api/app/api/routes/status.py`，把返回模型改成 `ApiResponse[StatusData]`，并在函数里显式构造 `ApiResponse`。这样 `/api/status` 仍然表达同一件事：服务名称、环境、状态和版本；只是它现在遵守了本项目统一的接口外壳。

```Python
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.status import StatusData

router = APIRouter(prefix="/status", tags=["status"])

@router.get("", response_model=ApiResponse[StatusData])
async def get_status() -> ApiResponse[StatusData]:
    return ApiResponse(
        data=StatusData(
            service=settings.api_app_name,
            environment=settings.api_env,
            status="ok",
            version=settings.api_version,
        )
    )
```

​        这段代码的价值不在于 `/status` 本身，而在于它给后续接口打了样。以后前端拿到任何 API 响应，都可以先看 `code` 和 `message`，再读取 `data`。这会让前端请求层更容易封装，也会让错误提示、空状态和加载状态更容易统一。

#### 3.2.6.7 创建业务异常类型

​        接口成功时需要统一结构，接口失败时同样需要统一入口。笔者先在 `backend/api/app/core/exceptions.py` 中创建一个很薄的 `AppException`。它不依赖 FastAPI，也不直接返回 HTTP 响应，只描述业务层想表达的错误信息、业务码和 HTTP 状态码。

```Python
class AppException(Exception):
    def __init__(
        self,
        message: str,
        code: int = 400,
        status_code: int = 400,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)
```

​        这样设计的好处是，业务代码以后不用关心 `JSONResponse` 怎么构造，也不用每个接口都写一遍错误格式。比如后续查询会话时，如果会话不存在，业务层只需要抛出一个明确的异常。

```Python
raise AppException(message="session not found", code=404, status_code=404)
```

​        至于这个异常最终如何变成 HTTP 响应，则交给下一步的异常处理器完成。职责分开以后，业务代码会更像业务代码，框架适配代码也会集中在框架层。

#### 3.2.6.8 注册统一异常处理器

​        现在打开 `backend/api/app/core/handlers.py`。这个文件负责把不同来源的错误翻译成同一种响应结构。核心函数是 `build_error_response()`，它接收业务码、错误信息和 HTTP 状态码，然后用 `ApiResponse[None]` 构造统一错误体。

```Python
def build_error_response(code: int, message: str, status_code: int) -> JSONResponse:
    payload = ApiResponse[None](code=code, message=message, data=None)
    return JSONResponse(status_code=status_code, content=payload.model_dump())
```

​        这个函数负责把错误统一转换成：

```JSON
{
  "code": 404,
  "message": "Not Found",
  "data": null
}
```

​        本节一共接管四类错误。`AppException` 用来表达后续业务主动抛出的异常，`HTTPException` 用来接住 FastAPI 或 Starlette 产生的 HTTP 错误，`RequestValidationError` 用来处理请求参数不符合模型定义的情况，最后的 `Exception` 则作为未捕获错误的兜底入口。这里的“兜底”不是为了吞掉错误，而是为了保证调用方收到稳定响应，同时日志里仍然记录真实异常。
​        最后用 `register_exception_handlers(app)` 把这些处理器注册到 FastAPI 应用上。

```Python
def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
```

​        这样后续接口抛出异常时，不需要每个接口自己写 `try/except`。笔者更推荐这种方式：业务接口保持短小，异常翻译集中在应用边界，日志也在同一个地方沉淀。等项目变大以后，这种集中处理会明显降低排查成本。

#### 3.2.6.9 加入基础日志

​        异常处理器里已经开始写日志，因此还需要一个最基础的日志配置入口。打开 `backend/api/app/core/logging.py`，先用 Python 标准库完成初始化。

```Python
import logging

from app.core.config import settings

def configure_logging() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
```

​        这里没有急着引入结构化日志、日志文件轮转或链路追踪。原因不是它们不重要，而是现在还没有真实业务流量，也没有跨服务调用链。教程前期最需要的是让错误在开发阶段可见：哪个路径出错、属于哪类异常、错误信息是什么。标准库 `logging` 已经足够完成这个阶段的任务。后面当沙箱、任务队列和 Agent 执行链路加入后，再扩展日志形态会更自然。

#### 3.2.6.10 在应用入口注册通用模块

​        最后回到应用入口 `backend/api/app/main.py`。前面写的配置、日志、CORS 和异常处理，如果不在入口处串起来，都只是孤立文件。`create_app()` 正是它们汇合的地方。

```Python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging

def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.api_app_name,
        version=settings.api_version,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app

app = create_app()
```

​        这段代码的顺序值得留意。日志要尽早配置，因为后续启动过程和异常处理都可能需要输出日志；CORS 要在路由处理之前作为中间件接入；异常处理器要在业务路由开始承接请求前注册；最后才把 `api_router` 挂到 `settings.api_prefix` 下。最终启动链路可以理解成下面这样：

```Plain
配置日志
  |
创建 FastAPI app
  |
注册 CORS 中间件
  |
注册异常处理器
  |
注册业务路由
```

​        这也是笔者希望读者在本节真正掌握的部分。`create_app()` 不是随便堆代码的地方，它应该像一个清晰的装配函数：每一项公共能力在这里接入，业务路由在这里获得统一运行环境。后面章节新增路由时，就不必再重复考虑 CORS、异常格式和基础日志。

#### 3.2.6.11 配置编辑器类型检查

​        这一节看似和运行逻辑无关，但对实际开发体验很重要。很多读者第一次打开项目时，代码能运行，编辑器却在 `from pydantic import BaseModel` 这种导入上标红。原因通常不是依赖没装，而是编辑器没有识别 `backend/api/.venv` 这个虚拟环境。

```Python
from pydantic import BaseModel
```

​        代码本身可以运行，但编辑器不知道应该使用哪个 Python 虚拟环境。

​        在项目根目录创建 `pyrightconfig.json`：

```JSON
{
  "include": ["backend/api/app"],
  "exclude": ["**/__pycache__", "backend/api/.venv"],
  "venvPath": "api",
  "venv": ".venv",
  "pythonVersion": "3.11",
  "typeCheckingMode": "basic"
}
```

​        `pyrightconfig.json` 的作用就是告诉 Cursor 或 VSCode：后端代码主要在 `backend/api/app`，虚拟环境位于 `backend/api/.venv`，Python 版本按 `3.11` 解析，类型检查先使用 `basic` 模式。这里先不追求特别严格的类型检查，因为项目还在从零搭建阶段；先让编辑器准确识别依赖和基础类型，比一开始就打开最严格规则更适合教程节奏。如果配置后仍然看到旧报错，重载窗口通常就能让语言服务重新读取配置。

### 3.2.7 关键理解

​        本节最重要的词其实就是“统一”。统一响应解决的是前后端对接问题，前端不需要猜每个接口外层到底长什么样；统一异常解决的是错误翻译问题，业务接口只负责表达错误，框架边界负责把错误变成 HTTP 响应；CORS 解决的是浏览器跨域访问问题，后端必须明确告诉浏览器哪些前端来源被允许；日志解决的是排查问题，接口出错后至少要知道路径、异常类型和关键错误信息；配置模块解决的是环境差异问题，本地、容器和部署环境可以使用不同配置，但代码不应该跟着环境来回改。
​        这些能力单独看都不复杂，但它们组合在一起，会决定一个后端项目有没有“继续长大”的空间。笔者认为，初学者写后端时最容易低估的不是某个框架 API，而是这些公共约定。一旦约定缺失，业务代码很快会失去边界；一旦约定稳定，后续加接口反而会变得轻松。

### 3.2.8 技术难点与亮点

​        本节的技术难点不在代码量，而在几个概念边界。HTTP 状态码和业务 `code` 不是同一个东西。HTTP 状态码是协议层告诉调用方这次请求整体成功、失败还是参数有问题，业务 `code` 则是项目内部对结果的进一步表达。很多项目会把二者混在一起，最后前端既要判断 HTTP 状态，又要判断业务字段，还要兼容各种历史返回。AtlasAgent 从这一阶段开始就把外层结构固定下来，后续对接会少很多歧义。
​        `ApiResponse[StatusData]` 这种泛型响应模型也是本节的一个重点。它让统一响应不是简单地“套一层字典”，而是继续保留类型信息。FastAPI 会根据模型生成接口文档，Pydantic 会负责序列化，编辑器也能看懂返回类型。对于一个会逐渐长出几十个接口的项目来说，这种类型约束能减少很多低级错误。
​        还有一个容易误解的点是 CORS。CORS 不是权限系统，它只是浏览器的跨域访问规则。允许 `localhost:3000` 访问 API，不等于任何用户都拥有业务权限；它只表示浏览器可以把这个来源发起的请求交给后端处理。真正的登录、鉴权和权限控制会在后续业务章节继续完成。
​        本节的项目亮点，是在业务接口变多之前就把这些边界放好。`AppException` 把业务错误从框架错误里分出来，`register_exception_handlers()` 把错误翻译集中起来，`create_app()` 把通用能力装配到一个入口，标准库日志先满足开发排查需求，CORS 则为第 4 章前端接入提前铺路。这些处理都不花哨，但很实用。

### 3.2.9 面试考点

​        如果把这一阶段放到面试场景里，面试官大概率不会问你“`logging.basicConfig` 的参数怎么写”，而是会追问你为什么要这样组织后端基础模块。比如，后端为什么需要统一响应结构，HTTP 状态码和业务状态码到底有什么区别，FastAPI 的异常处理器如何接管默认错误响应，CORS 为什么只在浏览器场景里明显出现，`pydantic-settings` 如何把环境变量解析成配置对象，为什么配置项不应该写死在业务函数里，日志模块为什么应该在项目早期就加入。
​        这些问题背后考察的不是记忆，而是工程判断。你能说清楚“为什么现在做这件事”，比只说“代码是这么写的”更重要。AtlasAgent 后续会有很多业务能力，但如果底层响应、异常和配置不稳定，再高级的 Agent 逻辑也会被基础工程问题拖慢。

### 3.2.10 运行验证

​        本节改动的是后端公共能力，所以验证不能只看服务能不能启动，还要分别看语法、Compose 配置、成功响应、错误响应和 CORS 响应头。下面命令默认在项目根目录执行。

```Bash
pwd
```

​        预期目录类似：

```Plain
/Users/atlas/Desktop/github/atlas-agents
```

#### 3.2.10.1 检查 Python 代码

​        先用 `compileall` 做一次最基础的语法检查。它不会替代单元测试，但可以快速暴露导入路径、缩进和语法层面的明显错误。

```Bash
python3.11 -m compileall backend/api/app
```

​        预期看到 `Listing` 输出，没有语法错误。

#### 3.2.10.2 检查 Compose 配置

​        接着检查 Docker Compose 展开后的配置。这样可以确认新增环境变量真的进入了 `api` 服务，而不是只写在文档或模板里。

```Bash
docker compose config
```

​        预期输出里能看到新增的 CORS 和日志环境变量：

```Plain
CORS_ALLOW_ORIGINS: '["http://localhost:3000","http://127.0.0.1:3000"]'
LOG_LEVEL: INFO
```

#### 3.2.10.3 本地运行 API

​        下面本地启动 API。读者可以继续使用默认 `8000` 端口；如果本机端口已经被占用，也可以临时用 `18000` 做验证。端口并不重要，关键是这次启动的仍然是 `app.main:app`，也就是刚刚装配过日志、CORS 和异常处理器的应用入口。

```Bash
cd backend/api
```

​        同步依赖：

```Bash
uv sync
```

​        如果本机 `8000` 端口被占用，可以使用 `18000` 临时验证：

```Bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 18000
```

#### 3.2.10.4 验证统一响应

​        API 启动后，另开一个终端访问状态接口。这里要观察的不只是 `status` 是否为 `ok`，还要确认外层已经出现 `code`、`message` 和 `data`。

```Bash
curl http://127.0.0.1:18000/api/status
```

​        预期输出：

```JSON
{"code":200,"message":"success","data":{"service":"AtlasAgent API","environment":"development","status":"ok","version":"0.1.0"}}
```

#### 3.2.10.5 验证统一异常

​        然后访问一个不存在的接口。这个请求会触发框架层的 404，但返回体应该已经被本节注册的异常处理器改造成项目统一格式。

```Bash
curl http://127.0.0.1:18000/api/not-found
```

​        预期输出：

```JSON
{"code":404,"message":"Not Found","data":null}
```

#### 3.2.10.6 验证 CORS

​        最后验证 CORS。这里通过 `Origin: http://localhost:3000` 模拟第 4 章前端页面发起请求时的来源，观察响应头里是否出现允许跨域的字段。

```Bash
curl -I -H "Origin: http://localhost:3000" http://127.0.0.1:18000/api/status
```

​        预期响应头里包含：

```Plain
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Credentials: true
```

​        如果看到 `405 Method Not Allowed`，不用紧张。这里使用 `-I` 发送的是 `HEAD` 请求，而当前状态接口只定义了 `GET`。本节要观察的是 CORS 响应头是否出现，而不是 HEAD 请求本身是否被业务接口处理。验证完成后，在运行 API 的终端按 `Ctrl + C` 停止服务。

### 3.2.11 小结

​        本节把后端从“最小可运行”推进到了“适合继续开发业务接口”的状态。我们扩展了配置模块，让 API、CORS 和日志都能从环境中进入应用；加入了统一响应模型，让成功响应和错误响应拥有一致的外层结构；改造了 `/api/status`，让它成为后续接口的返回样板；定义了 `AppException`，让业务错误有了自己的表达方式；注册了异常处理器，让框架错误和业务错误都能被翻译成统一 JSON；最后又在 `create_app()` 中集中接入日志、CORS、异常处理和路由。
​        这一阶段写完之后，项目表面上仍然只是一个状态接口，但内在结构已经不一样了。后续写会话、文件、任务、Agent 执行和沙箱调用时，不必每次重新讨论响应格式、异常格式和跨域问题。笔者更愿意把这一阶段看成 AtlasAgent 后端的“工程底盘”：它不直接展示给用户，却会承载后面越来越多的业务重量。

## 3.3 本章小结

​        完成“后端 API 最小服务初成”和“后端通用模块备料”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第二章. Docker Compose 基础设施奠基](02-Docker%20Compose%20基础设施奠基.md) · [返回目录](../README.md) · [第四章. 前端 UI 与 Nginx 网关贯通 →](04-前端%20UI%20与%20Nginx%20网关贯通.md)
