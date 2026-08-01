# 第二十七章. BrowserTool 浏览器工具成形

## 27.1 本章目标
​        学完本章后，你将能够：
​        第 26 章已经证明 Sandbox 可以启动 Chromium、打开网页并截图，但那仍然只是底层 Browser API。真实 Agent 不应该让用户手动调用 `/sandbox-api/browser/page/navigate`，而应该在执行任务时，把“打开网页”和“截图观察”当作工具能力自然调用。
​        学完本章后，你应该能区分 Browser API 和 BrowserTool：前者是 Sandbox 暴露的底层浏览器控制接口，后者是主 API 注册给 Agent 的工具封装。本章会在主 API 中封装 `SandboxBrowserClient`，把浏览器状态、打开网页、截图和关闭会话注册成工具，并让 ReAct 执行步骤在识别到网页访问或截图意图时触发这些工具。前端事件记录也会开始展示工具参数、工具输出和浏览器截图，让浏览器能力进入真实 AI 对话执行过程。

## 27.2 最终效果
​        本章结束后，主 API 的工具注册表会新增：

```Plain
browser_status
browser_open
browser_screenshot
browser_close
```

​        执行计划时，如果步骤里出现：

```Plain
访问网页
打开网站
浏览器
截图
```

​        ReAct 执行服务会优先调用 BrowserTool。
​        前端事件记录不再只显示 `tool_called`，而是会展示：

```Plain
工具名称
调用参数
工具输出
浏览器截图预览
```

​        本章完成后的调用链路是：

```Plain
计划步骤
  |
  v
ReActAgentService
  |
  v
BrowserTool
  |
  v
SandboxBrowserClient
  |
  v
Sandbox Browser API
  |
  v
Playwright / Chromium
  |
  v
tool_called 事件
  |
  v
前端事件记录展示
```

## 27.3 本章要解决的问题
​        第 26 章已经让 Sandbox 可以启动浏览器、打开网页和截图。
​        但那还只是 Sandbox API：

```Plain
curl /sandbox-api/browser/page/navigate
curl /sandbox-api/browser/page/screenshot
```

​        真实 Agent 不应该让用户手动调这些接口。Agent 应该在执行任务时，把浏览器能力当成工具：

```Plain
用户任务
  |
  v
计划步骤
  |
  v
Agent 判断需要打开网页
  |
  v
调用 browser_open
  |
  v
生成 tool_called 事件
  |
  v
前端展示工具调用结果
```

​        所以本章把 Browser API 封装成 BrowserTool，并让工具结果进入前端事件记录。

## 27.4 本章技术方案
​        本章继续沿用已有工具协议：

```Plain
ToolDefinition
ToolParameter
AgentTool
ToolRegistry
ToolCallResult
```

​        新增一层 `SandboxBrowserClient`：

```Plain
BrowserTool
  |
  v
SandboxBrowserClient
  |
  v
Sandbox Browser API
```

​        这样 BrowserTool 不需要导入 Playwright，也不需要知道浏览器运行在哪个容器。
​        前端不新增孤立演示页面，而是在现有事件记录中增强 `tool_called` 展示。
​        本章暂时不做这些内容：
​        本章不会做完整元素识别，也不会加入点击、输入、滚动工具。VNC 可视化、多标签页管理和统一工具预览面板的最终形态，也会继续留到后续章节。这里先把 Browser API 变成 Agent 可调用的工具，并让工具结果能进入事件记录。

## 27.5 新增和修改的文件

```Plain
README.md
docs/course/chapters/27-browser-tool.md
api/app/infrastructure/sandbox/browser_client.py
api/app/infrastructure/agent_tools/sandbox_browser.py
api/app/infrastructure/agent_tools/builtin.py
api/app/application/react_agent_service.py
ui/app/components/event-timeline.tsx
```

## 27.6 实施步骤
### 27.6.1 封装 SandboxBrowserClient
​        创建 `api/app/infrastructure/sandbox/browser_client.py`：

