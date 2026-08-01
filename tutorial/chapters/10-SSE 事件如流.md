# 第十章. SSE 事件如流

## 10.1 本章目标

​        第 09 章已经能保存消息和事件，但前端仍然是“请求发出去，等后端处理完，再一次性刷新”。这种模式适合很短的接口，不适合 Agent。真正的 Agent 执行过程会不断产生中间状态：收到任务、生成计划、执行步骤、调用工具、观察结果、继续推理。用户不应该等到所有事情结束后才看到结果。
​        本章引入 SSE，也就是 Server-Sent Events。读者会编写 `text/event-stream` 响应，通过 Nginx 正确代理流式响应，在前端用 `fetch` 读取 `ReadableStream`，并解析 SSE 中的 `event:` 和 `data:` 数据块。前端的 zustand store 会边读流边更新事件面板，同时保留第 09 章的一次性消息接口，新增一个流式消息接口。这样后续 Agent 执行事件就有了实时展示的基础。

## 10.2 最终效果

​        本章结束后，发送消息不再只是等待接口返回完整 JSON。前端会边读取 SSE 流，边把服务端推送的事件展示到事件面板里。

​        访问：

```Plain
http://localhost:8088
```

​        在聊天输入框发送消息后，前端会读取 SSE 流。

​        后端新增接口：

```Plain
POST /api/sessions/{session_id}/messages/stream
```

​        使用 `curl` 验证时，可以看到类似输出：

```Plain
event: message_created
data: {"id":"...","session_id":"...","type":"message_created","payload":{...},"created_at":"..."}

event: stream_done
data: {"session_id":"...","message":{...}}
```

​        页面效果：

```Plain
发送消息
  |
  v
事件面板出现 message_created
  |
  v
流结束后刷新消息时间线
```

## 10.3 本章要解决的问题

​        第 09 章已经实现了消息和事件持久化。但第 09 章的前端仍然是这种模式：

```Plain
发送请求
  |
  v
等待后端处理完
  |
  v
重新加载消息和事件
```

​        这适合很短的接口，不适合 Agent 执行。Agent 后续会经历很多过程：

```Plain
收到用户任务
生成计划
执行步骤
调用工具
等待工具结果
总结输出
```

​        这些过程不应该等全部完成后一次性返回。更好的体验是服务端每产生一个事件，前端就展示一个事件。所以本章引入 SSE，让事件从“事后查询”逐步走向“实时推送”。

## 10.4 本章技术方案

​        本章先做一个最小流式闭环。

​        后端保留第 09 章的接口：

```Plain
POST /api/sessions/{session_id}/messages
```

​        同时新增流式接口：

```Plain
POST /api/sessions/{session_id}/messages/stream
```

​        流式接口仍然复用 `SessionService.create_user_message()`，保证消息和事件还是写入数据库。

​        写入成功后，后端用 SSE 格式推送：

```Plain
message_created
stream_done
```

​        前端不使用额外依赖，直接用浏览器原生 `fetch` 读取 `ReadableStream`。

​        前端分层如下：

```Plain
ui/app/lib/sse.ts
  |
  +-- 解析 text/event-stream

ui/app/lib/session-api.ts
  |
  +-- 调用 stream 接口

ui/app/stores/session-store.ts
  |
  +-- 发送消息
  +-- 接收流式事件
  +-- 更新事件面板
```

​        本章暂时不实现真正的 Agent 执行，不生成 assistant 消息，不做停止任务，也不做断线重连、历史事件增量游标和多事件类型的复杂渲染。现在先让浏览器能稳定读取流，后面再把更多事件类型接进来。

## 10.5 新增和修改的文件

```Plain
README.md
api/README.md
ui/README.md
nginx/README.md
nginx/default.conf
api/app/api/sse.py
api/app/api/routes/sessions.py
ui/app/types.ts
ui/app/lib/sse.ts
ui/app/lib/session-api.ts
ui/app/stores/session-store.ts
docs/course/chapters/10-sse-events.md
```

## 10.6 实施步骤
### 10.6.1 理解 SSE 数据格式

​        SSE 的响应类型是：

```Plain
text/event-stream
```

​        一条事件通常长这样：

```Plain
event: message_created
data: {"type":"message_created"}
```

​        注意最后有一个空行。

​        浏览器或前端代码会通过空行判断一条事件结束。

