# 第七章. 对话消息与 SSE 事件流

## 7.1 对话输入与消息事件

### 7.1.1 本节目标

​        第 6 章让页面有了真实会话列表，但会话还只是入口。一个 Agent 工作台真正开始像产品，是从用户能在某个会话里输入任务、看到消息、看到系统事件开始的。聊天框只是表面，背后需要消息表、事件表、接口、事务和前端状态共同配合。
​        本节要完成基础聊天工作台。读者会设计消息表和事件表，理解为什么聊天系统不只保存消息，还要保存事件；会编写会话详情、消息列表、发送消息和事件列表接口；也会使用 Unit of Work 保证“写消息、写事件、更新会话时间”在同一个事务中完成。前端会引入 zustand，把会话、消息和事件状态从 `page.tsx` 中抽离出来，再用 hook 组织页面初始化和选中会话后的联动加载。到这一阶段结束时，页面会拥有聊天输入框、消息时间线和事件面板。

### 7.1.2 最终效果

​        本节结束后，页面不再只显示会话列表，而是可以进入一个基础聊天工作台。

​        访问：

```Plain
http://localhost:8088
```

​        你可以完成下面的操作：

```Plain
创建会话 -> 选择会话 -> 输入消息 -> 发送 -> 消息出现在时间线 -> 事件面板出现 message_created
```

​        后端新增接口：

```Plain
GET  /api/sessions/{session_id}
GET  /api/sessions/{session_id}/messages
POST /api/sessions/{session_id}/messages
GET  /api/sessions/{session_id}/events
```

​        本节先不接 LLM。发送消息后，只保存用户消息和一条 `message_created` 事件。这个限制是有意的：在让模型参与之前，先把“消息如何落库、事件如何记录、前端如何刷新”这条基础链路跑稳。本章后文会把事件改造成 SSE 流式输出。

### 7.1.3 本节要解决的问题

​        第 6 章已经有了会话列表，但会话只是一个入口，还不能承载真正的聊天内容。一个 Agent 产品里，用户每输入一次任务，系统至少要记录两类数据：

```Plain
消息：用户说了什么
事件：系统发生了什么
```

​        消息适合用来展示聊天记录，事件适合用来展示过程。比如：

```Plain
message_created
plan_created
step_started
tool_called
task_done
```

​        本节先实现最小版本：

```Plain
用户发送消息
  |
  v
写入 session_messages
  |
  v
写入 session_events
  |
  v
前端刷新消息时间线和事件面板
```

​        这样后续接入 SSE 时，事件模型已经存在，不需要重新推翻数据结构。消息回答“对话里说了什么”，事件回答“系统在执行中发生了什么”。这两个问题分开建模，后续 Agent 推理过程才有地方承载。

### 7.1.4 本节技术方案

​        后端继续沿用第 07、08 章的分层：

```Plain
API Route
  |
  v
SessionService
  |
  v
UnitOfWork
  |
  +-- SessionRepository
  +-- SessionMessageRepository
  +-- SessionEventRepository
```

​        发送消息时，应用服务会在同一个事务里完成三件事：

```Plain
1. 检查会话是否存在
2. 写入用户消息
3. 写入 message_created 事件
4. 更新会话 updated_at
5. commit
```

​        前端从本节开始使用 zustand。

​        第 6 章的 `page.tsx` 已经明显承担了越来越多状态：会话列表、选中会话、表单标题、错误信息。本节加入消息、事件和聊天输入后，如果继续放在 `page.tsx`，页面会很快变成一个大文件。

​        本节前端分层如下：

```Plain
frontend/web/app/page.tsx
  |
  +-- 只组合页面区域和服务状态

frontend/web/app/hooks/use-session-workspace.ts
  |
  +-- 页面初始化
  +-- 选中会话后的消息和事件加载
  +-- 派生 selectedSession

frontend/web/app/stores/session-store.ts
  |
  +-- 会话列表状态
  +-- 消息状态
  +-- 事件状态
  +-- 创建会话、删除会话、发送消息

frontend/web/app/components
  |
  +-- ChatWorkspace
  +-- ChatInput
  +-- MessageTimeline
  +-- EventTimeline
```

​        本节暂时不接 LLM，不生成 assistant 消息，不做 SSE，不做消息分页，也不做附件上传和任务停止。这里仍然只完成最小但真实的聊天链路：用户消息能写入数据库，事件能被记录，前端能看到两条时间线。

### 7.1.5 新增和修改的文件

```Plain
README.md
backend/api/README.md
frontend/web/README.md
backend/api/app/domain/sessions/entities.py
backend/api/app/domain/sessions/repositories.py
backend/api/app/infrastructure/database/models/__init__.py
backend/api/app/infrastructure/database/models/session_message.py
backend/api/app/infrastructure/database/models/session_event.py
backend/api/app/infrastructure/repositories/session_repository.py
backend/api/app/application/unit_of_work.py
backend/api/app/application/session_service.py
backend/api/app/api/routes/sessions.py
backend/api/app/schemas/session.py
backend/api/migrations/versions/202606030002_create_session_messages_events.py
frontend/web/package.json
frontend/web/pnpm-lock.yaml
frontend/web/app/types.ts
frontend/web/app/lib/session-api.ts
frontend/web/app/stores/session-store.ts
frontend/web/app/hooks/use-session-workspace.ts
frontend/web/app/components/app-sidebar.tsx
frontend/web/app/components/chat-input.tsx
frontend/web/app/components/message-timeline.tsx
frontend/web/app/components/event-timeline.tsx
frontend/web/app/components/chat-workspace.tsx
frontend/web/app/page.tsx
```

### 7.1.6 实施步骤
#### 7.1.6.1 安装 zustand

​        进入 `ui` 目录：

```Bash
cd frontend/web
```

​        安装 zustand：

```Bash
pnpm add zustand
```

​        安装完成后，`frontend/web/package.json` 会新增：

```JSON
"zustand": "^5.0.14"
```

​        `frontend/web/pnpm-lock.yaml` 也会同步更新。

.1.6.1.1 这一步的作用

​        zustand 是一个轻量状态管理库。

​        本节使用它管理会话页面的共享状态，例如：

```Plain
当前选中的会话
会话列表
消息列表
事件列表
输入框草稿
发送中状态
错误提示
```

​        这些状态会被侧边栏、聊天输入框、消息时间线、事件面板同时使用。放进 store 后，组件之间不用一层层传很多 props。

#### 7.1.6.2 定义消息和事件领域实体