```Python
from typing import Any

import httpx

from app.core.exceptions import AppException


class SandboxBrowserClient:
    """主 API 访问 Sandbox Browser API 的同步客户端。

    BrowserTool 不直接依赖 Playwright，只通过这个 client 调用 Sandbox。
    这样浏览器进程仍然被限制在隔离容器里。
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ===================== 第1步：浏览器会话状态和生命周期 =====================
    def status(self) -> dict[str, Any]:
        return self._request("GET", "/browser/status")

    def start(self) -> dict[str, Any]:
        return self._request("POST", "/browser/session")

    def close(self) -> dict[str, Any]:
        return self._request("DELETE", "/browser/session")

    # ===================== 第2步：页面操作 =====================
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/navigate",
            json={"url": url, "wait_until": wait_until},
        )

    def page_info(self) -> dict[str, Any]:
        return self._request("GET", "/browser/page")

    def screenshot(self, full_page: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/browser/page/screenshot",
            json={"full_page": full_page},
        )

    # ===================== 第3步：统一处理 Sandbox 响应 =====================
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise AppException(
                message=f"sandbox browser request failed: {error}",
                code=502,
                status_code=502,
            ) from error

        try:
            payload = response.json()
        except ValueError as error:
            raise AppException(
                message="sandbox browser returned non-json response",
                code=502,
                status_code=502,
            ) from error

        if response.status_code >= 400 or payload.get("code") != 200:
            raise AppException(
                message=str(payload.get("message") or "sandbox browser request failed"),
                code=int(payload.get("code") or response.status_code),
                status_code=response.status_code,
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppException(
                message="sandbox browser returned invalid data",
                code=502,
                status_code=502,
            )
        return data
```

#### 27.6.1.1 这段代码在流程中的位置
​        `SandboxBrowserClient` 是主 API 到 Sandbox Browser API 的适配层。
​        它的作用类似第 23 章的 `SandboxFileClient` 和第 24 章的 `SandboxShellClient`。
​        BrowserTool 不直接请求 `httpx`，而是通过 client 调用：

```Plain
browser_open
  |
  v
SandboxBrowserClient.navigate()
  |
  v
POST /sandbox-api/browser/page/navigate
```

#### 27.6.1.2 为什么这样设计
​        这样可以把错误处理集中在一个地方。
​        如果 Sandbox 返回非 JSON、HTTP 500、业务 code 不是 200，client 会统一转成 `AppException`。上层工具不用重复写这些判断。

### 27.6.2 注册 BrowserTool
​        创建 `api/app/infrastructure/agent_tools/sandbox_browser.py`：

```Python
import json

from app.core.config import settings
from app.domain.agent_core.tools import (
    AgentTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from app.infrastructure.sandbox.browser_client import SandboxBrowserClient


def build_sandbox_browser_client() -> SandboxBrowserClient:
    """根据主 API 配置创建 Sandbox Browser 客户端。"""

    return SandboxBrowserClient(
        base_url=settings.sandbox_api_base_url,
        timeout_seconds=settings.sandbox_api_timeout_seconds,
    )


def register_sandbox_browser_tools(
    registry: ToolRegistry,
    client: SandboxBrowserClient | None = None,
) -> None:
    """把 Sandbox 浏览器能力注册成 Agent 可调用工具。

    这些工具不直接控制本机浏览器，而是转发到 Sandbox Browser API。
    """

    browser_client = client or build_sandbox_browser_client()

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_status",
                description="查看 Sandbox 浏览器会话状态、当前页面和视口信息。",
                parameters=[],
            ),
            handler=lambda: _format_status(browser_client.status()),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_open",
                description="在 Sandbox 浏览器中打开一个网页，并返回页面地址和标题。",
                parameters=[
                    ToolParameter(
                        name="url",
                        type="string",
                        description="要打开的网页地址，例如 https://example.com。",
                    )
                ],
            ),
            handler=lambda url: _format_page(browser_client.navigate(url=url)),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_screenshot",
                description="截取当前浏览器页面，返回图片信息和 base64 数据。",
                parameters=[
                    ToolParameter(
                        name="full_page",
                        type="boolean",
                        description="是否截取完整页面，默认 true。",
                        required=False,
                    )
                ],
            ),
            handler=lambda full_page=True: _format_screenshot(
                browser_client.screenshot(full_page=_to_bool(full_page))
            ),
        )
    )

    registry.register(
        AgentTool(
            definition=ToolDefinition(
                name="browser_close",
                description="关闭 Sandbox 浏览器会话，释放浏览器资源。",
                parameters=[],
            ),
            handler=lambda: _format_session(browser_client.close()),
        )
    )


def _format_status(data: dict) -> str:
    return "\n".join(
        [
            f"浏览器启用：{data.get('enabled')}",
            f"会话已启动：{data.get('session_started')}",
            f"当前地址：{data.get('current_url') or '-'}",
            f"页面标题：{data.get('page_title') or '-'}",
            f"视口：{data.get('viewport_width')}x{data.get('viewport_height')}",
        ]
    )


def _format_page(data: dict) -> str:
    return "\n".join(
        [
            f"页面已打开：{data.get('url')}",
            f"页面标题：{data.get('title') or '-'}",
        ]
    )


def _format_screenshot(data: dict) -> str:
    # 截图结果使用 JSON，前端事件面板可以解析后直接显示图片。
    return json.dumps(
        {
            "kind": "browser_screenshot",
            "mime_type": data.get("mime_type"),
            "base64_data": data.get("base64_data"),
            "size": data.get("size"),
        },
        ensure_ascii=False,
    )


def _format_session(data: dict) -> str:
    return f"{data.get('message')} status={data.get('status')}"


def _to_bool(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"false", "0", "no"}
    return bool(value)
```

