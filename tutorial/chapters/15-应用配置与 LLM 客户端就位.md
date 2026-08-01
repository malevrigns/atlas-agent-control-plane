# 第十五章. 应用配置与 LLM 客户端就位

## 15.1 本章目标
​        前面的章节已经完成会话、消息、事件、文件和存储边界，但系统还没有真正调用大模型。也就是说，用户发出的消息目前只是被保存下来，还没有进入智能体的推理链路。第十五章开始补上这条最核心的能力：让后端具备读取 LLM 配置、检查密钥、调用 OpenAI 兼容接口并返回模型内容的基础。
​        本章不会急着把 LLM 接入会话流，也不会做 Agent 工具调用。我们先把配置和客户端打稳：YAML 保存 provider、model、temperature、max_tokens 和 base_url 这类非敏感结构化配置，环境变量保存真实 API Key；应用服务负责读取配置并创建客户端；路由只暴露配置查询和最小聊天调用接口。这样后续接入 Agent Runner 时，模型调用能力已经有了清楚边界。

## 15.2 最终效果
​        本章结束后，后端会新增两个接口。
​        查看 LLM 配置：

```Plain
GET /api/config/llm
```

​        调用模型聊天：

```Plain
POST /api/llm/chat
```

​        如果没有配置 `LLM_API_KEY`，配置接口会正常返回：

```JSON
{
  "configured": false
}
```

​        聊天接口会返回明确错误：

```JSON
{
  "code": 500,
  "message": "LLM api key is not configured: LLM_API_KEY",
  "data": null
}
```

​        如果填入可用的 API Key，并且 `base_url` 指向 OpenAI 兼容服务，聊天接口会返回模型内容。

## 15.3 本章要解决的问题
​        前面章节已经完成会话、消息、事件、文件、文件预览和存储扩展。
​        但是目前用户发送消息后，系统只是保存消息和事件，还没有真正调用大模型。
​        要调用大模型，至少需要解决四个问题：

```Plain
使用哪个 provider
使用哪个 model
请求发到哪个 base_url
真实 API Key 从哪里来
```

​        这些信息不能都写死在代码里。
​        原因很简单：
​        开发环境和生产环境可能使用不同模型，不同服务商也会提供不同的 `base_url`。更重要的是，API Key 是敏感信息，不能被写进仓库。后续页面需要知道当前默认模型、provider 和密钥是否已经配置，但绝不能拿到真实密钥本身。因此，配置层必须从一开始就把“可公开展示的信息”和“只能留在运行环境里的密钥”分开。
​        所以本章先建立 LLM 配置和客户端调用基础。

## 15.4 本章技术方案
​        本章使用：

```Plain
YAML 配置文件保存默认模型和 provider 信息
.env 环境变量保存真实 API Key
httpx 发送 OpenAI 兼容 HTTP 请求
FastAPI 暴露配置接口和聊天接口
```

​        为什么使用 YAML？
​        因为 LLM 配置是结构化配置，不只是一个字符串。
​        例如：

```Plain
默认 provider
默认 model
temperature
max_tokens
provider.base_url
provider.api_key_env
provider.timeout_seconds
```

​        这些信息放在 YAML 里更清楚，也更适合后续扩展多个 provider。
​        为什么 API Key 不放 YAML？
​        因为 YAML 文件会提交到仓库。如果把真实 Key 写进去，会造成密钥泄露。
​        本章只在 YAML 里写：

```Plain
api_key_env: LLM_API_KEY
```

​        意思是：真正的密钥要从名为 `LLM_API_KEY` 的环境变量读取。
​        本章调用链路如下：

```Plain
POST /api/llm/chat
  |
  v
LLMService
  |
  +-- load_llm_config()
  +-- os.getenv("LLM_API_KEY")
  |
  v
OpenAICompatibleClient
  |
  v
POST {base_url}/chat/completions
```

​        本章暂时不做这些内容：
​        本章暂时不把 LLM 接入会话发送消息流程，不做流式输出，也不做多 provider 页面配置、Agent 思考、工具调用和模型调用记录。这里先把最小客户端跑通，后续章节再把它接入 Agent 执行链路。
​        这些能力会在后续章节逐步接入。

