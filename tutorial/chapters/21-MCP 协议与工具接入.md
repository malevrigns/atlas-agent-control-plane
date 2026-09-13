# 第二十一章. MCP 协议与工具接入

前二十章把内部工具一条条接进工作台：读文件、跑 Shell、开浏览器、搜网页。那些工具都住在仓库里，参数形状、错误文案、事件名字都由我们自己定。这样写起来痛快，接第三个、第四个外部系统时就会开始疼。每个系统一套私有 client，一套注册表，一套输出解析，主 API 会慢慢变成集成脚本堆。

MCP，Model Context Protocol，要挡的就是这件事。外部服务自己跑一个 Server，按协议声明 tools、resources、prompts；Host 通过 Client 去发现、去调用。AtlasAgent 当 Host，不必把别人的能力抄进自己的仓库。代码在 `backend/api-ts` 和 `frontend/web`。语言是 TypeScript。不要再新建 Python 服务。

![工具协议把外部能力收成同一张卡片](../assets/ch12-tools.jpg)

## 三个角色，不要混成一句话

Host 是 AtlasAgent 自己：会话、计划、事件、工作台都在这里。Client 是 Host 里那一层连接器，负责打开传输、发 JSON-RPC、把 Server 的能力翻译成本地能懂的东西。Server 在墙的另一边，可能是 stdio 拉起的本地进程，也可能是 Streamable HTTP 上的远程服务。它暴露的不是「一个函数」，而是三类能力。tools 是可调用动作，resources 是可读取的上下文，prompts 是可复用的提示词模板。

调用顺序也固定。先 `tools/list`，看 Server 声明了什么、参数 schema 长什么样；再由 Host 决定调哪一个；然后 `tools/call`，把参数送过去，收回一段 content。这段 content 不该直接泼到模型提示词里当秘密推理，它应该像 `search_web` 那样变成可观察的工具输出：有名字、有参数、有结果、能写进会话事件。

笔者第一次读 MCP 文档时，也急着去装某个现成 Server。装完才发现分不清：连不上是传输的事，参数对不上是 schema 的事，前端没卡片是 Host 没把结果写成事件。角色没分开，日志再多也帮不上忙。

stdio 能跑任意命令，所以默认必须关掉，只放行白名单里的 argv 签名。HTTP 宿主同样要允许列表。允许列表应是精确字符串，不要 `uvx *`。工具一旦挂上，调用仍要走同一道门：风险、超时、审计。MCP 不是后门。

## 现行运行时诚实说：协议位在，Client 还没有

工作台右侧已经有一块「MCP 工具」面板，文件在 `frontend/web/app/components/mcp-panel.tsx`。它会去拉两个接口：`GET /api/mcp/servers` 和 `GET /api/mcp/tools`。前端封装很薄，只负责把信封拆开：

```ts
import { requestApi } from "./api";
import type { McpServerListData, McpToolListData } from "../types";

export function fetchMcpServers(): Promise<McpServerListData> {
  return requestApi<McpServerListData>("/api/mcp/servers");
}

export function fetchMcpTools(): Promise<McpToolListData> {
  return requestApi<McpToolListData>("/api/mcp/tools");
}
```

面板按 Server 名称、传输方式、启用状态画卡片，再按工具名称和描述画另一列。刷新按钮只是再打一遍这两个 GET。契约形状已经定了：列表走 `{ items: [...] }`，工具预览以后也能把某次 `tool_called` 认成 MCP 结果。空列表时显示空状态，不要转圈。

打开 `backend/api-ts/src/presentation/http/routes/stubs.ts` 会看到另一半真相。MCP 相关路由现在是占位，返回空列表，好让工作台不 404：

```ts
const empty = (c: { json: (body: unknown) => Response }) => c.json(ok({ items: [] }));
router.get("/mcp/servers", empty);
router.get("/mcp/tools", empty);
router.get("/mcp/concepts", empty);
```

`docs/TYPESCRIPT_RUNTIME.md` 写得很直：Tool runtime、MCP、A2A 仍在从旧实现往 TypeScript 搬。现行 Hono 进程不会拉起 stdio Server，也不会对某个 Streamable HTTP 地址做 `tools/list`。Compose 里虽然留着 `MCP_CONFIG_PATH`，控制平面读到的仍是空 `items`。这不是前端坏了，是 Host 侧的 Client 还没进 `api-ts`。

空列表也是一种协议。面板会渲染成「没有 Server」，而不是红字崩溃。读者现在就能核对：路径对不对、鉴权过不过、信封是不是 `{ code, message, data, error }`。等真正的 Client 接上，只要填进同样的 `items`，这块 UI 不用重画。

## 以后接真 Server 时，边界已经画好

内部工具和 MCP 工具最后都该落到同一套 Agent 工具协议上：一个名字，一份参数，一段可序列化的输出，一次 `tool_called` 事件。差别只在适配层。内部工具调 `backend/sandbox-ts`；MCP 工具调 Client，再把 content 压成前端认得的 JSON。ReAct 循环、右侧预览、中间时间线都不该知道对方是不是 MCP。

配置也该继续和密钥分开。Server 的名字、传输、命令或 URL 可以进 YAML；真实 token 只进环境变量。浏览器设置页可以展示「连了几个 Server、发现了几把工具」，绝不能把 token 读回来。第 25 章的设置工作台已经按这个假设留了 MCP 模块位，只是 PATCH 还没有在 TypeScript 控制平面里落地。

启用开关应能在不改 yaml 的情况下止血。那是策略层的事，不是把配置文件交给浏览器当编辑器。等 application 里出现 `McpService`，再把 stub 换成真路由，目录不用打乱。

笔者愿意把这一章写短，是因为把未完成的 Client 写成「已经能调 GitHub / 飞书」会害人。现在能确认的是：角色清楚，前端入口在，后端路由不 404，空列表可观察。真连接、真 `tools/call`、真事件写入，是后续往 `application/` 和 `infrastructure/` 填实现时的事。空着的位置比假装成功更有用。

## 这一章留下了什么

一套关于 Host、Client、Server 的共同语言，一块已经挂在工作台上的 MCP 面板，以及控制平面里诚实的空列表。下一章不谈新协议，回头把 TypeScript 后端的分层说清楚——MCP Client 将来要落在哪一层，取决于现在有没有把 HTTP、用例和外部适配分开。

---

[← 第二十章. SearchTool 搜索能力成形](20-SearchTool%20搜索能力成形.md) · [返回目录](../README.md) · [第二十二章. 后端分层框架再造 →](22-后端分层框架再造.md)