​        如果连续发送两条事件，就是：

```Plain
event: message_created
data: {"type":"message_created"}

event: stream_done
data: {"ok":true}
```

#### 10.6.1.1 关键理解

​        普通 JSON 接口只返回一次：

```Plain
HTTP request -> JSON response -> 结束
```

​        SSE 接口可以不断写出事件：

```Plain
HTTP request
  |
  +-- event 1
  +-- event 2
  +-- event 3
  |
  v
结束
```

​        本章先用两条事件演示这个机制。

### 10.6.2 编写后端 SSE 编码工具

​        创建 `api/app/api/sse.py`：

```Python
from collections.abc import AsyncIterator
from json import dumps


def encode_sse(event: str, data: dict) -> str:
    payload = dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def iter_sse(events: list[tuple[str, dict]]) -> AsyncIterator[str]:
    for event, data in events:
        yield encode_sse(event, data)
```

#### 10.6.2.1 这段代码的业务流程

​        `encode_sse()` 把 Python 字典转成 SSE 字符串。

​        输入：

```Python
encode_sse("message_created", {"type": "message_created"})
```

​        输出：

```Plain
event: message_created
data: {"type":"message_created"}
```

#### 10.6.2.2 为什么这样设计

​        SSE 格式很简单，但手写时容易漏掉最后的空行。

​        封装成 `encode_sse()` 后，路由里只需要关心事件名和数据内容。

​        `default=str` 用来处理 `datetime`、`UUID` 这类 JSON 默认不能直接序列化的对象。

### 10.6.3 新增流式消息接口

​        打开 `api/app/api/routes/sessions.py`，新增这些 import：

```Python
from asyncio import sleep

from fastapi.responses import StreamingResponse

from app.api.sse import encode_sse
```

​        在普通发送消息接口后面加入流式接口：

```Python
@router.post("/{session_id}/messages/stream")
async def stream_message(
    session_id: UUID,
    payload: MessageCreateRequest,
    service: SessionService = Depends(build_session_service),
) -> StreamingResponse:
    message, event = await service.create_user_message(
        session_id=session_id,
        content=payload.content,
    )
    message_data = to_message_response(message).model_dump(mode="json")
    event_data = to_event_response(event).model_dump(mode="json")

    async def event_stream():
        yield encode_sse("message_created", event_data)
        await sleep(0.2)
        yield encode_sse(
            "stream_done",
            {
                "session_id": str(session_id),
                "message": message_data,
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

#### 10.6.3.1 这段代码的业务流程

​        请求进入流式接口后：

```Plain
POST /api/sessions/{id}/messages/stream
  |
  v
调用 create_user_message()
  |
  v
写入消息和事件
  |
  v
推送 message_created
  |
  v
推送 stream_done
```

#### 10.6.3.2 关键代码逐段解释

​        先复用已有应用服务：

```Python
message, event = await service.create_user_message(...)
```

​        这样普通接口和流式接口写入数据的逻辑保持一致。

​        再把 Pydantic 模型转成 JSON 友好的字典：

```Python
model_dump(mode="json")
```

​        `mode="json"` 会把 `UUID`、`datetime` 转成前端容易处理的字符串。

​        最后用 `StreamingResponse` 返回流：

```Python
StreamingResponse(event_stream(), media_type="text/event-stream")
```

#### 10.6.3.3 为什么这样设计

​        本章的流式接口不是为了替代数据库，而是为了把“事件产生过程”推给前端。

​        数据库仍然是最终状态来源。流结束后，前端会重新加载消息和事件，保证页面和数据库一致。

### 10.6.4 配置 Nginx 支持流式代理

​        打开 `nginx/default.conf`，修改 `/api/` 代理：

```Nginx
location /api/ {
    proxy_buffering off;
    proxy_cache off;
    proxy_pass http://api:8000;
}
```

​        完整文件如下：

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
        proxy_buffering off;
        proxy_cache off;
        proxy_pass http://api:8000;
    }

    location / {
        proxy_pass http://ui:3000;
    }
}
```

#### 10.6.4.1 为什么这样设计

​        Nginx 默认可能会缓冲后端响应。

​        普通 JSON 接口不怕缓冲，但 SSE 需要服务端发一条，浏览器尽快收到一条。

​        所以这里关闭 `/api/` 的代理缓冲：

