"""记忆图谱关联（Memory Graph Links）。

单条记忆往往不是孤立事实：项目事实支撑架构决策、缺陷教训扩展自
某次事故情景。这里在 ``AgentMemory.related_ids`` 上维护一个轻量的
关联图：

- ``link_memories``：在两条记忆之间建立带类型的关联边
  （supports/contradicts/extends/duplicates），双向可见，
  单条记忆的关联边数受 ``memory_graph_max_links`` 上限约束。
- ``expand_context``：检索命中一条记忆时，顺带取出它的直接关联
  记忆，供 MemoryContext 扩展上下文。深度硬上限 1、条数上限
  默认 3，防止上下文爆炸。

关联类型本身记录在记忆 metadata 的 ``graph_relations`` 映射中
（key 为关联记忆的 uuid 字符串），related_ids 只保存 id 集合。
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Awaitable, Callable
from uuid import UUID

from app.core.config import Settings, settings as global_settings
from app.domain.memories.entities import AgentMemory, MemoryStatus
from app.domain.memories.repositories import AgentMemoryRepository


class MemoryRelation(StrEnum):
    """两条记忆之间的关联类型。"""

    supports = "supports"
    contradicts = "contradicts"
    extends = "extends"
    duplicates = "duplicates"


@dataclass(slots=True)
class GraphNeighbour:
    """``expand_context`` 返回的一条关联记忆。

    主体是 ``memory``，``relation`` 是它指向 source 记忆的关联类型
    （从 source 侧的 ``graph_relations`` 元数据中读出）。既支持属性
    访问（``.id``、``.relation``），也支持按 ``(memory, relation)``
    解包，方便调用方按需取用。
    """

    memory: AgentMemory
    relation: MemoryRelation | None

    @property
    def id(self) -> UUID:
        return self.memory.id

    def __getattr__(self, name: str):
        # 未显式定义的属性直接委托给被关联的记忆实体，
        # 让 GraphNeighbour 在读取场景下可以当作 AgentMemory 使用。
        return getattr(self.memory, name)

    def __iter__(self):
        yield self.memory
        yield self.relation


class MemoryGraphService:
    """记忆图谱读写服务。

    依赖只有领域层 ``AgentMemoryRepository`` 协议和一个可选的
    ``commit`` 回调，事务归属由调用方决定。
    """

    def __init__(
        self,
        repository: AgentMemoryRepository,
        *,
        commit: Callable[[], Awaitable[None]] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.commit = commit
        # 未注入 settings 时回退到全局配置对象；参数名遮蔽模块导入，用别名。
        self.settings = settings if settings is not None else global_settings

    # ===================== 第1步：建立关联边 =====================
    async def link_memories(
        self,
        memory_a: UUID | AgentMemory,
        memory_b: UUID | AgentMemory,
        *,
        relation: MemoryRelation | str,
    ) -> tuple[AgentMemory | None, AgentMemory | None]:
        """在两条记忆之间建立双向关联边。

        入参接受记忆实体或记忆 ID（实体免去一次仓库回读）。
        ``relation`` 接受枚举或其字符串值，且只能按关键字传入，
        避免两个实参换位造成关系写反。

        - 已双向关联时直接返回当前实体，幂等且不重写关系类型。
        - 单侧关联（历史脏数据）时补齐另一侧。
        - 任一侧关联边数达到 ``memory_graph_max_links`` 时该侧不再追加，
          防止单条记忆成为上下文爆炸的源头（另一侧照常记录）。
        - 关联类型写在双方 metadata 的 graph_relations 中，
          便于后续解释"为什么这两条记忆一起出现"。
        """
        memory_a = await self._resolve(memory_a)
        memory_b = await self._resolve(memory_b)
        if memory_a.id == memory_b.id:
            raise ValueError("不能把记忆关联到它自己")
        relation = relation if isinstance(relation, MemoryRelation) else MemoryRelation(relation)
        existing_a = memory_a.id in memory_b.related_ids
        existing_b = memory_b.id in memory_a.related_ids
        if existing_a and existing_b:
            return memory_a, memory_b

        updated_a = memory_a
        updated_b = memory_b
        if not existing_b and len(memory_a.related_ids) < self.settings.memory_graph_max_links:
            metadata_a = dict(memory_a.metadata)
            relations_a = dict(metadata_a.get("graph_relations") or {})
            relations_a[str(memory_b.id)] = relation.value
            metadata_a["graph_relations"] = relations_a
            result = await self.repository.update(
                memory_a.id,
                related_ids=[*memory_a.related_ids, memory_b.id],
                metadata=metadata_a,
            )
            if result is not None:
                updated_a = result
        if not existing_a and len(memory_b.related_ids) < self.settings.memory_graph_max_links:
            metadata_b = dict(memory_b.metadata)
            relations_b = dict(metadata_b.get("graph_relations") or {})
            relations_b[str(memory_a.id)] = relation.value
            metadata_b["graph_relations"] = relations_b
            result = await self.repository.update(
                memory_b.id,
                related_ids=[*memory_b.related_ids, memory_a.id],
                metadata=metadata_b,
            )
            if result is not None:
                updated_b = result
        if (updated_a is not memory_a or updated_b is not memory_b) and self.commit is not None:
            await self.commit()
        return updated_a, updated_b

    async def _resolve(self, memory: UUID | AgentMemory) -> AgentMemory:
        """实体直接返回；ID 经仓库解析，取不到就拒绝关联。"""

        if isinstance(memory, AgentMemory):
            return memory
        resolved = await self.repository.get(memory)
        if resolved is None:
            raise ValueError(f"memory {memory} does not exist")
        return resolved

    # ===================== 第2步：检索上下文扩展 =====================
    async def expand_context(
        self,
        memory: AgentMemory,
        *,
        depth: int = 1,
        limit: int | None = None,
    ) -> list[GraphNeighbour]:
        """取出一跳范围内的关联记忆，供检索命中时扩展上下文。

        - ``depth`` 硬上限 1：只取直接关联，不做多跳扩散。
        - ``limit`` 默认 ``memory_graph_max_links``（3 条），防止上下文爆炸。
        - 禁用、已软删除或已 superseded 的关联记忆直接跳过。
        - 保持 ``related_ids`` 的既有顺序（隐含用户/检索方的重要性排序），
          截断到 ``limit``。
        """
        bounded_depth = max(0, min(depth, self.settings.memory_graph_expand_depth))
        bounded_limit = limit or self.settings.memory_graph_max_links
        if bounded_depth == 0 or bounded_limit <= 0 or not memory.related_ids:
            return []

        relations = dict(memory.metadata.get("graph_relations") or {})
        seen: set[UUID] = {memory.id}
        neighbours: list[GraphNeighbour] = []
        for related_id in memory.related_ids:
            if related_id in seen:
                continue
            seen.add(related_id)
            related = await self.repository.get(related_id)
            if related is None:
                continue
            if related.deleted_at is not None or not related.enabled:
                continue
            # 已被冲突消解标记为 superseded 的记忆是过期事实，不再进入上下文。
            if related.status is MemoryStatus.superseded:
                continue
            if not related.is_retrievable():
                continue
            relation_raw = relations.get(str(related_id))
            relation: MemoryRelation | None = None
            if isinstance(relation_raw, str):
                try:
                    relation = MemoryRelation(relation_raw)
                except ValueError:
                    relation = None
            neighbours.append(GraphNeighbour(memory=related, relation=relation))

        # 保持 related_ids 既有顺序，截断到 limit。
        return neighbours[:bounded_limit]