​        打开 `api/app/infrastructure/agent_tools/builtin.py`，注册 BrowserTool：

```Python
from app.infrastructure.agent_tools.sandbox_browser import register_sandbox_browser_tools
```

​        在 `build_builtin_tool_registry()` 里加入：

```Python
register_sandbox_browser_tools(registry)
```

#### 27.6.2.1 这段代码在流程中的位置
​        这一步把浏览器能力加入工具注册表。
​        注册后，`GET /api/agent-core/tools` 会看到 `browser_open`、`browser_screenshot` 等工具，ReAct 执行服务也可以通过 `self.registry.get("browser_open")` 找到工具。

#### 27.6.2.2 为什么截图结果用 JSON 字符串
​        当前工具协议的 `ToolCallResult.output` 是字符串。
​        为了让前端能识别截图，本章把截图结果格式化成 JSON 字符串：

```JSON
{
  "kind": "browser_screenshot",
  "mime_type": "image/png",
  "base64_data": "...",
  "size": 12345
}
```

​        这不是最终工具事件协议，但足够支撑本章的前端图片预览。第 29 章会把工具预览面板统一重构。

### 27.6.3 让 ReAct 步骤触发 BrowserTool
​        打开 `api/app/application/react_agent_service.py`，新增 import：

```Python
from urllib.parse import urlparse
```

​        在 `_execute_step()` 中，把计划、步骤和序号一起传给工具选择方法：

```Python
tool_result = self._call_tool_for_step(plan=plan, step=step, index=index)
```

​        在 `_call_tool_for_step()` 中，把浏览器判断放在其他教学工具之前：

```Python
def _call_tool_for_step(self, plan: dict, step: dict, index: int) -> dict:
    """根据计划目标和步骤内容选择并调用一个内置工具。

    这里同时读取 plan.goal 和 step 文本，是为了避免计划步骤被概括后
    丢失用户原始任务里的“访问网页、截图”等关键信息。
    """

    goal = str(plan.get("goal", ""))
    title = str(step.get("title", ""))
    description = str(step.get("description", ""))
    expected_output = str(step.get("expected_output", ""))
    step_text = f"{title} {description} {expected_output}".strip()
    text = f"{goal} {step_text}".strip()

    if self._needs_browser_screenshot(text):
        # 同一个任务里同时出现“访问”和“截图”时，先打开页面，再截图。
        # 这样即使规划步骤比较抽象，也能稳定产生 browser_open 和 browser_screenshot。
        if index == 1 or self._needs_browser_open(step_text):
            tool = self.registry.get("browser_open")
            arguments = {"url": self._extract_url(text)}
        else:
            tool = self.registry.get("browser_screenshot")
            arguments = {"full_page": True}
    elif self._needs_browser_open(text):
        tool = self.registry.get("browser_open")
        arguments = {"url": self._extract_url(text)}
    elif "拆" in title or "步骤" in title or "计划" in title:
        tool = self.registry.get("draft_plan")
        arguments = {"task": text}
```

​        继续新增三个辅助方法：

```Python
def _needs_browser_open(self, text: str) -> bool:
    """判断当前步骤是否需要打开网页。"""

    keywords = ["网页", "网站", "浏览器", "访问", "打开", "页面"]
    return any(keyword in text for keyword in keywords)

def _needs_browser_screenshot(self, text: str) -> bool:
    """判断当前步骤是否需要对页面截图。"""

    keywords = ["截图", "截屏", "页面截图", "观察页面"]
    return any(keyword in text for keyword in keywords)

def _extract_url(self, text: str) -> str:
    """从计划步骤中提取 URL，没有 URL 时使用稳定示例站点。

    本章先用简单规则，后续会由 LLM 结构化输出工具参数。
    """

    for token in text.split():
        clean_token = token.strip("，。,.!?！？、()（）")
        parsed = urlparse(clean_token)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return clean_token
    return "https://example.com"
```