```Nginx
proxy_buffering off;
```

### 10.6.5 定义前端流式事件类型

​        打开 `ui/app/types.ts`，新增：

```TypeScript
export type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};
```

#### 10.6.5.1 这段代码的业务流程

​        后端推送的 SSE 数据会被前端解析成：

```TypeScript
{
  event: "message_created",
  data: {
    id: "...",
    type: "message_created"
  }
}
```

​        `event` 是事件名称，`data` 是事件内容。

### 10.6.6 编写前端 SSE 解析工具

​        创建 `ui/app/lib/sse.ts`：

```TypeScript
import type { StreamEvent } from "../types";

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split("\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>,
  };
}

export async function readSseStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
) {
  if (!response.body) {
    throw new Error("empty stream response");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseSseBlock(block.trim());
      if (event) {
        onEvent(event);
      }
    }
  }

  buffer += decoder.decode();
  const event = parseSseBlock(buffer.trim());
  if (event) {
    onEvent(event);
  }
}
```

#### 10.6.6.1 这段代码的业务流程

​        浏览器收到的流不是一次完整字符串，而是一小块一小块的数据。

```Plain
chunk 1 -> buffer
chunk 2 -> buffer
遇到空行 -> 解析成事件
```

​        所以这里维护了一个 `buffer`。

​        每次读到新 chunk 后，用：

```TypeScript
buffer.split("\n\n")
```

​        切出完整事件块。

#### 10.6.6.2 常见误区

​        不要假设一次 `reader.read()` 就能读到完整事件。

​        网络传输会把数据切成不固定大小的 chunk。必须用 buffer 累积，再按 SSE 的空行分隔解析。

### 10.6.7 封装流式发送 API

​        打开 `ui/app/lib/session-api.ts`，新增 import：

```TypeScript
import { readSseStream } from "./sse";
```

​        再新增 `streamMessage()`：

```TypeScript
export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  await readSseStream(response, onEvent);
}
```

#### 10.6.7.1 这段代码的业务流程

​        `streamMessage()` 负责三件事：

```Plain
发送 POST 请求
  |
  v
拿到 text/event-stream 响应
  |
  v
交给 readSseStream() 持续解析
```

​        每解析出一条事件，就调用：

```TypeScript
onEvent(event)
```

​        store 可以在这个回调里更新事件面板。

### 10.6.8 在 store 中消费流式事件

​        打开 `ui/app/stores/session-store.ts`，把 `sendMessage` import 换成：

```TypeScript
streamMessage,
```

​        新增事件转换函数：

```TypeScript
function toSessionEventItem(event: StreamEvent): SessionEventItem | null {
  if (event.event !== "message_created") {
    return null;
  }
  const data = event.data as Partial<SessionEventItem>;
  if (!data.id || !data.session_id || !data.type || !data.created_at) {
    return null;
  }
  return {
    id: String(data.id),
    session_id: String(data.session_id),
    type: String(data.type),
    payload:
      typeof data.payload === "object" && data.payload !== null
        ? (data.payload as Record<string, unknown>)
        : {},
    created_at: String(data.created_at),
  };
}
```

​        把 `sendMessage` action 改成流式版本：

```TypeScript
sendMessage: async () => {
  const sessionId = get().selectedSessionId;
  const content = get().draft.trim();
  if (!sessionId) {
    set({ actionError: "请先选择一个会话" });
    return;
  }
  if (!content) {
    set({ actionError: "请输入消息内容" });
    return;
  }

  set({ actionError: null, sendingMessage: true });
  try {
    await streamMessage(sessionId, content, (event) => {
      const sessionEvent = toSessionEventItem(event);
      if (!sessionEvent) {
        return;
      }
      set((state) => {
        const currentEvents =
          state.events.type === "ready" ? state.events.data : [];
        return {
          events: {
            type: "ready",
            data: [...currentEvents, sessionEvent],
          },
        };
      });
    });
    set({ draft: "" });
    await Promise.all([
      get().loadSessionDetail(sessionId),
      get().refreshSessions(),
    ]);
  } catch (error) {
    set({ actionError: getErrorMessage(error) });
  } finally {
    set({ sendingMessage: false });
  }
}
```

#### 10.6.8.1 这段代码的业务流程

​        用户点击发送后：