​        打开 `backend/api/app/domain/sessions/entities.py`，新增消息角色和事件类型：

```Python
class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"

class SessionEventType(StrEnum):
    message_created = "message_created"
```

​        继续新增两个实体：

```Python
@dataclass(slots=True)
class SessionMessage:
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime

@dataclass(slots=True)
class SessionEvent:
    id: UUID
    session_id: UUID
    type: SessionEventType
    payload: dict
    created_at: datetime
```

.1.6.2.1 这段代码的业务流程

​        `SessionMessage` 表示聊天内容。

​        `SessionEvent` 表示会话里发生过的动作。

​        用户发送消息后，会产生：

```Plain
一条 SessionMessage
一条 SessionEvent
```

​        事件的 `payload` 用来存放结构化信息，例如：

```JSON
{
  "message_id": "...",
  "role": "user",
  "content": "帮我规划一个学习任务"
}
```

.1.6.2.2 为什么这样设计

​        消息和事件不要混成一张表。

​        消息更关注“对话内容”，事件更关注“过程记录”。后续 Agent 执行时，工具调用、计划更新、步骤开始、任务完成都不是普通聊天消息，但它们都应该进入事件流。

#### 7.1.6.3 扩展 Repository 协议

​        打开 `backend/api/app/domain/sessions/repositories.py`，为会话仓库增加 `touch()`：

```Python
async def touch(self, session_id: UUID) -> None:
    raise NotImplementedError
```

​        再新增消息和事件仓库协议：

```Python
class SessionMessageRepository(Protocol):
    async def add_user_message(self, session_id: UUID, content: str) -> SessionMessage:
        raise NotImplementedError

    async def list_by_session(self, session_id: UUID) -> list[SessionMessage]:
        raise NotImplementedError

class SessionEventRepository(Protocol):
    async def add(
        self,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        raise NotImplementedError

    async def list_by_session(self, session_id: UUID) -> list[SessionEvent]:
        raise NotImplementedError
```

.1.6.3.1 这段代码的业务流程

​        `SessionMessageRepository` 负责消息读写。

​        `SessionEventRepository` 负责事件读写。

​        `touch()` 负责更新会话的 `updated_at`。发送消息后，左侧会话列表应该把最近有动作的会话排到前面，所以需要刷新会话更新时间。

.1.6.3.2 常见误区

​        不要让消息仓库直接修改会话表。

​        消息仓库只管消息，会话仓库只管会话。一次业务动作要写多张表时，由应用服务和 Unit of Work 负责协调。

#### 7.1.6.4 创建 SQLAlchemy 模型

​        创建 `backend/api/app/infrastructure/database/models/session_message.py`：

```Python
class SessionMessageModel(Base):
    __tablename__ = "session_messages"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
```

​        创建 `backend/api/app/infrastructure/database/models/session_event.py`：

```Python
class SessionEventModel(Base):
    __tablename__ = "session_events"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
```

​        同时更新 `backend/api/app/infrastructure/database/models/__init__.py`，确保 Alembic 能加载模型：

```Python
from app.infrastructure.database.models.session_event import SessionEventModel
from app.infrastructure.database.models.session_message import SessionMessageModel
from app.infrastructure.database.models.session import SessionModel

__all__ = ["SessionEventModel", "SessionMessageModel", "SessionModel"]
```

.1.6.4.1 这段代码的业务流程

​        `session_messages.session_id` 指向 `sessions.id`。

​        `session_events.session_id` 也指向 `sessions.id`。

​        也就是说，一个会话下面可以有多条消息和多条事件。

```Plain
sessions
  |
  +-- session_messages
  |
  +-- session_events
```

.1.6.4.2 为什么这样设计

​        `payload` 使用 PostgreSQL 的 `JSONB`，因为不同事件的字段不完全一样。

​        例如 `message_created` 需要 `message_id`，后续 `tool_called` 可能需要工具名、参数、结果摘要。如果每种事件都加很多固定列，表结构会很快变得僵硬。

#### 7.1.6.5 创建迁移文件

​        创建 `backend/api/migrations/versions/202606030002_create_session_messages_events.py`。

​        核心迁移如下：

```Python
def upgrade() -> None:
    op.create_table(
        "session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_messages_session_created",
        "session_messages",
        ["session_id", "created_at"],
    )

    op.create_table(
        "session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_events_session_created",
        "session_events",
        ["session_id", "created_at"],
    )
```

.1.6.5.1 这段代码的业务流程

​        前端进入某个会话时，会按会话 ID 查询：

```Plain
GET /api/sessions/{session_id}/messages
GET /api/sessions/{session_id}/events
```

​        所以两张表都加了组合索引：

```Plain
session_id + created_at
```

​        这样数据库可以更快按会话查出时间线。

#### 7.1.6.6 实现消息和事件 Repository

​        打开 `backend/api/app/infrastructure/repositories/session_repository.py`。

​        新增消息仓库：

```Python
class SqlAlchemySessionMessageRepository(SessionMessageRepository):
    async def add_user_message(self, session_id: UUID, content: str) -> SessionMessage:
        model = SessionMessageModel(
            session_id=session_id,
            role=MessageRole.user.value,
            content=content,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()

    async def list_by_session(self, session_id: UUID) -> list[SessionMessage]:
        stmt = (
            select(SessionMessageModel)
            .where(SessionMessageModel.session_id == session_id)
            .order_by(SessionMessageModel.created_at.asc())
        )
        result = await self.db_session.execute(stmt)
        return [model.to_entity() for model in result.scalars()]
```

​        新增事件仓库：

```Python
class SqlAlchemySessionEventRepository(SessionEventRepository):
    async def add(
        self,
        session_id: UUID,
        event_type: SessionEventType,
        payload: dict,
    ) -> SessionEvent:
        model = SessionEventModel(
            session_id=session_id,
            type=event_type.value,
            payload=payload,
        )
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return model.to_entity()
```

.1.6.6.1 这段代码的业务流程

​        发送消息时：

```Plain
SessionService
  |
  +-- session_messages.add_user_message()
  |
  +-- session_events.add()
```

​        查询详情时：

```Plain
SessionService
  |
  +-- session_messages.list_by_session()
  |
  +-- session_events.list_by_session()
```

.1.6.6.2 为什么这样设计

​        Repository 不提交事务，只负责把模型加入当前数据库会话。

​        提交事务放在应用服务最后做，是为了保证消息和事件要么一起成功，要么一起失败。

#### 7.1.6.7 扩展 Unit of Work 和应用服务

​        打开 `backend/api/app/application/unit_of_work.py`，加入两个仓库：