## 15.5 新增和修改的文件

```Plain
.env.example
README.md
api/README.md
api/Dockerfile
api/config/llm.yaml
api/pyproject.toml
api/uv.lock
api/app/api/router.py
api/app/api/routes/config.py
api/app/api/routes/llm.py
api/app/application/llm_service.py
api/app/core/config.py
api/app/core/llm_config.py
api/app/domain/llm/__init__.py
api/app/domain/llm/entities.py
api/app/infrastructure/llm/__init__.py
api/app/infrastructure/llm/openai_compatible.py
api/app/schemas/llm.py
docker-compose.yml
docs/course/chapter-template.md
docs/course/conventions.md
docs/course/chapters/15-llm-client.md
```

## 15.6 实施步骤
### 15.6.1 安装 HTTP 和 YAML 依赖
​        进入后端目录：

```Bash
cd api
```

​        安装依赖：

```Bash
uv add httpx pyyaml
```

​        这一步会更新：

```Plain
api/pyproject.toml
api/uv.lock
```

​        `httpx` 用来发起异步 HTTP 请求。
​        `pyyaml` 用来读取 YAML 配置文件。
​        这一步完成后，`api/pyproject.toml` 的依赖里会出现：

```TOML
"httpx>=0.28.1",
"pyyaml>=6.0.3",
```

​        常见误区：
​        不要只手动改 `pyproject.toml`。如果不更新 `uv.lock`，Docker 构建时会因为锁文件和依赖声明不一致而失败。

### 15.6.2 创建 LLM YAML 配置
​        创建 `api/config/llm.yaml`：

```YAML
llm:
  default_provider: openai_compatible
  default_model: gpt-4o-mini
  temperature: 0.2
  max_tokens: 1024

providers:
  openai_compatible:
    base_url: https://api.openai.com/v1
    api_key_env: LLM_API_KEY
    timeout_seconds: 60
```

​        这段配置在流程中的位置：

```Plain
LLMService 初始化
  |
  v
load_llm_config()
  |
  v
读取 api/config/llm.yaml
```

​        输入和输出：
​        这一步的输入是 YAML 文件内容，输出是后端可以直接使用的 `LLMConfig` 对象。不要把它理解成简单读取文本文件；它还承担结构校验职责，确保默认 provider、默认模型和各个 provider 的连接信息都能被后续服务稳定使用。
​        关键字段解释：
​        `default_provider` 表示默认使用哪个 provider。
​        `default_model` 表示默认使用哪个模型。
​        `temperature` 控制输出随机性，越低越稳定，越高越发散。
​        `max_tokens` 控制模型最多生成多少 token。
​        `base_url` 是 OpenAI 兼容接口地址。
​        `api_key_env` 不是 API Key。它只是环境变量名称。
​        为什么这样设计：
​        把 `base_url`、`model`、`temperature` 放在 YAML 里，方便团队看到当前默认配置。
​        把真实 API Key 放进环境变量，可以避免密钥进入代码仓库。
​        小白最容易困惑的点：
​        `api_key_env: LLM_API_KEY` 的意思不是 Key 等于 `LLM_API_KEY`，而是运行时去读取：

```Plain
LLM_API_KEY=真实密钥
```

### 15.6.3 让 Settings 知道配置文件路径
​        打开 `api/app/core/config.py`，加入：

```Python
llm_config_path: str = "config/llm.yaml"
```

​        同步更新 `.env.example`：

```Plain
LLM_CONFIG_PATH=config/llm.yaml
```

​        同步更新 `docker-compose.yml`：

```YAML
LLM_CONFIG_PATH: ${LLM_CONFIG_PATH:-config/llm.yaml}
LLM_API_KEY: ${LLM_API_KEY:-}
```

​        这段代码在流程中的位置：

```Plain
容器启动
  |
  v
读取环境变量
  |
  v
Settings.llm_config_path
  |
  v
load_llm_config()
```

​        为什么 Docker Compose 要传 `LLM_API_KEY`？
​        因为 API 容器是一个独立运行环境。
​        你在宿主机 `.env` 里写了 `LLM_API_KEY`，不代表容器自动能读到。Compose 需要显式把环境变量传给 `api` 服务。