```Plain
ChatInput
  |
  v
store.sendMessage()
  |
  v
streamMessage()
  |
  v
readSseStream()
  |
  v
onEvent(message_created)
  |
  v
追加到事件面板
```

​        流结束后再重新加载消息和事件：

```TypeScript
await Promise.all([
  get().loadSessionDetail(sessionId),
  get().refreshSessions(),
]);
```

​        这样既能看到流式事件，又能保证最终页面以数据库为准。

### 10.6.9 对照关键完整文件

​        下面给出本章新增和重点修改文件的完整代码。

#### 10.6.9.1 api/app/api/sse.py

```Python
from collections.abc import AsyncIterator
from json import dumps


def encode_sse(event: str, data: dict) -> str:
    payload = dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def iter_sse(events: list[tuple[str, dict]]) -> AsyncIterator[str]:
    for event, data in events:
        yield encode_sse(event, data)
```

#### 10.6.9.2 ui/app/lib/sse.ts

```TypeScript
import type { StreamEvent } from "../types";

function parseSseBlock(block: string): StreamEvent | null {
  const lines = block.split("\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>,
  };
}

export async function readSseStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
) {
  if (!response.body) {
    throw new Error("empty stream response");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseSseBlock(block.trim());
      if (event) {
        onEvent(event);
      }
    }
  }

  buffer += decoder.decode();
  const event = parseSseBlock(buffer.trim());
  if (event) {
    onEvent(event);
  }
}
```

#### 10.6.9.3 ui/app/lib/session-api.ts

```TypeScript
import { requestApi } from "./api";
import { readSseStream } from "./sse";
import type {
  ChatMessage,
  MessageCreateData,
  MessageListData,
  SessionEventItem,
  SessionEventListData,
  SessionItem,
  SessionListData,
  StreamEvent,
} from "../types";

export function fetchSessions(): Promise<SessionItem[]> {
  return requestApi<SessionListData>("/api/sessions").then((data) => data.items);
}

export function createSession(title: string): Promise<SessionItem> {
  return requestApi<SessionItem>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function deleteSession(sessionId: string): Promise<void> {
  return requestApi<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export function fetchMessages(sessionId: string): Promise<ChatMessage[]> {
  return requestApi<MessageListData>(`/api/sessions/${sessionId}/messages`).then(
    (data) => data.items,
  );
}

export function fetchEvents(sessionId: string): Promise<SessionEventItem[]> {
  return requestApi<SessionEventListData>(
    `/api/sessions/${sessionId}/events`,
  ).then((data) => data.items);
}

export function sendMessage(
  sessionId: string,
  content: string,
): Promise<MessageCreateData> {
  return requestApi<MessageCreateData>(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(`/api/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  await readSseStream(response, onEvent);
}
```

#### 10.6.9.4 ui/app/stores/session-store.ts

```TypeScript
import { create } from "zustand";

import {
  createSession,
  deleteSession,
  fetchEvents,
  fetchMessages,
  fetchSessions,
  streamMessage,
} from "../lib/session-api";
import type {
  ChatMessage,
  LoadState,
  SessionEventItem,
  SessionItem,
  StreamEvent,
} from "../types";

type SessionState = {
  actionError: string | null;
  draft: string;
  events: LoadState<SessionEventItem[]>;
  messages: LoadState<ChatMessage[]>;
  selectedSessionId: string | null;
  sendingMessage: boolean;
  sessions: LoadState<SessionItem[]>;
  submitting: boolean;
  title: string;
};

type SessionActions = {
  createSession: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  loadSessionDetail: (sessionId: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
  selectSession: (sessionId: string | null) => void;
  sendMessage: () => Promise<void>;
  setActionError: (message: string | null) => void;
  setDraft: (draft: string) => void;
  setTitle: (title: string) => void;
};

const initialDetailState = {
  messages: { type: "ready", data: [] } as LoadState<ChatMessage[]>,
  events: { type: "ready", data: [] } as LoadState<SessionEventItem[]>,
};

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "unknown error";
}

function toSessionEventItem(event: StreamEvent): SessionEventItem | null {
  if (event.event !== "message_created") {
    return null;
  }
  const data = event.data as Partial<SessionEventItem>;
  if (!data.id || !data.session_id || !data.type || !data.created_at) {
    return null;
  }
  return {
    id: String(data.id),
    session_id: String(data.session_id),
    type: String(data.type),
    payload:
      typeof data.payload === "object" && data.payload !== null
        ? (data.payload as Record<string, unknown>)
        : {},
    created_at: String(data.created_at),
  };
}

