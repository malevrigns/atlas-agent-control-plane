"""工具结果缓存（Result Cache）。

对「低风险 + 幂等」的工具调用做内存级结果缓存：
- key = sha256(工具名 + 版本号 + 规范化参数)，参数按字典序序列化，
  因此 ``{"a": 1, "b": 2}`` 与 ``{"b": 2, "a": 1}`` 命中同一个 key。
- 容量上限采用 LRU 淘汰，条目超过 TTL 后按未命中处理（惰性清理）。
- 统计命中 / 未命中 / 淘汰次数，供审计与可观测性使用。

本模块是纯 domain 层实现：不依赖数据库、LLM 或网络，
由 ToolRuntime 在执行路径上接线（命中时结果带 cache_hit 标记）。
"""

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

# 时钟函数类型：注入后可在测试中模拟时间流逝。
Clock = Callable[[], float]


@dataclass(slots=True)
class ToolCacheEntry:
    """单条缓存条目：值 + 写入时间 + 有效期。"""

    value: Any
    stored_at: float
    ttl_seconds: float


class ToolResultCache:
    """内存 LRU + TTL 工具结果缓存。

    用法::

        cache = ToolResultCache(max_entries=256, default_ttl_seconds=300)
        key = ToolResultCache.build_key("search_web", {"query": "x"}, version="1.0.0")
        if cache.get(key) is None:
            value = await run_tool()
            cache.put(key, value)

    线程安全说明：本缓存面向单事件循环内的协程使用，
    get/put 之间没有 await 点，因此在 asyncio 场景下是安全的。
    """

    def __init__(
        self,
        *,
        max_entries: int = 256,
        default_ttl_seconds: float = 300.0,
        clock: Clock | None = None,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self._max_entries = max_entries
        self._default_ttl = float(default_ttl_seconds)
        self._clock: Clock = clock or monotonic
        self._entries: OrderedDict[str, ToolCacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    # ===================== key 生成 =====================
    @staticmethod
    def build_key(
        tool_name: str,
        arguments: dict[str, Any],
        *,
        version: str = "1.0.0",
    ) -> str:
        """生成缓存 key：工具名 + 版本 + 规范化参数（键排序）的 sha256。"""

        body = json.dumps(
            {"tool": tool_name, "version": version, "arguments": arguments},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"toolcache:{hashlib.sha256(body).hexdigest()}"

    # ===================== 读写 =====================
    def get(self, key: str) -> Any | None:
        """读取缓存；未命中或已过期返回 None，并更新命中统计。"""

        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        if self._clock() - entry.stored_at > entry.ttl_seconds:
            # 惰性清理过期条目
            del self._entries[key]
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return entry.value

    def put(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        """写入缓存；超出容量时 LRU 淘汰最旧条目。"""

        ttl = float(ttl_seconds) if ttl_seconds is not None else self._default_ttl
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        if key in self._entries:
            self._entries.move_to_end(key)
        elif len(self._entries) >= self._max_entries:
            self._entries.popitem(last=False)
            self._evictions += 1
        self._entries[key] = ToolCacheEntry(value=value, stored_at=self._clock(), ttl_seconds=ttl)

    # ===================== 统计与运维 =====================
    def stats(self) -> dict[str, int]:
        """返回 hits / misses / evictions / size 统计，供审计输出。"""

        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "size": len(self._entries),
        }

    def clear(self) -> None:
        """清空所有条目（统计计数保留）。"""

        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