### 15.6.4 编写 LLM 配置加载器
​        创建 `api/app/core/llm_config.py`：

```Python
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import AppException


# ===================== 第1步：定义 YAML 中 llm 节点的数据结构 =====================
class LLMDefaults(BaseModel):
    default_provider: str
    default_model: str
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)


# ===================== 第2步：定义每个模型服务商的连接配置 =====================
class LLMProviderConfig(BaseModel):
    base_url: str
    # 这里保存的是环境变量名称，不是真实密钥，避免把密钥写进配置文件。
    api_key_env: str
    timeout_seconds: float = Field(gt=0)


# ===================== 第3步：定义完整 LLM 配置文件结构 =====================
class LLMConfig(BaseModel):
    llm: LLMDefaults
    providers: dict[str, LLMProviderConfig]


# ===================== 第4步：读取、解析并校验 YAML 配置 =====================
@lru_cache
def load_llm_config() -> LLMConfig:
    path = Path(settings.llm_config_path)
    if not path.is_file():
        raise AppException(
            message=f"LLM config file not found: {settings.llm_config_path}",
            code=500,
            status_code=500,
        )

    raw_config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = LLMConfig.model_validate(raw_config)
    # 默认 provider 必须能在 providers 中找到，否则后续聊天接口不知道该调用谁。
    if config.llm.default_provider not in config.providers:
        raise AppException(
            message="default LLM provider is not defined",
            code=500,
            status_code=500,
        )
    return config
```

​        这段代码在流程中的位置：

```Plain
LLMService()
  |
  v
load_llm_config()
  |
  v
得到 LLMConfig
```

​        输入和输出：
​        这段加载器读取 `config/llm.yaml`，再用 Pydantic 校验成 `LLMConfig`。如果配置文件不存在，或者默认 provider 没有在 `providers` 中定义，错误会在这里明确暴露，而不是等到真正调用模型时才变成难以定位的请求失败。
​        调用链路：

```Plain
Route -> LLMService -> load_llm_config -> YAML 文件
```

​        关键代码逐段解释：
​        第一段 `LLMDefaults` 对应 YAML 中的 `llm` 节点。
​        第二段 `LLMProviderConfig` 对应 YAML 中每个 provider 的配置。
​        第三段 `LLMConfig` 把默认配置和 provider 列表组合起来。
​        第四段 `load_llm_config()` 负责读文件、解析 YAML、做结构校验。
​        为什么这样设计：
​        YAML 只是文本，不做校验的话，字段写错也可能到调用模型时才暴露。
​        使用 Pydantic 后，如果 `temperature` 超过范围、`max_tokens` 不是正数、provider 缺字段，后端会尽早报错。
​        小白最容易困惑的点：
​        `@lru_cache` 表示配置加载后会缓存。这样每次请求不会重复读 YAML 文件。
​        如果开发时修改了 YAML，需要重启 API 才会重新加载。
​        本章先不做什么：
​        本章不做在线修改配置。配置修改仍然通过文件和环境变量完成。

### 15.6.5 定义 LLM 领域数据结构
​        创建 `api/app/domain/llm/entities.py`：

```Python
from dataclasses import dataclass


# ===================== 第1步：定义最小消息结构 =====================
@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


# ===================== 第2步：定义一次模型调用需要的完整参数 =====================
@dataclass(slots=True)
class LLMChatRequest:
    messages: list[LLMMessage]
    model: str
    provider: str
    temperature: float
    max_tokens: int


# ===================== 第3步：定义模型调用完成后的统一结果 =====================
@dataclass(slots=True)
class LLMChatResult:
    provider: str
    model: str
    content: str
    usage: dict | None = None
```

​        这段代码在流程中的位置：

```Plain
LLMService
  |
  +-- 组装 LLMChatRequest
  |
  v
OpenAICompatibleClient
  |
  +-- 返回 LLMChatResult
```