export const useSessionStore = create<SessionState & SessionActions>(
  (set, get) => ({
    actionError: null,
    draft: "",
    events: initialDetailState.events,
    messages: initialDetailState.messages,
    selectedSessionId: null,
    sendingMessage: false,
    sessions: { type: "loading" },
    submitting: false,
    title: "",

    setActionError: (message) => set({ actionError: message }),
    setDraft: (draft) => set({ draft }),
    setTitle: (title) => set({ title }),

    selectSession: (sessionId) => {
      set({
        selectedSessionId: sessionId,
        ...initialDetailState,
      });
    },

    refreshSessions: async () => {
      set({ actionError: null });
      try {
        const items = await fetchSessions();
        set((state) => {
          const selectedSessionId =
            state.selectedSessionId &&
            items.some((item) => item.id === state.selectedSessionId)
              ? state.selectedSessionId
              : items[0]?.id ?? null;

          return {
            sessions: { type: "ready", data: items },
            selectedSessionId,
          };
        });
      } catch (error) {
        set({
          actionError: getErrorMessage(error),
          sessions: { type: "error", message: getErrorMessage(error) },
        });
      }
    },

    loadSessionDetail: async (sessionId) => {
      set({
        events: { type: "loading" },
        messages: { type: "loading" },
      });
      try {
        const [messages, events] = await Promise.all([
          fetchMessages(sessionId),
          fetchEvents(sessionId),
        ]);
        set({
          events: { type: "ready", data: events },
          messages: { type: "ready", data: messages },
        });
      } catch (error) {
        const message = getErrorMessage(error);
        set({
          actionError: message,
          events: { type: "error", message },
          messages: { type: "error", message },
        });
      }
    },

    createSession: async () => {
      const cleanTitle = get().title.trim();
      if (!cleanTitle) {
        set({ actionError: "请输入会话标题" });
        return;
      }

      set({ actionError: null, submitting: true });
      try {
        const created = await createSession(cleanTitle);
        set({
          title: "",
          selectedSessionId: created.id,
        });
        await get().refreshSessions();
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ submitting: false });
      }
    },

    deleteSession: async (sessionId) => {
      set({ actionError: null });
      try {
        await deleteSession(sessionId);
        await get().refreshSessions();
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      }
    },

    sendMessage: async () => {
      const sessionId = get().selectedSessionId;
      const content = get().draft.trim();
      if (!sessionId) {
        set({ actionError: "请先选择一个会话" });
        return;
      }
      if (!content) {
        set({ actionError: "请输入消息内容" });
        return;
      }

      set({ actionError: null, sendingMessage: true });
      try {
        await streamMessage(sessionId, content, (event) => {
          const sessionEvent = toSessionEventItem(event);
          if (!sessionEvent) {
            return;
          }
          set((state) => {
            const currentEvents =
              state.events.type === "ready" ? state.events.data : [];
            return {
              events: {
                type: "ready",
                data: [...currentEvents, sessionEvent],
              },
            };
          });
        });
        set({ draft: "" });
        await Promise.all([
          get().loadSessionDetail(sessionId),
          get().refreshSessions(),
        ]);
      } catch (error) {
        set({ actionError: getErrorMessage(error) });
      } finally {
        set({ sendingMessage: false });
      }
    },
  }),
);
```

#### 10.6.9.5 nginx/default.conf

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
        proxy_buffering off;
        proxy_cache off;
        proxy_pass http://api:8000;
    }

    location / {
        proxy_pass http://ui:3000;
    }
}
```

## 10.7 关键理解

​        SSE 不是新的数据库模型，也不是 WebSocket。

​        它是一个普通 HTTP 连接，只是响应不会立刻结束，而是持续写出事件。

​        本章的链路是：

```Plain
前端发送消息
  |
  v
后端写入消息和事件
  |
  v
后端通过 SSE 推送事件
  |
  v
前端边读流边更新事件面板
  |
  v
流结束后刷新数据库状态
```

​        这里有一个重要取舍：本章仍然在流结束后重新加载消息和事件。

​        原因是流式事件适合展示过程，数据库查询适合确认最终状态。两者结合，页面既能及时反馈，又不容易和后端状态脱节。

