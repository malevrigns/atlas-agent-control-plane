"""查询改写与多查询扩展（query_processing）的单元测试。

覆盖四个能力单元：
- tokenize_mixed_text：中英文混合分词口径；
- rule_expand：无 LLM 时的确定性规则改写（停用词/同义词/中英扩展）；
- expand_query：LLM 多查询优先、失败静默降级规则改写；
- reciprocal_rank_fuse：RRF 多列表融合（k=60）。
"""

import asyncio
import json
import unittest

from app.domain.llm.entities import LLMChatResult
from app.domain.rag.query_processing import (
    expand_query,
    reciprocal_rank_fuse,
    rule_expand,
    tokenize_mixed_text,
)


class FakeLLM:
    """返回固定内容的最小 LLM 桩，同时记录收到的 prompt。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.prompts: list[str] = []

    async def chat(self, messages, *args, **kwargs) -> LLMChatResult:
        self.prompts.append(messages[-1].content if messages else "")
        return LLMChatResult(provider="fake", model="fake", content=self.content)


class TokenizeMixedTextTests(unittest.TestCase):
    """中英文混合分词：与词法信号、重排共用同一口径。"""

    def test_english_words_are_lowercased(self) -> None:
        terms = tokenize_mixed_text("Hello Docker WORLD")
        self.assertIn("hello", terms)
        self.assertIn("docker", terms)
        self.assertIn("world", terms)

    def test_chinese_ngrams(self) -> None:
        terms = tokenize_mixed_text("数据库迁移")
        for expected in ("数据", "据库", "数据库", "据库迁", "数据库迁", "库迁移"):
            self.assertIn(expected, terms)

    def test_mixed_text_keeps_both_sides(self) -> None:
        terms = tokenize_mixed_text("使用 Alembic 进行数据库迁移")
        self.assertIn("alembic", terms)
        self.assertIn("数据库", terms)
        self.assertIn("迁移", terms)

    def test_empty_text_returns_empty_set(self) -> None:
        self.assertEqual(tokenize_mixed_text(""), set())
        self.assertEqual(tokenize_mixed_text("   "), set())


class RuleExpandTests(unittest.TestCase):
    """规则改写：确定性、无副作用、与原始查询去重。"""

    def test_synonym_replacement_variant(self) -> None:
        variants = rule_expand("数据库迁移怎么回滚")
        self.assertTrue(any("回退" in variant for variant in variants))

    def test_bilingual_expansion_appends_english_terms(self) -> None:
        variants = rule_expand("数据库超时")
        joined = " ".join(variants)
        self.assertIn("database", joined)
        self.assertIn("timeout", joined)

    def test_stopword_stripping_variant(self) -> None:
        variants = rule_expand("什么是配置")
        self.assertIn("配置", variants)

    def test_no_variants_when_nothing_to_change(self) -> None:
        self.assertEqual(rule_expand("zzz"), [])

    def test_max_variants_capped(self) -> None:
        variants = rule_expand("数据库迁移日志超时", max_variants=2)
        self.assertLessEqual(len(variants), 2)

    def test_variants_never_equal_original(self) -> None:
        original = "数据库迁移怎么回滚"
        for variant in rule_expand(original):
            self.assertNotEqual(variant.lower(), original.lower())

    def test_empty_query_returns_no_variants(self) -> None:
        self.assertEqual(rule_expand("   "), [])


class ExpandQueryTests(unittest.TestCase):
    """expand_query：LLM 优先、任何失败都降级规则改写。"""

    def test_llm_path_parses_json_array(self) -> None:
        llm = FakeLLM('["数据库故障排查", "数据库异常处理"]')
        result = asyncio.run(expand_query("数据库报错", llm, max_variants=3))
        self.assertEqual(result.method, "llm")
        self.assertEqual(result.variants, ["数据库故障排查", "数据库异常处理"])
        self.assertEqual(result.all_queries[0], "数据库报错")
        self.assertEqual(len(result.all_queries), 3)

    def test_llm_output_tolerates_fences_and_extras(self) -> None:
        llm = FakeLLM('好的，以下是改写结果：\n```json\n["数据库故障", "DB 异常"]\n```\n')
        result = asyncio.run(expand_query("数据库报错", llm))
        self.assertEqual(result.method, "llm")
        self.assertEqual(result.variants, ["数据库故障", "DB 异常"])

    def test_llm_output_filtering_original_and_dups(self) -> None:
        llm = FakeLLM(json.dumps(["数据库报错", "数据库故障", "数据库故障"]))
        result = asyncio.run(expand_query("数据库报错", llm))
        self.assertEqual(result.variants, ["数据库故障"])

    def test_llm_exception_falls_back_to_rule(self) -> None:
        class BrokenLLM:
            async def chat(self, *args, **kwargs):
                raise RuntimeError("llm down")

        result = asyncio.run(expand_query("数据库迁移回滚", BrokenLLM()))
        self.assertEqual(result.method, "rule")
        self.assertTrue(result.variants)

    def test_llm_garbage_output_falls_back_to_rule(self) -> None:
        llm = FakeLLM("这不是 JSON 数组")
        result = asyncio.run(expand_query("数据库迁移回滚", llm))
        self.assertEqual(result.method, "rule")
        self.assertTrue(result.variants)

    def test_no_llm_uses_rule_path(self) -> None:
        result = asyncio.run(expand_query("数据库迁移怎么回滚", None))
        self.assertEqual(result.method, "rule")
        self.assertGreaterEqual(len(result.all_queries), 2)

    def test_blank_query_yields_empty_expansion(self) -> None:
        result = asyncio.run(expand_query("   ", None))
        self.assertEqual(result.original, "")
        self.assertEqual(result.variants, [])
        self.assertEqual(result.all_queries, [""])


class ReciprocalRankFusionTests(unittest.TestCase):
    """RRF 融合：多列表投票、k 平滑、确定性排序。"""

    def test_chunk_in_both_lists_ranks_first(self) -> None:
        fused = reciprocal_rank_fuse([["a", "b"], ["a", "c"]], k=60)
        self.assertEqual(fused[0][0], "a")
        scores = dict(fused)
        self.assertGreater(scores["a"], scores["b"])
        self.assertGreater(scores["a"], scores["c"])

    def test_single_list_preserves_order(self) -> None:
        fused = reciprocal_rank_fuse([["x", "y", "z"]], k=60)
        self.assertEqual([item[0] for item in fused], ["x", "y", "z"])

    def test_larger_k_smooths_rank_differences(self) -> None:
        small = dict(reciprocal_rank_fuse([["a", "b", "c"]], k=10))
        large = dict(reciprocal_rank_fuse([["a", "b", "c"]], k=1000))
        self.assertGreater(small["a"] - small["c"], large["a"] - large["c"])

    def test_known_score_value(self) -> None:
        # 1/(60+1) + 1/(60+1) = 2/61
        fused = reciprocal_rank_fuse([["a"], ["a"]], k=60)
        self.assertAlmostEqual(fused[0][1], round(2.0 / 61.0, 6), places=6)

    def test_tie_keeps_first_seen_order(self) -> None:
        # b 与 c 各只在一个列表出现且名次相同 → 按先出现顺序
        fused = reciprocal_rank_fuse([["a", "b"], ["a", "c"]], k=60)
        self.assertEqual([item[0] for item in fused], ["a", "b", "c"])

    def test_empty_input(self) -> None:
        self.assertEqual(reciprocal_rank_fuse([], k=60), [])


if __name__ == "__main__":
    unittest.main()