​        输入和输出：
​        `LLMMessage` 表示 system、user、assistant 这类模型消息；`LLMChatRequest` 表示一次完整模型请求，它把消息、模型、provider、temperature 和 max_tokens 放在一起；`LLMChatResult` 则是项目内部统一使用的模型结果。这样做之后，应用层不需要直接依赖第三方响应格式。
​        为什么不直接在整个项目里使用 OpenAI 返回的 JSON？
​        因为后续可能接入多个 provider。
​        不同 provider 的原始返回格式可能不完全一样。项目里应该尽量使用统一结构。
​        小白最容易困惑的点：
​        `role` 不是随便写的字符串。OpenAI 兼容接口通常支持：

```Plain
system
user
assistant
```

​        本章在 API Schema 里会限制这三个值。

### 15.6.6 编写 OpenAI 兼容客户端
​        创建 `api/app/infrastructure/llm/openai_compatible.py`：

```Python
import httpx

from app.core.exceptions import AppException
from app.domain.llm.entities import LLMChatRequest, LLMChatResult


# ===================== 第1步：封装 OpenAI 兼容的 HTTP 客户端 =====================
class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        provider: str,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    async def chat(self, request: LLMChatRequest) -> LLMChatResult:
        # ===================== 第2步：组装 /chat/completions 请求体 =====================
        payload = {
            "model": request.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # ===================== 第3步：向模型服务商发送 HTTP 请求 =====================
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AppException(
                message=f"LLM request failed: {exc}",
                code=502,
                status_code=502,
            ) from exc

        # ===================== 第4步：把服务商错误统一转换为项目异常 =====================
        if response.status_code >= 400:
            raise AppException(
                message=f"LLM provider returned HTTP {response.status_code}",
                code=502,
                status_code=502,
            )

        # ===================== 第5步：解析 OpenAI 兼容响应结构 =====================
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise AppException(
                message="LLM provider returned empty choices",
                code=502,
                status_code=502,
            )

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise AppException(
                message="LLM provider returned empty message content",
                code=502,
                status_code=502,
            )

        # 这里只取第一条回复，后续如果支持多候选结果，可以在这里扩展。
        return LLMChatResult(
            provider=request.provider,
            model=request.model,
            content=content,
            usage=data.get("usage"),
        )
```

​        这段代码在流程中的位置：

```Plain
LLMService.chat()
  |
  v
OpenAICompatibleClient.chat()
  |
  v
HTTP POST /chat/completions
```

​        输入和输出：
​        客户端接收项目统一的 `LLMChatRequest`，把它转换成 OpenAI 兼容的 `/chat/completions` 请求；模型服务商返回响应后，客户端再把 `choices[0].message.content` 和 `usage` 提取成 `LLMChatResult`。第三方协议只留在基础设施层，应用服务看到的是项目自己的对象。
​        调用链路：

```Plain
Route -> LLMService -> OpenAICompatibleClient -> 模型服务商
```

​        关键代码逐段解释：
​        第 1 步保存连接信息，包括 `api_key`、`base_url`、`timeout_seconds`。
​        第 2 步把项目消息转换成 OpenAI 兼容的请求体。
​        第 3 步使用 `httpx.AsyncClient` 发起异步 HTTP 请求。
​        第 4 步把模型服务商返回的错误统一转换为 `AppException`。
​        第 5 步解析响应里的 `choices[0].message.content`。
​        为什么这样设计：
​        后端 API 不应该把模型服务商的原始错误结构直接抛给前端。
​        统一转换成 `AppException` 后，前端收到的格式仍然是项目统一响应：

```JSON
{"code":502,"message":"...","data":null}
```

​        小白最容易困惑的点：
​        `base_url` 里通常不包含 `/chat/completions`。
​        所以代码里拼接：

```Python
f"{self.base_url}/chat/completions"
```

​        如果配置里的 `base_url` 已经带了 `/chat/completions`，请求路径就会重复。
​        本章先不做什么：
​        本章不做流式输出。`chat()` 会等模型完整返回后，再把内容返回给前端。

### 15.6.7 编写 LLM 应用服务
​        创建 `api/app/application/llm_service.py`：