```Python
self.session_messages = SqlAlchemySessionMessageRepository(db_session)
self.session_events = SqlAlchemySessionEventRepository(db_session)
```

​        打开 `backend/api/app/application/session_service.py`，新增发送消息逻辑：

```Python
async def create_user_message(
    self,
    session_id: UUID,
    content: str,
) -> tuple[SessionMessage, SessionEvent]:
    await self.get_session(session_id)
    clean_content = content.strip()
    if not clean_content:
        raise AppException(
            message="message content is required",
            code=400,
            status_code=400,
        )

    message = await self.uow.session_messages.add_user_message(
        session_id=session_id,
        content=clean_content,
    )
    event = await self.uow.session_events.add(
        session_id=session_id,
        event_type=SessionEventType.message_created,
        payload={
            "message_id": str(message.id),
            "role": message.role.value,
            "content": message.content,
        },
    )
    await self.uow.sessions.touch(session_id)
    await self.uow.commit()
    return message, event
```

.1.6.7.1 这段代码的业务流程

​        这是本节最关键的一段业务代码。

```Plain
POST /api/sessions/{session_id}/messages
  |
  v
检查会话是否存在
  |
  v
清理消息内容
  |
  v
写入用户消息
  |
  v
写入 message_created 事件
  |
  v
更新会话时间
  |
  v
提交事务
```

.1.6.7.2 为什么这样设计

​        发送消息不是单表写入。

​        如果只写消息，不写事件，本章后文就没有事件流可以展示。

​        如果写了消息和事件但没有统一事务，就可能出现消息成功、事件失败的数据不一致。

#### 7.1.6.8 扩展 API Schema 和路由

​        打开 `backend/api/app/schemas/session.py`，新增消息和事件响应：

```Python
class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    created_at: datetime

class SessionEventResponse(BaseModel):
    id: UUID
    session_id: UUID
    type: str
    payload: dict
    created_at: datetime
```

​        打开 `backend/api/app/api/routes/sessions.py`，新增发送消息接口：

```Python
@router.post(
    "/{session_id}/messages",
    response_model=ApiResponse[MessageCreateResponse],
)
async def create_message(
    session_id: UUID,
    payload: MessageCreateRequest,
    service: SessionService = Depends(build_session_service),
) -> ApiResponse[MessageCreateResponse]:
    message, event = await service.create_user_message(
        session_id=session_id,
        content=payload.content,
    )
    return ApiResponse(
        data=MessageCreateResponse(
            message=to_message_response(message),
            event=to_event_response(event),
        )
    )
```

.1.6.8.1 这段代码的业务流程

​        前端发送：

```JSON
{"content":"帮我规划一个学习任务"}
```

​        后端返回：

```JSON
{
  "message": {
    "role": "user",
    "content": "帮我规划一个学习任务"
  },
  "event": {
    "type": "message_created"
  }
}
```

​        前端收到后会重新加载消息和事件，让页面展示数据库里的最新结果。

#### 7.1.6.9 定义前端类型和 API 函数

​        打开 `frontend/web/app/types.ts`，新增：

```TypeScript
export type ChatMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type SessionEventItem = {
  id: string;
  session_id: string;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};
```

​        创建 `frontend/web/app/lib/session-api.ts`，把会话相关请求集中到一个文件：

```TypeScript
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
```

.1.6.9.1 为什么这样设计

​        `requestApi()` 是通用请求工具。

​        `session-api.ts` 是会话模块 API。

​        这样组件和 store 不需要记住每个接口路径，也不用知道响应外层是 `ApiResponse`。

#### 7.1.6.10 使用 zustand 管理会话工作台状态

​        创建 `frontend/web/app/stores/session-store.ts`。

​        状态结构如下：

```TypeScript
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
```

​        发送消息 action：

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
    await sendMessage(sessionId, content);
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

.1.6.10.1 这段代码的业务流程

​        用户点击发送：

```Plain
ChatInput
  |
  v
store.sendMessage()
  |
  v
POST /api/sessions/{id}/messages
  |
  v
重新加载消息和事件
  |
  v
清空输入框
```

.1.6.10.2 为什么这样设计

​        发送消息后不直接把返回值塞进数组，而是重新加载消息和事件。

​        这样页面展示以数据库为准。后续后端如果同时生成 assistant 消息、计划事件或工具事件，前端刷新后都能拿到完整结果。

#### 7.1.6.11 用 hook 组织页面联动

​        创建 `frontend/web/app/hooks/use-session-workspace.ts`：

```TypeScript
export function useSessionWorkspace() {
  const store = useSessionStore();

  useEffect(() => {
    store.refreshSessions();
  }, []);

  useEffect(() => {
    if (store.selectedSessionId) {
      store.loadSessionDetail(store.selectedSessionId);
    }
  }, [store.selectedSessionId]);

  const sessionItems = store.sessions.type === "ready" ? store.sessions.data : [];
  const selectedSession = useMemo(
    () =>
      sessionItems.find((item) => item.id === store.selectedSessionId) ?? null,
    [sessionItems, store.selectedSessionId],
  );

  return {
    ...store,
    selectedSession,
    sessionItems,
  };
}
```

.1.6.11.1 这段代码的业务流程

​        页面打开时，hook 自动加载会话列表。

​        选中会话变化时，hook 自动加载对应消息和事件。

```Plain
selectedSessionId 改变
  |
  v
loadSessionDetail()
  |
  +-- GET messages
  +-- GET events
```

.1.6.11.2 为什么这样设计

​        store 管状态和动作，hook 管页面生命周期。

​        这样 `page.tsx` 不需要堆很多 `useEffect`，组件也不需要知道什么时候该请求数据。

#### 7.1.6.12 拆分聊天组件

​        本节新增这些组件：

```Plain
frontend/web/app/components/chat-input.tsx
frontend/web/app/components/message-timeline.tsx
frontend/web/app/components/event-timeline.tsx
frontend/web/app/components/chat-workspace.tsx
```

​        `ChatInput` 只负责输入和发送：

```TypeScript
export function ChatInput({
  disabled,
  draft,
  onDraftChange,
  onSend,
  sending,
}: ChatInputProps) {
  return (
    <form onSubmit={(event) => {
      event.preventDefault();
      onSend();
    }}>
      <textarea
        disabled={disabled || sending}
        onChange={(event) => onDraftChange(event.target.value)}
        value={draft}
      />
      <button disabled={disabled || sending} type="submit">
        发送
      </button>
    </form>
  );
}
```

