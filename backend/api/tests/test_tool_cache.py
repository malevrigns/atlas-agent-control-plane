"""工具结果缓存（LRU + TTL）单元测试。

覆盖：命中/未命中、LRU 淘汰顺序、TTL 过期（假时钟）、缓存键包含版本、
自定义 TTL、stats 统计、clear，以及 ToolRuntime 集成：
cacheable 工具第二次相同调用命中缓存，底层函数只执行一次。
"""

import unittest

from app.application.tool_runtime import ToolExecutionContext, ToolRuntime
from app.domain.agent_core.tool_cache import ToolResultCache
from app.domain.agent_core.tools import (
    ToolCallResult,
    ToolRegistry,
    agent_tool,
)

# 可缓存工具：调用次数可观测，用于验证缓存命中后不再执行底层函数。
CALL_COUNTS: dict[str, int] = {}


def _result(output: str = "ok") -> ToolCallResult:
    """构造一个成功的工具结果，供缓存测试复用。"""
    return ToolCallResult(
        tool_name="search",
        arguments={"q": "x"},
        output=output,
    )


@agent_tool(
    name="cached_search",
    description="可缓存的搜索工具",
    parameter_descriptions={"q": "搜索词"},
    required_permissions=("search:query",),
    idempotent=True,
    cacheable=True,
    cache_ttl_seconds=120,
)
def cached_search(q: str) -> str:
    """记录调用次数并返回查询词。"""
    CALL_COUNTS["cached_search"] = CALL_COUNTS.get("cached_search", 0) + 1
    return q


@agent_tool(
    name="plain_echo",
    description="不可缓存的回显工具",
    parameter_descriptions={"text": "文本"},
    required_permissions=("text:read",),
    idempotent=True,
)
def plain_echo(text: str) -> str:
    """普通回显，未声明 cacheable。"""
    return text


class ToolResultCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1000.0
        self.cache = ToolResultCache(
            max_entries=2,
            default_ttl_seconds=60.0,
            clock=lambda: self.now,
        )

    def test_hit_returns_stored_result(self) -> None:
        """相同键命中时返回原结果对象。"""
        stored = _result("first")
        key = ToolResultCache.build_key("search", {"q": "x"})
        self.assertIsNone(self.cache.get(key))
        self.cache.put(key, stored)
        self.assertIs(stored, self.cache.get(key))

    def test_different_arguments_or_version_miss(self) -> None:
        """参数或版本不同则未命中。"""
        self.cache.put(ToolResultCache.build_key("search", {"q": "x"}), _result())
        self.assertIsNone(self.cache.get(ToolResultCache.build_key("search", {"q": "y"})))
        self.assertIsNone(
            self.cache.get(ToolResultCache.build_key("search", {"q": "x"}, version="2.0.0"))
        )

    def test_lru_evicts_least_recently_used(self) -> None:
        """容量满时淘汰最久未使用的条目。"""
        k1 = ToolResultCache.build_key("a", {"i": 1})
        k2 = ToolResultCache.build_key("b", {"i": 2})
        k3 = ToolResultCache.build_key("c", {"i": 3})
        self.cache.put(k1, _result("1"))
        self.cache.put(k2, _result("2"))
        # 访问 k1 使其变为最近使用，再插入 k3 应淘汰 k2。
        self.cache.get(k1)
        self.cache.put(k3, _result("3"))
        self.assertIsNotNone(self.cache.get(k1))
        self.assertIsNone(self.cache.get(k2))
        self.assertIsNotNone(self.cache.get(k3))

    def test_ttl_expires_with_clock(self) -> None:
        """超过 TTL 的条目视为未命中并被清除。"""
        key = ToolResultCache.build_key("search", {"q": "x"})
        self.cache.put(key, _result())
        self.now = 1000.0 + 59.0
        self.assertIsNotNone(self.cache.get(key))
        self.now = 1000.0 + 61.0
        self.assertIsNone(self.cache.get(key))

    def test_custom_ttl_overrides_default(self) -> None:
        """put 时传入的 TTL 覆盖默认值。"""
        key = ToolResultCache.build_key("search", {"q": "x"})
        self.cache.put(key, _result(), ttl_seconds=10.0)
        self.now = 1000.0 + 9.0
        self.assertIsNotNone(self.cache.get(key))
        self.now = 1000.0 + 11.0
        self.assertIsNone(self.cache.get(key))

    def test_stats_and_clear(self) -> None:
        """stats 记录命中/未命中/淘汰次数；clear 清空全部。"""
        key = ToolResultCache.build_key("search", {"q": "x"})
        self.cache.get(key)  # 未命中
        self.cache.put(key, _result())
        self.cache.get(key)  # 命中
        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["size"], 1)
        self.cache.clear()
        self.assertEqual(self.cache.stats()["size"], 0)


class ToolRuntimeResultCacheIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        CALL_COUNTS.clear()
        registry = ToolRegistry()
        registry.register(cached_search)
        registry.register(plain_echo)
        self.runtime = ToolRuntime(
            registry,
            result_cache=ToolResultCache(max_entries=16, default_ttl_seconds=60.0),
        )
        self.context = ToolExecutionContext(allowed_permissions={"search:query", "text:read"})

    def test_cacheable_tool_second_call_hits_cache(self) -> None:
        """cacheable 工具相同参数第二次调用命中缓存，底层只执行一次。"""
        first = self._run("cached_search", {"q": "atlas"})
        self.assertTrue(first.cache_hit is False)
        second = self._run("cached_search", {"q": "atlas"})
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.output, first.output)
        self.assertEqual(CALL_COUNTS["cached_search"], 1)
        self.assertEqual((second.audit or {}).get("cache_hit"), True)

    def test_non_cacheable_tool_never_hits(self) -> None:
        """未声明 cacheable 的工具每次都会真实执行。"""
        self._run("plain_echo", {"text": "a"})
        second = self._run("plain_echo", {"text": "a"})
        self.assertFalse(second.cache_hit)

    def test_runtime_without_cache_still_works(self) -> None:
        """显式禁用缓存时行为与旧版一致（每次执行）。"""
        runtime = ToolRuntime(
            _registry([cached_search]),
            result_cache=None,
        )
        context = ToolExecutionContext(allowed_permissions={"search:query"})
        self._run_via(runtime, context, "cached_search", {"q": "x"})
        self._run_via(runtime, context, "cached_search", {"q": "x"})
        self.assertEqual(CALL_COUNTS["cached_search"], 2)

    def _run(self, name: str, args: dict) -> ToolCallResult:
        import asyncio

        return asyncio.run(self.runtime.execute(name, args, self.context))

    def _run_via(
        self, runtime: ToolRuntime, context: ToolExecutionContext, name: str, args: dict
    ) -> ToolCallResult:
        import asyncio

        return asyncio.run(runtime.execute(name, args, context))


def _registry(tools: list) -> ToolRegistry:
    """按列表注册工具，返回新注册表。"""
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


if __name__ == "__main__":
    unittest.main()
