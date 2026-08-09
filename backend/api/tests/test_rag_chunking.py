import unittest

from app.domain.rag.chunking import split_text


class ChunkingTests(unittest.TestCase):
    """切分器是 RAG 质量的第一道闸门，行为必须完全可预测。"""

    def test_empty_text_returns_no_chunks(self) -> None:
        self.assertEqual(split_text("   \n\n  "), [])

    def test_short_text_returns_single_chunk(self) -> None:
        spans = split_text("AtlasAgent 是一个可审计的 Agent 控制平面。")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].char_start, 0)

    def test_paragraphs_are_packed_to_chunk_size(self) -> None:
        text = "\n\n".join(f"第 {index} 段。" + "内容" * 30 for index in range(10))
        spans = split_text(text, chunk_size=200, chunk_overlap=0)
        self.assertGreater(len(spans), 1)
        for span in spans:
            self.assertLessEqual(len(span.content), 200)

    def test_overlap_repeats_previous_tail(self) -> None:
        text = "\n\n".join("段落" * 60 for _ in range(4))
        spans = split_text(text, chunk_size=150, chunk_overlap=30)
        for previous, current in zip(spans, spans[1:], strict=False):
            # 当前 chunk 的开头必须覆盖上一个 chunk 的结尾。
            self.assertLess(current.char_start, previous.char_end)

    def test_oversized_sentence_is_hard_split(self) -> None:
        text = "x" * 2000
        spans = split_text(text, chunk_size=500, chunk_overlap=0)
        self.assertGreaterEqual(len(spans), 4)
        for span in spans:
            self.assertLessEqual(len(span.content), 500)

    def test_char_ranges_point_back_to_source(self) -> None:
        text = "第一段内容。\n\n第二段内容，比第一段稍微长一点。"
        for span in split_text(text, chunk_size=12, chunk_overlap=0):
            self.assertEqual(text[span.char_start : span.char_end], span.content)

    def test_invalid_config_raises(self) -> None:
        with self.assertRaises(ValueError):
            split_text("内容", chunk_size=0)
        with self.assertRaises(ValueError):
            split_text("内容", chunk_size=100, chunk_overlap=100)


if __name__ == "__main__":
    unittest.main()