```Python
import os

from app.core.exceptions import AppException
from app.core.llm_config import LLMConfig, load_llm_config
from app.domain.llm.entities import LLMChatRequest, LLMChatResult, LLMMessage
from app.infrastructure.llm.openai_compatible import OpenAICompatibleClient


# ===================== 第1步：编写 LLM 应用服务 =====================
class LLMService:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or load_llm_config()

    # ===================== 第2步：返回可公开展示的配置 =====================
    def get_public_config(self) -> dict:
        return {
            "default_provider": self.config.llm.default_provider,
            "default_model": self.config.llm.default_model,
            "temperature": self.config.llm.temperature,
            "max_tokens": self.config.llm.max_tokens,
            "providers": [
                {
                    "name": name,
                    "base_url": provider.base_url,
                    "api_key_env": provider.api_key_env,
                    # 只返回是否已配置，不返回真实密钥。
                    "configured": bool(os.getenv(provider.api_key_env)),
                }
                for name, provider in self.config.providers.items()
            ],
        }

    # ===================== 第3步：根据配置和请求参数发起模型调用 =====================
    async def chat(
        self,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMChatResult:
        provider_name = provider or self.config.llm.default_provider
        provider_config = self.config.providers.get(provider_name)
        if provider_config is None:
            raise AppException(
                message=f"LLM provider not found: {provider_name}",
                code=400,
                status_code=400,
            )

        api_key = os.getenv(provider_config.api_key_env)
        if not api_key:
            # 密钥只能来自环境变量，不能写进 YAML，也不能从接口传入。
            raise AppException(
                message=f"LLM api key is not configured: {provider_config.api_key_env}",
                code=500,
                status_code=500,
            )

        # 请求参数优先使用接口传入值；没有传入时使用 YAML 默认值。
        request = LLMChatRequest(
            messages=messages,
            model=model or self.config.llm.default_model,
            provider=provider_name,
            temperature=temperature
            if temperature is not None
            else self.config.llm.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.config.llm.max_tokens,
        )
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=provider_config.base_url,
            provider=provider_name,
            timeout_seconds=provider_config.timeout_seconds,
        )
        return await client.chat(request)
```

​        这段代码在流程中的位置：

```Plain
API Route
  |
  v
LLMService
  |
  +-- 读取配置
  +-- 检查 provider
  +-- 读取环境变量
  +-- 创建客户端
  |
  v
OpenAICompatibleClient
```

​        输入和输出：
​        `get_public_config()` 返回可以公开展示的配置，包括默认 provider、默认模型和每个 provider 是否已经配置密钥；`chat()` 则接收消息列表和可选覆盖参数，完成 provider 查找、API Key 读取、请求对象构造和客户端调用。密钥只在服务端运行时读取，不进入响应体。
​        关键代码逐段解释：
​        `__init__()` 加载 LLM 配置。
​        `get_public_config()` 返回给前端看的配置，但不返回真实密钥。
​        `chat()` 先确定 provider，再检查 provider 是否存在。
​        然后从环境变量读取 API Key。
​        最后组装 `LLMChatRequest` 并调用客户端。
​        为什么这样设计：
​        `LLMService` 是应用服务，它负责业务编排。
​        它不直接写 HTTP 请求细节，因为 HTTP 细节属于基础设施客户端。
​        它也不直接暴露 Key，因为 Key 只应该在后端运行时使用。
​        小白最容易困惑的点：
​        为什么接口不能让用户传 API Key？
​        因为这个项目的 API 是后端服务。后端统一管理密钥更安全，也便于后续做权限、审计和多 provider 配置。
​        本章先不做什么：
​        本章不把 LLMService 接到会话消息发送流程。现在只是先确认模型客户端可以独立工作。

### 15.6.8 定义 API Schema
​        创建 `api/app/schemas/llm.py`：

```Python
from pydantic import BaseModel, Field


# ===================== 第1步：定义对外展示的 provider 信息 =====================
class LLMProviderResponse(BaseModel):
    name: str
    base_url: str
    api_key_env: str
    configured: bool


# ===================== 第2步：定义 LLM 配置接口响应 =====================
class LLMConfigResponse(BaseModel):
    default_provider: str
    default_model: str
    temperature: float
    max_tokens: int
    providers: list[LLMProviderResponse]


# ===================== 第3步：定义聊天请求中的消息结构 =====================
class LLMMessageRequest(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


# ===================== 第4步：定义聊天请求体 =====================
class LLMChatRequest(BaseModel):
    messages: list[LLMMessageRequest] = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


# ===================== 第5步：定义聊天响应体 =====================
class LLMChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: dict | None = None
```