#### 27.6.3.1 这段代码在流程中的位置
​        第 19 章的 ReAct 执行服务本来会根据步骤内容选择教学工具。
​        本章把浏览器判断放在最前面。这样只要计划目标或步骤内容包含“网页、网站、浏览器、访问、截图”等关键词，就会触发 BrowserTool。
​        执行计划时，每个步骤结束后都会提交一次事件。这样前端轮询事件列表时，可以逐步看到：

```Plain
step_started -> tool_called -> step_completed
```

​        如果某个浏览器工具超时或失败，错误事件会带上当前 `step_id`，前端就能把对应步骤从 `running` 改成 `failed`，而不是一直停在运行中。

#### 27.6.3.2 为什么本章用简单规则
​        现在还没有完整的 LLM 工具参数生成。
​        所以本章先用关键词和 URL 提取规则，让浏览器工具进入真实执行链路。后续 LLM 结构化输出成熟后，会由模型明确生成：

```JSON
{"tool_name":"browser_open","arguments":{"url":"https://example.com"}}
```

### 27.6.4 增强前端事件记录
​        打开 `ui/app/components/event-timeline.tsx`，在事件时间后加入：

```TypeScript
<EventPayload event={event} />
```

​        然后新增 `EventPayload`：

```TypeScript
function EventPayload({ event }: { event: SessionEventItem }) {
  if (event.type !== "tool_called") {
    return null;
  }

  const toolName = getString(event.payload.tool_name);
  const output = getString(event.payload.output);
  const screenshot = parseScreenshot(output);

  return (
    <div className="mt-2 grid gap-2 text-xs text-slate-600">
      <div>
        <span className="font-medium text-slate-700">工具：</span>
        {toolName || "-"}
      </div>
      <pre className="max-h-24 overflow-auto rounded-md bg-white p-2 text-[11px] leading-5 text-slate-600">
        {JSON.stringify(event.payload.arguments ?? {}, null, 2)}
      </pre>
      {screenshot ? (
        <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
          <img
            alt="浏览器截图"
            className="max-h-48 w-full object-contain"
            src={`data:${screenshot.mime_type};base64,${screenshot.base64_data}`}
          />
          <div className="border-t border-slate-200 px-2 py-1 text-[11px] text-slate-500">
            {screenshot.mime_type} · {screenshot.size} bytes
          </div>
        </div>
      ) : (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded-md bg-white p-2 text-[11px] leading-5 text-slate-600">
          {output || "<no output>"}
        </pre>
      )}
    </div>
  );
}
```

​        再新增截图解析工具：

```TypeScript
type ScreenshotPayload = {
  kind: "browser_screenshot";
  mime_type: string;
  base64_data: string;
  size: number;
};

function parseScreenshot(value: string): ScreenshotPayload | null {
  try {
    const payload = JSON.parse(value) as Partial<ScreenshotPayload>;
    if (
      payload.kind === "browser_screenshot" &&
      typeof payload.mime_type === "string" &&
      typeof payload.base64_data === "string" &&
      typeof payload.size === "number"
    ) {
      return payload as ScreenshotPayload;
    }
  } catch {
    return null;
  }
  return null;
}

function getString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
```

#### 27.6.4.1 这段代码在流程中的位置
​        第 09 章的事件记录只能显示事件类型。
​        本章开始展示工具调用详情：

```Plain
tool_called
  |
  +-- tool_name
  +-- arguments
  +-- output
  +-- browser screenshot
```

​        这让浏览器工具不再只是接口验证，而是进入了对话执行过程。

#### 27.6.4.2 为什么这里还不是最终工具预览面板
​        本章先在事件记录里展示工具详情，是为了尽早让浏览器工具结果可见。
​        第 29 章会集中重构工具预览面板，把 File、Shell、Browser、Search 等工具输出统一展示。

## 27.7 关键理解
​        本章最重要的是理解 Browser API 和 BrowserTool 的区别。

```Plain
Browser API：Sandbox 提供的底层浏览器控制接口
BrowserTool：Agent 可以调用的工具封装
```

​        第 26 章解决的是“浏览器能不能被控制”。
​        第 27 章解决的是“Agent 能不能把浏览器当工具调用，并让前端看到结果”。
​        第二个重点是理解本章的前端收敛方向。
​        本章没有新增独立浏览器演示页，而是增强事件记录。因为浏览器动作应该属于当前任务执行过程，而不是孤立按钮。

