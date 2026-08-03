from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


# ===================== 第1步：定义 Memory 中允许出现的消息角色 =====================
class MemoryRole(StrEnum):
    """Agent Memory 中的消息角色。

    user 表示用户输入，assistant 表示 Agent 输出，tool 表示工具执行结果。
    """

    user = "user"
    assistant = "assistant"
    tool = "tool"


# ===================== 第2步：定义 Memory 中的一条消息 =====================
@dataclass(slots=True)
class MemoryMessage:
    """Agent 运行时放入上下文的一条消息。"""

    id: UUID
    role: MemoryRole
    content: str
    created_at: datetime
    name: str | None = None


# ===================== 第3步：定义一个轻量 Memory 容器 =====================
@dataclass(slots=True)
class ConversationMemory:
    """保存一次 Agent 演示过程中的上下文消息。"""

    messages: list[MemoryMessage] = field(default_factory=list)

    def add_user_message(self, content: str) -> MemoryMessage:
        """把用户任务放入 Memory。"""

        return self._append(role=MemoryRole.user, content=content)

    def add_assistant_message(self, content: str) -> MemoryMessage:
        """把 Agent 的文字回复放入 Memory。"""

        return self._append(role=MemoryRole.assistant, content=content)

    def add_tool_message(self, tool_name: str, content: str) -> MemoryMessage:
        """把工具执行结果放入 Memory。

        name 字段保存工具名，方便后续模型知道这条消息来自哪个工具。
        """

        return self._append(role=MemoryRole.tool, content=content, name=tool_name)

    def list_messages(self) -> list[MemoryMessage]:
        """返回当前 Memory 的全部消息。"""

        return list(self.messages)

    def _append(
        self,
        role: MemoryRole,
        content: str,
        name: str | None = None,
    ) -> MemoryMessage:
        """统一创建消息，避免每个 add_* 方法重复写 id 和时间。"""

        message = MemoryMessage(
            id=uuid4(),
            role=role,
            content=content,
            created_at=datetime.now(UTC),
            name=name,
        )
        self.messages.append(message)
        return message