​        这段代码在流程中的位置：

```Plain
浏览器或 curl
  |
  v
FastAPI Schema 校验
  |
  v
Route
```

​        输入和输出：
​        `LLMChatRequest` 校验请求体。
​        `LLMChatResponse` 约束响应体。
​        关键代码逐段解释：
​        `LLMProviderResponse.configured` 表示 Key 是否配置，不表示 Key 的内容。
​        `LLMMessageRequest.role` 限制只能是 `system`、`user`、`assistant`。
​        `messages` 至少要有一条。
​        `temperature` 范围是 0 到 2。
​        `max_tokens` 必须大于 0。
​        为什么这样设计：
​        请求越早校验，后面的服务代码越简单。
​        如果用户传了非法 role，应该在进入模型调用前就返回 422。

### 15.6.9 编写配置接口
​        创建 `api/app/api/routes/config.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.llm_service import LLMService
from app.schemas.common import ApiResponse
from app.schemas.llm import LLMConfigResponse

router = APIRouter(prefix="/config", tags=["config"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_llm_service() -> LLMService:
    return LLMService()


# ===================== 第2步：暴露不含密钥的 LLM 配置接口 =====================
@router.get("/llm", response_model=ApiResponse[LLMConfigResponse])
async def get_llm_config(
    service: LLMService = Depends(build_llm_service),
) -> ApiResponse[LLMConfigResponse]:
    return ApiResponse(data=LLMConfigResponse.model_validate(service.get_public_config()))
```

​        这段代码在流程中的位置：

```Plain
GET /api/config/llm
  |
  v
LLMService.get_public_config()
```

​        输入和输出：
​        配置接口没有请求体，输出的是默认模型、默认 provider、provider 列表，以及每个 provider 对应的 Key 是否已经配置。它返回的是 `configured`，不是密钥。后续设置页面可以用这个接口判断当前运行环境是否可调用模型，同时不会泄露任何真实凭据。
​        为什么这样设计：
​        后续前端设置面板需要知道当前 LLM 配置状态。
​        但是这个接口不能返回真实 API Key。
​        小白最容易困惑的点：
​        `configured: false` 不代表配置文件坏了。
​        它只表示当前环境变量里没有 `LLM_API_KEY`。

### 15.6.10 编写聊天接口
​        创建 `api/app/api/routes/llm.py`：

```Python
from fastapi import APIRouter, Depends

from app.application.llm_service import LLMService
from app.domain.llm.entities import LLMMessage
from app.schemas.common import ApiResponse
from app.schemas.llm import LLMChatRequest, LLMChatResponse

router = APIRouter(prefix="/llm", tags=["llm"])


# ===================== 第1步：创建应用服务依赖 =====================
def build_llm_service() -> LLMService:
    return LLMService()


# ===================== 第2步：接收聊天请求并调用 LLMService =====================
@router.post("/chat", response_model=ApiResponse[LLMChatResponse])
async def chat(
    payload: LLMChatRequest,
    service: LLMService = Depends(build_llm_service),
) -> ApiResponse[LLMChatResponse]:
    result = await service.chat(
        messages=[
            LLMMessage(role=message.role, content=message.content)
            for message in payload.messages
        ],
        provider=payload.provider,
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    # LLMChatResult 使用了 slots=True，没有 __dict__。
    # 显式映射字段可以避免运行时错误，也能让响应结构更清楚。
    return ApiResponse(
        data=LLMChatResponse(
            content=result.content,
            model=result.model,
            provider=result.provider,
            usage=result.usage,
        )
    )
```

​        这段代码在流程中的位置：

```Plain
POST /api/llm/chat
  |
  v
LLM Schema 校验
  |
  v
LLMService.chat()
  |
  v
OpenAICompatibleClient.chat()
```

​        输入和输出：
​        输入示例：

```JSON
{
  "messages": [
    {"role": "user", "content": "你好"}
  ]
}
```

​        输出示例：