​        `MessageTimeline` 负责展示消息加载中、错误、空状态和消息气泡。

​        `EventTimeline` 负责展示事件记录。

​        `ChatWorkspace` 负责把输入框、消息时间线和事件面板组合起来。

.1.6.12.1 为什么这样设计

​        聊天界面很容易变复杂。

​        如果把输入框、消息气泡、事件面板都写在 `page.tsx`，后续接入 SSE、工具事件、附件消息时会越来越难维护。

​        按组件拆分后，每个文件都有清晰职责：

```Plain
ChatInput        输入和发送
MessageTimeline  消息展示
EventTimeline    事件展示
ChatWorkspace    聊天区域组合
```

#### 7.1.6.13 让 page.tsx 只做页面编排

​        打开 `frontend/web/app/page.tsx`。

​        现在页面通过 hook 拿到工作台状态：

```TypeScript
const workspace = useSessionWorkspace();
```

​        侧边栏使用 store action：

```TypeScript
<AppSidebar
  actionError={workspace.actionError}
  onCreateSession={workspace.createSession}
  onDeleteSession={workspace.deleteSession}
  onRefresh={refreshAll}
  onSelectSession={workspace.selectSession}
  onTitleChange={workspace.setTitle}
  selectedSessionId={workspace.selectedSessionId}
  sessions={workspace.sessions}
  submitting={workspace.submitting}
  title={workspace.title}
/>
```

​        聊天区域使用拆分后的组件：

```TypeScript
<ChatWorkspace
  draft={workspace.draft}
  events={workspace.events}
  messages={workspace.messages}
  onDraftChange={workspace.setDraft}
  onSend={workspace.sendMessage}
  selectedSession={workspace.selectedSession}
  sending={workspace.sendingMessage}
/>
```

.1.6.13.1 这段代码的业务流程

​        `page.tsx` 不直接知道如何发送消息。

​        它只把 `workspace.sendMessage` 传给聊天组件。

​        真正的业务动作在 store 中完成，页面只负责把区域摆出来。

#### 7.1.6.14 对照前端完整文件

​        前面步骤为了讲清楚业务流，展示了关键片段。

​        下面给出本节前端新增和重点修改文件的完整代码。实际编写时，新增文件应该以这里的完整代码为准；如果你前面已经按片段写过，可以用本节逐个对照。

.1.6.14.1 frontend/web/app/lib/session-api.ts

```TypeScript
import { requestApi } from "./api";
import type {
  ChatMessage,
  MessageCreateData,
  MessageListData,
  SessionEventItem,
  SessionEventListData,
  SessionItem,
  SessionListData,
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
```

​        这个文件只负责会话模块的接口调用。

​        组件和 store 不直接拼接口响应结构，而是调用这里的函数。这样后续接口路径变化时，优先改这个文件。

.1.6.14.2 frontend/web/app/stores/session-store.ts

```TypeScript
import { create } from "zustand";

import {
  createSession,
  deleteSession,
  fetchEvents,
  fetchMessages,
  fetchSessions,
  sendMessage,
} from "../lib/session-api";
import type {
  ChatMessage,
  LoadState,
  SessionEventItem,
  SessionItem,
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
        await sendMessage(sessionId, content);
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

​        这个文件是本节前端的业务状态中心。

​        组件不直接请求接口，`page.tsx` 也不保存聊天业务状态。发送消息、创建会话、删除会话、加载详情都在 store 里完成。

.1.6.14.3 frontend/web/app/hooks/use-session-workspace.ts

```TypeScript
import { useEffect, useMemo } from "react";

import { useSessionStore } from "../stores/session-store";

export function useSessionWorkspace() {
  const store = useSessionStore();

  useEffect(() => {
    store.refreshSessions();
  }, []);

  useEffect(() => {
    if (store.selectedSessionId) {
      store.loadSessionDetail(store.selectedSessionId);
    }
  }, [store.selectedSessionId]);

  const sessionItems = store.sessions.type === "ready" ? store.sessions.data : [];
  const selectedSession = useMemo(
    () =>
      sessionItems.find((item) => item.id === store.selectedSessionId) ?? null,
    [sessionItems, store.selectedSessionId],
  );

  return {
    ...store,
    selectedSession,
    sessionItems,
  };
}
```

​        这个 hook 负责页面生命周期和派生数据。

​        页面打开时加载会话列表；选中会话变化时加载消息和事件；`selectedSession` 从会话列表中计算出来。

.1.6.14.4 frontend/web/app/components/chat-input.tsx

```TypeScript
import { SendHorizontal } from "lucide-react";

type ChatInputProps = {
  disabled: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  sending: boolean;
};

export function ChatInput({
  disabled,
  draft,
  onDraftChange,
  onSend,
  sending,
}: ChatInputProps) {
  return (
    <form
      className="border-t border-slate-200 bg-white p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSend();
      }}
    >
      <div className="flex items-end gap-3">
        <textarea
          className="min-h-20 flex-1 resize-none rounded-md border border-slate-200 px-3 py-3 text-sm outline-none transition focus:border-slate-400 disabled:bg-slate-50"
          disabled={disabled || sending}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder={disabled ? "先创建或选择一个会话" : "输入任务内容"}
          value={draft}
        />
        <button
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-950 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          disabled={disabled || sending}
          title="发送消息"
          type="submit"
        >
          <SendHorizontal size={18} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
```

​        `ChatInput` 只关心输入框和发送按钮。

​        它不直接调用接口，而是通过 `onSend` 通知外层。这样它可以被复用，也更容易测试。

.1.6.14.5 frontend/web/app/components/message-timeline.tsx

```TypeScript
import { Bot, UserRound } from "lucide-react";

import { formatDate } from "../lib/format";
import type { ChatMessage, LoadState } from "../types";