## 27.8 技术难点与亮点
​        本章的技术难点在于分层。BrowserTool 不能直接导入 Playwright，也不能在主 API 里启动浏览器进程；它必须通过 `SandboxBrowserClient` 调用 Sandbox Browser API，继续保持浏览器运行环境隔离。
​        截图结果也比普通文本工具复杂。它本质上是二进制图片，本章暂时把它编码成 JSON 字符串放进 `ToolCallResult.output`，前端再尝试解析这个字符串并生成 `data:image/png;base64,...` 预览。这个方案不是最终协议，但能让截图尽早进入事件记录。
​        ReAct 侧同样有过渡性设计。当前还没有完整的 LLM 结构化工具参数生成，所以本章先用关键词和 URL 提取规则触发浏览器工具。项目亮点在于浏览器能力已经进入 Agent 工具体系，`tool_called` 事件开始展示真实工具参数和结果，前端也不再新增孤立演示 UI，而是把能力合并进工作台事件记录。

## 27.9 面试考点
​        面试里问到这一章，可以先说明 Browser API 和 BrowserTool 的层次差异。Browser API 属于 Sandbox，是底层浏览器控制能力；BrowserTool 属于主 API 的工具体系，是 Agent 能调用的封装。主 API 不应该直接启动 Playwright，因为浏览器进程、页面状态和截图都属于执行环境，应该留在 Sandbox。
​        工具调用结果进入事件流，是为了让用户能看到 Agent 执行过程中到底调用了什么工具、传了什么参数、拿到了什么结果。截图这种二进制结果可以先编码成 base64，再由前端拼成 data URL 展示。后续更成熟的做法，是把截图保存成文件对象，再在工具预览面板中引用。
​        本章使用规则选择工具，是因为当前还没有完整 LLM 结构化工具调用。等后续工具参数生成稳定后，模型应该直接给出 `tool_name` 和 `arguments`，而不是依赖关键词判断。

## 27.10 运行验证
​        下面命令默认在项目根目录执行：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

### 27.10.1 编译和类型检查

```Bash
cd api
uv run python -m compileall app

cd ../ui
pnpm typecheck
```

### 27.10.2 启动服务
​        如果第 26 章已经构建过 Sandbox 镜像，可以直接启动：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
docker compose up -d sandbox api ui nginx
```

​        如果还没有构建过包含 Chromium 的 Sandbox 镜像，先执行：

```Bash
docker compose build sandbox
```

​        再启动：

```Bash
docker compose up -d sandbox api ui nginx
```

### 27.10.3 验证 Browser API

```Bash
curl http://localhost:8088/sandbox-api/browser/status
curl -X POST http://localhost:8088/sandbox-api/browser/session
curl -X POST http://localhost:8088/sandbox-api/browser/page/navigate \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

​        预期导航接口返回页面标题：

```Plain
Example Domain
```

### 27.10.4 验证工具列表

```Bash
curl http://localhost:8088/api/agent-core/tools
```

​        预期能看到：

```Plain
browser_status
browser_open
browser_screenshot
browser_close
```

### 27.10.5 验证前端事件展示
​        访问：

```Plain
http://localhost:8088
```

​        创建一个会话，发送任务。第一次验证建议使用稳定、页面很轻的 `example.com`：

```Plain
请访问 https://example.com 并截图观察页面
```

​        `example.com` 不是假地址，它是 IANA 保留的真实示例域名，页面很轻，适合先确认 BrowserTool 链路是否打通。
​        基础链路正常后，再用真实网站验证浏览器工具：

```Plain
请访问 https://www.python.org 并截图观察页面
```

​        如果这一步也正常，再测试 `https://baidu.com` 这类资源更多、网络波动更明显的网站。
​        然后按顺序操作：

```Plain
1. 点击右侧计划区域的生成按钮
2. 等事件记录出现 plan_created
3. 点击执行按钮
4. 等执行任务状态变成 succeeded
```

​        预期事件记录中能看到：

```Plain
step_started
tool_called
工具：browser_open
调用参数：{"url":"https://example.com"}
工具输出：页面已打开

tool_called
工具：browser_screenshot
调用参数：{"full_page":true}
浏览器截图预览

step_completed
task_done
```