```JSON
{
  "provider": "openai_compatible",
  "model": "gpt-4o-mini",
  "content": "你好！有什么可以帮你？",
  "usage": {}
}
```

​        关键代码逐段解释：
​        路由层收到 Pydantic 请求对象 `payload`。
​        然后把请求消息转换成领域对象 `LLMMessage`。
​        再调用 `LLMService.chat()`。
​        最后把领域结果转换成响应模型。
​        为什么这样设计：
​        路由层负责 HTTP 输入输出。
​        Service 层负责业务编排。
​        Client 层负责第三方 HTTP 调用。
​        这三层分开以后，后续把 LLM 接到会话任务时，可以直接复用 `LLMService`。

### 15.6.11 注册路由并更新 Dockerfile
​        打开 `api/app/api/router.py`：

```Python
from fastapi import APIRouter

from app.api.routes import config, files, llm, sessions, status

api_router = APIRouter()
api_router.include_router(status.router)
api_router.include_router(sessions.router)
api_router.include_router(files.router)
api_router.include_router(config.router)
api_router.include_router(llm.router)
```

​        打开 `api/Dockerfile`，把配置目录放进镜像：

```Dockerfile
COPY app ./app
COPY config ./config
COPY alembic.ini ./
```

​        为什么要改 Dockerfile？
​        本地运行 API 时，`config/llm.yaml` 在项目目录里。
​        Docker 构建时，如果不把 `config` 放进镜像，容器运行后会找不到：

```Plain
config/llm.yaml
```

​        这种错误通常会在接口请求时才暴露，所以本章必须提前处理。

## 15.7 关键理解
​        本章最重要的是理解配置分层：

```Plain
YAML
  |
  +-- 非敏感结构化配置
  +-- provider、model、base_url、temperature

.env
  |
  +-- 敏感配置
  +-- LLM_API_KEY
```

​        第二个重点是调用分层：

```Plain
Route       处理 HTTP
Service     编排业务
Client      调用模型服务商
Config      提供模型配置
```

​        第三个重点是 OpenAI 兼容。
​        很多模型服务商会提供类似 OpenAI 的接口格式：

```Plain
POST /chat/completions
Authorization: Bearer <api_key>
messages: [{role, content}]
```

​        只要符合这个格式，本章的客户端就有机会复用。

## 15.8 技术难点与亮点
​        本章的难点主要在配置边界和错误表达。YAML 和环境变量必须分工清楚，配置接口不能泄露真实 API Key；provider 返回的 HTTP 错误也要转换成项目统一异常，而不是把第三方响应原样丢给前端。`base_url` 与 `/chat/completions` 的拼接也很容易出错，一旦地址多一个或少一个路径段，模型调用就会变成 404。
​        项目亮点在于 LLM 调用能力被独立成模块，而不是直接写进会话接口。配置查询接口为后续设置面板做准备，OpenAI 兼容客户端也为接入多个 provider 留出空间。当前实现不绑定会话模块，后续既可以服务普通聊天，也可以被 Agent Runner、Planner 或工具总结器复用。

## 15.9 面试考点
​        面试里可以围绕五个问题展开：为什么 API Key 不应该写进 YAML，为什么配置接口只能返回 `configured` 而不能返回真实 Key，OpenAI 兼容接口的基本请求结构是什么，`Route`、`Service`、`Client` 各自负责什么，以及没有 API Key 时应该返回什么错误。这里要强调的是配置安全和调用分层，而不是只说“我封装了一个 httpx 请求”。

## 15.10 运行验证
​        下面命令默认在项目根目录执行。

### 15.10.1 检查后端代码

```Bash
cd api
uv run python -m compileall app
```

​        预期没有语法错误。

### 15.10.2 检查配置能否加载

```Bash
uv run python -c "from app.application.llm_service import LLMService; print(LLMService().get_public_config())"
```

​        如果没有配置 `LLM_API_KEY`，预期能看到：

```Plain
'configured': False
```