export function MessageTimeline({
  state,
}: {
  state: LoadState<ChatMessage[]>;
}) {
  if (state.type === "loading") {
    return <div className="p-5 text-sm text-slate-500">消息加载中...</div>;
  }

  if (state.type === "error") {
    return (
      <div className="m-5 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
        {state.message}
      </div>
    );
  }

  if (state.data.length === 0) {
    return (
      <div className="flex min-h-72 items-center justify-center p-5 text-sm text-slate-500">
        暂无消息，发送第一条任务内容
      </div>
    );
  }

  return (
    <div className="grid gap-4 p-5">
      {state.data.map((message) => {
        const isUser = message.role === "user";
        const Icon = isUser ? UserRound : Bot;

        return (
          <div
            className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
            key={message.id}
          >
            {!isUser ? (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-600">
                <Icon size={16} aria-hidden="true" />
              </div>
            ) : null}
            <div
              className={`max-w-[70%] rounded-md px-4 py-3 text-sm leading-6 ${
                isUser
                  ? "bg-slate-950 text-white"
                  : "border border-slate-200 bg-white text-slate-800"
              }`}
            >
              <div className="whitespace-pre-wrap">{message.content}</div>
              <div
                className={`mt-2 text-xs ${
                  isUser ? "text-slate-300" : "text-slate-400"
                }`}
              >
                {formatDate(message.created_at)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

​        `MessageTimeline` 负责四种展示状态：加载中、错误、空消息、消息列表。

​        它不维护状态，也不发请求，只根据 `state` 渲染界面。

.1.6.14.6 frontend/web/app/components/event-timeline.tsx

```TypeScript
import { Activity } from "lucide-react";

import { formatDate } from "../lib/format";
import type { LoadState, SessionEventItem } from "../types";

export function EventTimeline({
  state,
}: {
  state: LoadState<SessionEventItem[]>;
}) {
  if (state.type === "loading") {
    return <div className="text-sm text-slate-500">事件加载中...</div>;
  }

  if (state.type === "error") {
    return <div className="text-sm text-rose-600">{state.message}</div>;
  }

  if (state.data.length === 0) {
    return <div className="text-sm text-slate-500">暂无事件</div>;
  }

  return (
    <div className="grid gap-2">
      {state.data.map((event) => (
        <div
          className="flex gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
          key={event.id}
        >
          <Activity className="mt-0.5 shrink-0 text-slate-500" size={15} />
          <div className="min-w-0">
            <div className="text-sm font-medium text-slate-800">
              {event.type}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {formatDate(event.created_at)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

​        事件面板现在只展示事件类型和时间。后续事件 payload 变丰富后，可以继续在这个组件里扩展不同事件的展示方式。

.1.6.14.7 frontend/web/app/components/chat-workspace.tsx

```TypeScript
import { ChatInput } from "./chat-input";
import { EventTimeline } from "./event-timeline";
import { MessageTimeline } from "./message-timeline";
import type {
  ChatMessage,
  LoadState,
  SessionEventItem,
  SessionItem,
} from "../types";

type ChatWorkspaceProps = {
  draft: string;
  events: LoadState<SessionEventItem[]>;
  messages: LoadState<ChatMessage[]>;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  selectedSession: SessionItem | null;
  sending: boolean;
};

export function ChatWorkspace({
  draft,
  events,
  messages,
  onDraftChange,
  onSend,
  selectedSession,
  sending,
}: ChatWorkspaceProps) {
  return (
    <section className="grid grid-cols-[1fr_280px] gap-5 max-xl:grid-cols-1">
      <div className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-slate-200 bg-slate-50">
        <MessageTimeline state={messages} />
        <div className="mt-auto">
          <ChatInput
            disabled={!selectedSession}
            draft={draft}
            onDraftChange={onDraftChange}
            onSend={onSend}
            sending={sending}
          />
        </div>
      </div>

      <aside className="rounded-md border border-slate-200 bg-white p-5">
        <h2 className="text-base font-semibold text-slate-950">事件记录</h2>
        <p className="mt-1 text-sm text-slate-500">
          本章先展示消息创建事件
        </p>
        <div className="mt-4">
          <EventTimeline state={events} />
        </div>
      </aside>
    </section>
  );
}
```

​        `ChatWorkspace` 是聊天区域的组合组件。

​        它不直接管理请求，也不保存草稿，只把 store 传来的状态继续分发给输入框、消息时间线和事件时间线。

.1.6.14.8 frontend/web/app/components/app-sidebar.tsx

​        第 6 章已经有侧边栏组件。本节需要把创建会话表单的提交方式改成普通回调，不再把表单事件传给页面。

​        完整代码如下：

```TypeScript
import { Bot, MessageSquare, Plus, RefreshCw } from "lucide-react";

import { SessionList } from "./session-list";
import type { LoadState, SessionItem } from "../types";

type AppSidebarProps = {
  actionError: string | null;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onRefresh: () => void;
  onSelectSession: (sessionId: string) => void;
  selectedSessionId: string | null;
  sessions: LoadState<SessionItem[]>;
  submitting: boolean;
  title: string;
  onTitleChange: (value: string) => void;
};

export function AppSidebar({
  actionError,
  onCreateSession,
  onDeleteSession,
  onRefresh,
  onSelectSession,
  selectedSessionId,
  sessions,
  submitting,
  title,
  onTitleChange,
}: AppSidebarProps) {
  return (
    <aside className="border-r border-slate-200 bg-white px-4 py-5 max-lg:border-b max-lg:border-r-0">
      <div className="flex items-center gap-3 px-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-950 text-white">
          <Bot size={22} aria-hidden="true" />
        </div>
        <div>
          <div className="text-base font-semibold leading-5">AtlasAgent</div>
          <div className="mt-1 text-xs text-slate-500">Agent Workspace</div>
        </div>
      </div>

      <form
        className="mt-6 grid gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          onCreateSession();
        }}
      >
        <label className="text-xs font-medium text-slate-500" htmlFor="title">
          新建会话
        </label>
        <div className="flex gap-2">
          <input
            className="h-10 min-w-0 flex-1 rounded-md border border-slate-200 px-3 text-sm outline-none transition focus:border-slate-400"
            id="title"
            maxLength={200}
            onChange={(event) => onTitleChange(event.target.value)}
            placeholder="输入任务标题"
            value={title}
          />
          <button
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-950 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={submitting}
            title="创建会话"
            type="submit"
          >
            <Plus size={18} aria-hidden="true" />
          </button>
        </div>
      </form>

      <div className="mt-6 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <MessageSquare size={17} aria-hidden="true" />
          <span>会话列表</span>
        </div>
        <button
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-950"
          onClick={onRefresh}
          title="刷新"
          type="button"
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>

      <SessionList
        onDelete={onDeleteSession}
        onSelect={onSelectSession}
        selectedId={selectedSessionId}
        state={sessions}
      />

      {actionError ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {actionError}
        </div>
      ) : null}
    </aside>
  );
}
```

​        `AppSidebar` 仍然只负责侧边栏展示。

​        创建、删除、刷新这些动作都由外层传入。本节这些动作最终来自 zustand store。

.1.6.14.9 frontend/web/app/page.tsx

​        最后对照页面入口文件。

​        完整代码如下：

```TypeScript
"use client";

import { CheckCircle2, Clock3, Wifi } from "lucide-react";
import { useEffect, useState } from "react";

import { AppSidebar } from "./components/app-sidebar";
import { ChatWorkspace } from "./components/chat-workspace";
import { SessionPanel } from "./components/session-panel";
import { StatusBadge } from "./components/status-badge";
import { StatusPanel } from "./components/status-panel";
import { useSessionWorkspace } from "./hooks/use-session-workspace";
import { requestApi } from "./lib/api";
import type {
  ApiStatusData,
  DatabaseStatusData,
  LoadState,
  StatusBadgeView,
} from "./types";

export default function Home() {
  const [apiStatus, setApiStatus] = useState<LoadState<ApiStatusData>>({
    type: "loading",
  });
  const [databaseStatus, setDatabaseStatus] = useState<
    LoadState<DatabaseStatusData>
  >({ type: "loading" });
  const workspace = useSessionWorkspace();

  async function loadStatus() {
    const [apiData, databaseData] = await Promise.all([
      requestApi<ApiStatusData>("/api/status"),
      requestApi<DatabaseStatusData>("/api/status/database"),
    ]);
    setApiStatus({ type: "ready", data: apiData });
    setDatabaseStatus({ type: "ready", data: databaseData });
  }

  async function refreshAll() {
    workspace.setActionError(null);
    try {
      await Promise.all([loadStatus(), workspace.refreshSessions()]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setApiStatus((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      setDatabaseStatus((current) =>
        current.type === "loading" ? { type: "error", message } : current,
      );
      workspace.setActionError(message);
    }
  }

  useEffect(() => {
    loadStatus().catch((error) => {
      const message = error instanceof Error ? error.message : "unknown error";
      setApiStatus({ type: "error", message });
      setDatabaseStatus({ type: "error", message });
    });
  }, []);

  const apiBadge = getBadge(apiStatus, "API 正常", "API 异常");
  const dbBadge = getBadge(databaseStatus, "数据库正常", "数据库异常");

  return (
    <main className="min-h-screen bg-[#f6f7f9] text-slate-950">
      <div className="grid min-h-screen grid-cols-[320px_1fr] max-lg:grid-cols-1">
        <AppSidebar
          actionError={workspace.actionError}
          onCreateSession={workspace.createSession}
          onDeleteSession={workspace.deleteSession}
          onRefresh={refreshAll}
          onSelectSession={workspace.selectSession}
          onTitleChange={workspace.setTitle}
          selectedSessionId={workspace.selectedSessionId}
          sessions={workspace.sessions}
          submitting={workspace.submitting}
          title={workspace.title}
        />

        <section className="flex min-w-0 flex-col">
          <header className="flex min-h-16 items-center justify-between border-b border-slate-200 bg-white px-6 max-sm:flex-col max-sm:items-start max-sm:gap-3 max-sm:px-4 max-sm:py-4">
            <div>
              <h1 className="text-xl font-semibold tracking-normal text-slate-950">
                {workspace.selectedSession?.title ?? "工作台"}
              </h1>
              <p className="mt-1 text-sm text-slate-500">
                创建会话后，可以发送第一条任务消息
              </p>
            </div>
            <div className="flex gap-2 max-sm:flex-wrap">
              <StatusBadge badge={apiBadge} />
              <StatusBadge badge={dbBadge} />
            </div>
          </header>

          <div className="grid gap-5 p-6 max-sm:p-4">
            <section className="grid grid-cols-[1fr_1fr] gap-5 max-xl:grid-cols-1">
              <StatusPanel
                apiStatus={apiStatus}
                databaseStatus={databaseStatus}
              />
              <SessionPanel selectedSession={workspace.selectedSession} />
            </section>

            <ChatWorkspace
              draft={workspace.draft}
              events={workspace.events}
              messages={workspace.messages}
              onDraftChange={workspace.setDraft}
              onSend={workspace.sendMessage}
              selectedSession={workspace.selectedSession}
              sending={workspace.sendingMessage}
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function getBadge<T>(
  state: LoadState<T>,
  readyLabel: string,
  errorLabel: string,
): StatusBadgeView {
  if (state.type === "ready") {
    return {
      label: readyLabel,
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
      icon: CheckCircle2,
    };
  }
  if (state.type === "error") {
    return {
      label: errorLabel,
      className: "border-rose-200 bg-rose-50 text-rose-700",
      icon: Wifi,
    };
  }
  return {
    label: "检测中",
    className: "border-slate-200 bg-white text-slate-600",
    icon: Clock3,
  };
}
```

​        这个文件现在只做三件事：

​        `page.tsx` 现在只做页面编排：查询 API 和数据库状态，调用 `useSessionWorkspace()` 获得会话工作台状态，再把状态和动作分发给侧边栏、状态面板、会话详情和聊天工作区。真正的数据操作已经进入 store，选中会话后的联动加载也进入 hook，页面文件不再承担所有业务状态。

### 7.1.7 关键理解

​        本节最重要的是理解消息和事件的区别。

```Plain
消息：适合展示给用户看的对话内容
事件：适合描述系统执行过程
```

​        本节的 `message_created` 事件看起来很简单，但它建立了后续事件流的基本形状。

​        本章后文接入 SSE 后，事件会从“刷新后展示”变成“服务端边产生、前端边接收”。

​        第二个重点是前端状态分层。

```Plain
lib      负责请求
store    负责状态和动作
hook     负责页面生命周期
component负责展示和交互
page     负责页面组合
```

​        这套分层能让后续聊天页面继续扩展，而不是把所有逻辑塞进一个页面文件。

### 7.1.8 技术难点与亮点

​        技术难点：

​        本节的技术难点，集中在一致性和前端状态边界上。一次发送消息会写两张表，还会更新会话时间，所以必须放在一个事务里完成。事件 `payload` 使用 JSONB，是因为事件负载会随着类型变化，不适合全都拆成固定字段。前端引入 zustand 后，也要分清 store、hook、component 的职责：store 管状态和动作，hook 管页面联动，component 管展示和用户交互。

​        项目亮点：

​        本节的项目亮点，是 AtlasAgent 从这里开始有了真正的消息时间线。事件表为后续 SSE、Agent 执行过程和工具调用展示打基础，前端也提前完成组件、hooks、store 拆分，后续复杂状态不会继续堆在 `page.tsx` 里。

### 7.1.9 面试考点

​        面试里可以围绕几个问题展开：为什么聊天系统需要事件表，而不是只保存消息表；为什么发送消息要放在一个事务里完成；PostgreSQL `JSONB` 适合存什么数据；zustand store、React hook、组件分别适合放什么逻辑；为什么 `page.tsx` 不应该承载全部业务状态。能把这些讲清楚，说明你理解的是一个可演进的 Agent 工作台，而不是只会写聊天框。

### 7.1.10 运行验证

​        下面命令默认在项目根目录执行。

#### 7.1.10.1 安装前端依赖

​        如果还没有安装本节依赖，执行：

```Bash
cd frontend/web
pnpm install
```

​        确认 zustand 已安装：

```Bash
pnpm list zustand
```

​        预期能看到类似：

```Plain
zustand 5.0.14
```

#### 7.1.10.2 检查前端类型

```Bash
pnpm typecheck
```

​        预期没有 TypeScript 报错。

#### 7.1.10.3 启动服务并执行迁移

​        回到项目根目录：

```Bash
cd /Users/atlas/Desktop/github/atlas-agents
```

​        本节同时修改了 API 和 UI 代码，所以需要重新构建这两个镜像。

​        执行：

```Bash
docker compose build api ui
```

​        这一步会把本节新增的后端接口和前端聊天输入框打进 Docker 镜像。

​        如果跳过这一步，只执行 `docker compose up -d nginx`，浏览器可能仍然看到第 6 章的旧页面，也就看不到聊天输入框。

​        构建完成后启动服务：

```Bash
docker compose up -d nginx
```

​        执行迁移：

```Bash
docker compose exec api uv run alembic upgrade head
```

​        预期迁移会执行到：

```Plain
202606030002
```

#### 7.1.10.4 创建会话

​        执行：

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 9 章测试会话"}'
```

​        返回中会包含会话 `id`。

#### 7.1.10.5 发送消息

​        把上一步返回的 `id` 替换到下面命令中：

```Bash
curl -X POST http://localhost:8088/api/sessions/{session_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"帮我规划一个 AI Agent 学习任务"}'
```

​        预期返回：

```JSON
{
  "code": 200,
  "message": "success",
  "data": {
    "message": {
      "role": "user",
      "content": "帮我规划一个 AI Agent 学习任务"
    },
    "event": {
      "type": "message_created"
    }
  }
}
```

#### 7.1.10.6 查询消息和事件

​        查询消息：

```Bash
curl http://localhost:8088/api/sessions/{session_id}/messages
```

​        查询事件：

```Bash
curl http://localhost:8088/api/sessions/{session_id}/events
```

​        预期消息列表里有刚才发送的用户消息，事件列表里有 `message_created`。

#### 7.1.10.7 验证页面

​        访问：

```Plain
http://localhost:8088
```

​        在页面里：

​        验证时创建或选择一个会话，在聊天输入框输入任务内容，然后点击发送按钮。正常情况下，消息时间线会出现用户消息，事件记录会出现 `message_created`。这说明前端输入、后端写消息、后端写事件、事务提交和前端刷新已经连成一条线。

​        如果页面仍然是第 6 章的样子，或者没有看到聊天输入框，说明浏览器访问到的还是旧 UI 构建产物。

​        可以执行：

```Bash
docker compose build ui
docker compose up -d ui nginx
```

​        然后刷新浏览器。

### 7.1.11 小结

​        本节完成了基础聊天工作台。后端新增消息和事件领域实体，新增 `session_messages` 和 `session_events` 表，补齐消息和事件 Repository，并在发送消息时同时写入消息和事件。接口层新增消息列表和事件列表，前端则引入 zustand store，新增聊天输入框、消息时间线和事件记录面板，`page.tsx` 进一步收敛为页面编排文件。

​        从这一阶段开始，会话已经可以承载真实输入。下一步会让事件从普通查询升级为流式推送。

## 7.2 SSE 事件如流

### 7.2.1 本节目标

​        前文已经能保存消息和事件，但前端仍然是“请求发出去，等后端处理完，再一次性刷新”。这种模式适合很短的接口，不适合 Agent。真正的 Agent 执行过程会不断产生中间状态：收到任务、生成计划、执行步骤、调用工具、观察结果、继续推理。用户不应该等到所有事情结束后才看到结果。
​        本节引入 SSE，也就是 Server-Sent Events。读者会编写 `text/event-stream` 响应，通过 Nginx 正确代理流式响应，在前端用 `fetch` 读取 `ReadableStream`，并解析 SSE 中的 `event:` 和 `data:` 数据块。前端的 zustand store 会边读流边更新事件面板，同时保留前文的一次性消息接口，新增一个流式消息接口。这样后续 Agent 执行事件就有了实时展示的基础。

### 7.2.2 最终效果

​        本节结束后，发送消息不再只是等待接口返回完整 JSON。前端会边读取 SSE 流，边把服务端推送的事件展示到事件面板里。

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

### 7.2.3 本节要解决的问题

​        前文已经实现了消息和事件持久化。但前文的前端仍然是这种模式：

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

​        这些过程不应该等全部完成后一次性返回。更好的体验是服务端每产生一个事件，前端就展示一个事件。所以本节引入 SSE，让事件从“事后查询”逐步走向“实时推送”。

### 7.2.4 本节技术方案

​        本节先做一个最小流式闭环。

​        后端保留前文的接口：

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
frontend/web/app/lib/sse.ts
  |
  +-- 解析 text/event-stream

frontend/web/app/lib/session-api.ts
  |
  +-- 调用 stream 接口

frontend/web/app/stores/session-store.ts
  |
  +-- 发送消息
  +-- 接收流式事件
  +-- 更新事件面板
```

​        本节暂时不实现真正的 Agent 执行，不生成 assistant 消息，不做停止任务，也不做断线重连、历史事件增量游标和多事件类型的复杂渲染。现在先让浏览器能稳定读取流，后面再把更多事件类型接进来。

### 7.2.5 新增和修改的文件

```Plain
README.md
backend/api/README.md
frontend/web/README.md
nginx/README.md
nginx/default.conf
backend/api/app/api/sse.py
backend/api/app/api/routes/sessions.py
frontend/web/app/types.ts
frontend/web/app/lib/sse.ts
frontend/web/app/lib/session-api.ts
frontend/web/app/stores/session-store.ts
docs/course/chapters/10-sse-events.md
```

### 7.2.6 实施步骤
#### 7.2.6.1 理解 SSE 数据格式

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

.2.6.1.1 关键理解

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

​        本节先用两条事件演示这个机制。

#### 7.2.6.2 编写后端 SSE 编码工具

​        创建 `backend/api/app/api/sse.py`：

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

.2.6.2.1 这段代码的业务流程

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

.2.6.2.2 为什么这样设计

​        SSE 格式很简单，但手写时容易漏掉最后的空行。

​        封装成 `encode_sse()` 后，路由里只需要关心事件名和数据内容。

​        `default=str` 用来处理 `datetime`、`UUID` 这类 JSON 默认不能直接序列化的对象。

#### 7.2.6.3 新增流式消息接口

​        打开 `backend/api/app/api/routes/sessions.py`，新增这些 import：

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

.2.6.3.1 这段代码的业务流程

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

.2.6.3.2 关键代码逐段解释

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

.2.6.3.3 为什么这样设计

​        本节的流式接口不是为了替代数据库，而是为了把“事件产生过程”推给前端。

​        数据库仍然是最终状态来源。流结束后，前端会重新加载消息和事件，保证页面和数据库一致。

#### 7.2.6.4 配置 Nginx 支持流式代理

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

.2.6.4.1 为什么这样设计

​        Nginx 默认可能会缓冲后端响应。

​        普通 JSON 接口不怕缓冲，但 SSE 需要服务端发一条，浏览器尽快收到一条。

​        所以这里关闭 `/api/` 的代理缓冲：

```Nginx
proxy_buffering off;
```

#### 7.2.6.5 定义前端流式事件类型

​        打开 `frontend/web/app/types.ts`，新增：

```TypeScript
export type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};
```

.2.6.5.1 这段代码的业务流程

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

#### 7.2.6.6 编写前端 SSE 解析工具

​        创建 `frontend/web/app/lib/sse.ts`：

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

.2.6.6.1 这段代码的业务流程

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

.2.6.6.2 常见误区

​        不要假设一次 `reader.read()` 就能读到完整事件。

​        网络传输会把数据切成不固定大小的 chunk。必须用 buffer 累积，再按 SSE 的空行分隔解析。

#### 7.2.6.7 封装流式发送 API

​        打开 `frontend/web/app/lib/session-api.ts`，新增 import：

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

.2.6.7.1 这段代码的业务流程

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

#### 7.2.6.8 在 store 中消费流式事件

​        打开 `frontend/web/app/stores/session-store.ts`，把 `sendMessage` import 换成：

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

.2.6.8.1 这段代码的业务流程

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

#### 7.2.6.9 对照关键完整文件

​        下面给出本节新增和重点修改文件的完整代码。

.2.6.9.1 backend/api/app/api/sse.py

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

.2.6.9.2 frontend/web/app/lib/sse.ts

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

.2.6.9.3 frontend/web/app/lib/session-api.ts

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

.2.6.9.4 frontend/web/app/stores/session-store.ts

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

.2.6.9.5 nginx/default.conf

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

### 7.2.7 关键理解

​        SSE 不是新的数据库模型，也不是 WebSocket。

​        它是一个普通 HTTP 连接，只是响应不会立刻结束，而是持续写出事件。

​        本节的链路是：

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

​        这里有一个重要取舍：本节仍然在流结束后重新加载消息和事件。

​        原因是流式事件适合展示过程，数据库查询适合确认最终状态。两者结合，页面既能及时反馈，又不容易和后端状态脱节。

### 7.2.8 技术难点与亮点

​        技术难点：

​        本节的技术难点集中在流式数据的边界上。SSE 事件必须用空行分隔，前端不能假设一次读取就是一条完整事件，所以需要维护 buffer。Nginx 代理需要关闭缓冲，避免流式响应被攒起来一次性返回。store 也要边读流边更新事件面板，同时在流结束后刷新最终状态。

​        项目亮点：

​        本节的亮点，是消息接口开始具备流式能力。前端不引入额外依赖，直接使用浏览器原生流读取能力；Nginx 网关开始为后续长任务事件流做准备；第 8 章也可以自然扩展运行状态、停止任务和未读数。

### 7.2.9 面试考点

​        面试里可以重点讲清楚：SSE 和普通 JSON 接口有什么区别，SSE 和 WebSocket 的区别是什么，为什么 SSE 响应需要 `text/event-stream`，为什么前端读取 SSE 要维护 buffer，以及为什么 Nginx 代理 SSE 时要关闭缓冲。能回答这些问题，就说明你理解的是流式链路，而不是只复制了一个响应头。

### 7.2.10 运行验证

​        下面命令默认在项目根目录执行。

#### 7.2.10.1 重新构建 API 和 UI

​        本节修改了 API、UI 和 Nginx 配置。

​        执行：

```Bash
docker compose build api ui
docker compose up -d nginx
```

​        如果 Nginx 配置没有刷新，可以重新创建 Nginx 容器：

```Bash
docker compose up -d --force-recreate nginx
```

#### 7.2.10.2 执行迁移

​        如果前文已经执行过迁移，这一步不会重复创建表。

```Bash
docker compose exec api uv run alembic upgrade head
```

#### 7.2.10.3 创建会话

```Bash
curl -X POST http://localhost:8088/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"第 10 章 SSE 测试"}'
```

​        记录返回结果里的 `id`。

#### 7.2.10.4 验证 SSE 接口

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

#### 7.2.10.5 验证页面

​        访问：

```Plain
http://localhost:8088
```

​        在页面中：

​        验证时选择一个会话，输入任务内容并点击发送。正常情况下，事件记录会先出现 `message_created`，流结束后消息时间线出现用户消息。这说明前端已经不是等完整 JSON 返回，而是在读取服务端推送的流式事件。

### 7.2.11 小结

​        本节完成了第一个 SSE 流式闭环。后端新增 SSE 编码工具和消息流式接口，Nginx 对 `/api/` 关闭代理缓冲，前端新增 SSE 解析工具，并在发送消息时改为读取流式响应。store 现在可以边读事件边更新事件面板，这为后续长时间 Agent 执行打下了基础。

​        从这一阶段开始，事件不再只能通过普通查询获取。后续 Agent 执行、工具调用、计划更新都可以沿着这条流式链路继续扩展。

## 7.3 本章小结

​        完成“对话输入与消息事件”和“SSE 事件如流”两个阶段后，这条能力链已经形成闭环。读者仍然可以在每个阶段结束时单独运行验证，但理解上应把两者视作一个连续决策：先建立可靠边界，再让上层能力真正依赖它。

---

[← 第六章. 会话开立与左侧列表](06-会话开立与左侧列表.md) · [返回目录](../README.md) · [第八章. 会话状态与任务收放 →](08-会话状态与任务收放.md)