## 10.8 技术难点与亮点

​        技术难点：

​        本章的技术难点集中在流式数据的边界上。SSE 事件必须用空行分隔，前端不能假设一次读取就是一条完整事件，所以需要维护 buffer。Nginx 代理需要关闭缓冲，避免流式响应被攒起来一次性返回。store 也要边读流边更新事件面板，同时在流结束后刷新最终状态。

​        项目亮点：

​        本章的亮点，是消息接口开始具备流式能力。前端不引入额外依赖，直接使用浏览器原生流读取能力；Nginx 网关开始为后续长任务事件流做准备；第 11 章也可以自然扩展运行状态、停止任务和未读数。

## 10.9 面试考点

​        面试里可以重点讲清楚：SSE 和普通 JSON 接口有什么区别，SSE 和 WebSocket 的区别是什么，为什么 SSE 响应需要 `text/event-stream`，为什么前端读取 SSE 要维护 buffer，以及为什么 Nginx 代理 SSE 时要关闭缓冲。能回答这些问题，就说明你理解的是流式链路，而不是只复制了一个响应头。

## 10.10 运行验证

​        下面命令默认在项目根目录执行。

### 10.10.1 重新构建 API 和 UI

​        第 10 章修改了 API、UI 和 Nginx 配置。

​        执行：

```Bash
docker compose build api ui
docker compose up -d nginx
```

​        如果 Nginx 配置没有刷新，可以重新创建 Nginx 容器：

```Bash
docker compose up -d --force-recreate nginx
```

### 10.10.2 执行迁移

​        如果第 09 章已经执行过迁移，这一步不会重复创建表。

```Bash
docker compose exec api uv run alembic upgrade head
```

### 10.10.3 创建会话

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 10 章 SSE 测试"}'
```

​        记录返回结果里的 `id`。

### 10.10.4 验证 SSE 接口

​        把会话 ID 替换到下面命令：

```Bash
curl -N -X POST http://localhost:8088/api/sessions/{session_id}/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"content":"测试 SSE 流式事件"}'
```

​        预期看到：

```Plain
event: message_created
data: {...}

event: stream_done
data: {...}
```

​        `-N` 表示关闭 curl 自己的输出缓冲。验证 SSE 时建议加上。

### 10.10.5 验证页面

​        访问：

```Plain
http://localhost:8088
```

​        在页面中：

​        验证时选择一个会话，输入任务内容并点击发送。正常情况下，事件记录会先出现 `message_created`，流结束后消息时间线出现用户消息。这说明前端已经不是等完整 JSON 返回，而是在读取服务端推送的流式事件。

## 10.11 常见问题

### 10.11.1 `curl` 没有立刻输出事件怎么办

​        确认命令里有 `-N`，并确认 Nginx 配置里 `/api/` 已经加入 `proxy_buffering off;`。如果代理层开启缓冲，事件可能会被攒起来，前端就看不到实时效果。

### 10.11.2 页面没有使用流式接口怎么办

​        第 10 章修改了 UI 构建产物，需要执行 `docker compose build ui`，再启动服务。否则浏览器看到的可能还是旧版本前端代码。

### 10.11.3 接口返回 404 怎么办

​        确认 API 镜像已经重新构建。执行 `docker compose build api` 后再启动，确保 `/messages/stream` 路由已经进入容器中的后端服务。

### 10.11.4 为什么页面收到流式事件后还要重新加载消息

​        事件流负责实时反馈，数据库查询负责最终一致。后续一次请求可能产生多条事件和多条消息，流结束后刷新能保证页面结果准确。

## 10.12 本章小结

​        本章完成了第一个 SSE 流式闭环。后端新增 SSE 编码工具和消息流式接口，Nginx 对 `/api/` 关闭代理缓冲，前端新增 SSE 解析工具，并在发送消息时改为读取流式响应。store 现在可以边读事件边更新事件面板，这为后续长时间 Agent 执行打下了基础。

​        从这一章开始，事件不再只能通过普通查询获取。后续 Agent 执行、工具调用、计划更新都可以沿着这条流式链路继续扩展。

## 10.13 下一章预告

​        第 11 章会补齐会话运行状态、停止任务、未读消息数和前端加载/停止/错误状态，让会话更像一个可运行的任务。