### 15.10.3 启动 API
​        本章只修改后端。

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose build --pull=false api
docker compose up -d api nginx
```

​        如果网络不稳定，可以只重试：

```Bash
docker compose build --pull=false api
```

### 15.10.4 验证配置接口

```Bash
curl http://localhost:8088/api/config/llm
```

​        没有配置 Key 时，预期返回：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "default_provider": "openai_compatible",
    "default_model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_tokens": 1024,
    "providers": [
      {
        "name": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "LLM_API_KEY",
        "configured": false
      }
    ]
  }
}
```

### 15.10.5 验证没有 Key 时的聊天接口

```Bash
curl -X POST http://localhost:8088/api/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好"}]}'
```

​        没有配置 `LLM_API_KEY` 时，预期返回：

```JSON
{
  "code": 500,
  "message": "LLM api key is not configured: LLM_API_KEY",
  "data": null
}
```

​        这表示后端配置检查生效了。

### 15.10.6 配置 Key 后真实调用
​        如果你有 OpenAI 兼容服务的 API Key，可以在 `.env` 中填写：

```Plain
LLM_API_KEY=你的真实密钥
```

​        如果使用的不是 OpenAI 官方地址，需要修改：

```Plain
api/config/llm.yaml
```

​        例如把 `base_url` 改成你的服务商地址。
​        然后重新启动 API：

```Bash
docker compose up -d api nginx
```

​        再次调用：

```Bash
curl -X POST http://localhost:8088/api/llm/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"用一句话介绍 AI Agent"}]}'
```

​        如果配置正确，预期 `data.content` 会出现模型返回内容。

## 15.11 常见问题

### 15.11.1 `GET /api/config/llm` 返回配置文件不存在怎么办
​        先检查 `LLM_CONFIG_PATH` 是否指向 `config/llm.yaml`，再确认 Dockerfile 已经把 `config` 目录复制进镜像。这个错误通常不是接口逻辑问题，而是容器运行时找不到配置文件。

### 15.11.2 `docker compose build api` 报 `ghcr.io/astral-sh/uv:0.11.15` 的 `EOF` 怎么办
​        这是 Docker 读取 uv 基础镜像元数据时网络中断，不是项目代码错误。可以改用 `docker compose build --pull=false api`，优先使用本机已有镜像缓存。如果进入 `uv sync` 后下载依赖很慢，可以继续等待或重试；依赖层构建成功后，后续会被 Docker 缓存。

### 15.11.3 配置接口里 `configured` 是 `false` 怎么办
​        这说明后端运行环境里没有 `LLM_API_KEY`，或者 API 容器没有读取到更新后的 `.env`。在 `.env` 填写密钥后，需要重启 API，让环境变量进入进程。

### 15.11.4 聊天接口返回 `LLM provider returned HTTP 401` 怎么办
​        通常是 API Key 错误，或者服务商不接受当前 Key。此时应该检查运行环境里的 `LLM_API_KEY`，而不是检查 YAML 文件，因为 YAML 里只保存环境变量名称。

### 15.11.5 聊天接口返回 `LLM provider returned HTTP 404` 怎么办
​        通常是 `base_url` 配错，或者服务商不是 OpenAI 兼容路径。客户端会自动拼接 `/chat/completions`，所以 YAML 中的 `base_url` 应该指向兼容接口的根路径，例如 `https://api.openai.com/v1`。

### 15.11.6 为什么本章不直接接入会话发送消息
​        本章先把模型配置和客户端打通。会话任务、Agent 思考、流式事件和调用记录都会带来新的状态管理问题，后续章节会逐步接入。这里先让 LLM 调用本身独立可验证。

## 15.12 本章小结
​        本章完成了 LLM 调用基础。后端新增 YAML 配置文件、LLM 配置加载器、领域对象、OpenAI 兼容客户端和 LLM 应用服务，并暴露了配置查询接口和最小聊天调用接口。真实 API Key 只从环境变量读取，配置接口只返回 `configured` 状态，不返回密钥本身。
​        从这一章开始，项目已经具备调用模型的基础能力。它还没有进入会话和 Agent 执行链路，但模型配置、密钥检查、客户端调用和错误转换已经独立成立。

## 15.13 下一章预告
​        第 16 章会进入 Agent 思维模型，通过小例子讲清楚普通 ChatBot、CoT、ReAct、任务拆解和工具调用之间的区别。