​        如果页面里只看到 `message_created`，说明当前还只是“消息已保存”，计划还没有生成或还没有执行。先确认是否已经看到 `plan_created`，再点击执行按钮。
​        如果步骤长时间停在 `running`，通常是浏览器工具还没有返回。优先用 `https://example.com` 验证基础链路，再用 `https://www.python.org` 验证真实网站；如果只在 `https://baidu.com` 上卡住，说明更可能是容器网络、目标站点加载速度或浏览器导航超时问题。

## 27.11 常见问题

### 27.11.1 工具列表没有 browser 工具怎么办？
​        先确认 `api/app/infrastructure/agent_tools/builtin.py` 中已经调用 `register_sandbox_browser_tools(registry)`。如果代码已经加入，但接口列表里仍然没有 `browser_open` 或 `browser_screenshot`，说明 API 进程还没有加载最新代码。
​        Docker 环境里需要重新构建或重启 API。执行 `docker compose build api`，再执行 `docker compose up -d --force-recreate api nginx`，然后重新请求 `/api/agent-core/tools`。

### 27.11.2 浏览器工具调用返回 502 怎么办？
​        502 通常说明主 API 调用 Sandbox Browser API 失败。先确认 `curl http://localhost:8088/sandbox-api/browser/status` 是否正常，如果这个接口都失败，问题就在 Sandbox、Chromium 依赖或 Nginx 到 Sandbox 的路径上。
​        如果 Sandbox Browser API 正常，再看 API 容器日志和 `SANDBOX_API_BASE_URL`。主 API 在 Compose 网络里应该访问 `http://sandbox:8100/api`，而不是 `localhost:8100`。

### 27.11.3 页面只看到 `message_created`，没有 `tool_called` 怎么办？
​        `message_created` 只表示用户消息已经保存，还没有进入计划执行。继续点击计划区域的生成按钮，看到 `plan_created` 后，再点击执行按钮。只有执行计划时，ReAct 才会按步骤调用工具并写入 `tool_called` 事件。
​        如果已经生成并执行计划，事件仍然没有变化，就重新构建并重启 API 和 UI：`docker compose build api ui`，然后执行 `docker compose up -d --force-recreate api ui nginx`。

### 27.11.4 计划第一步一直显示 `running` 怎么办？
​        这通常表示当前工具调用还没有返回，或者浏览器导航已经失败但旧版本前端没有把失败事件映射到步骤状态。先查看后台任务区域是否显示 `failed`，再查看事件记录里是否有 `task_error`。
​        验证时优先使用 `https://example.com`，它页面轻、加载稳定，适合确认基础链路。基础链路正常后，再用 `https://www.python.org` 验证真实网站。如果只在资源更多的网站上卡住，更可能是容器网络、目标站加载速度或浏览器导航超时问题。

### 27.11.5 页面没有显示截图怎么办？
​        先确认事件 payload 里的 `tool_name` 是否为 `browser_screenshot`，再确认 `output` 是否是包含 `kind: browser_screenshot` 的 JSON 字符串。前端只有解析到这个结构，才会把 base64 数据渲染成图片。
​        如果后端事件正常，但页面仍然是旧展示方式，说明 UI 容器没有加载最新代码。重新构建 UI：`docker compose build ui`，然后执行 `docker compose up -d --force-recreate ui nginx`。

### 27.11.6 为什么本章还没有点击、输入、滚动？
​        本章先把浏览器作为工具接入 Agent 执行链路，重点是工具注册、ReAct 触发和事件展示。点击、输入、滚动需要元素定位、页面状态提取和更完整的动作参数，这些内容比打开页面和截图复杂得多。
​        等基础链路稳定后，后续章节再继续扩展浏览器动作，否则一开始就把所有浏览器操作塞进来，会让 BrowserTool 的边界变得难以验证。

## 27.12 本章小结
​        本章完成了 BrowserTool 的第一版。主 API 新增了 `SandboxBrowserClient`，并注册了 `browser_status`、`browser_open`、`browser_screenshot` 和 `browser_close` 这些浏览器工具。ReAct 执行服务也开始根据计划目标和步骤内容，触发浏览器打开网页或截图。
​        前端事件记录现在可以展示工具名称、调用参数、普通文本输出和浏览器截图。从这一章开始，浏览器能力不再只是 Sandbox API，而是进入了 Agent 工具体系，也开始真正出现在用户可观察的执行流里。

## 27.13 下一章预告
​        第 28 章会进入 VNC 远程桌面，让浏览器不只可以截图，还能通过前端远程桌面可视化观察。
