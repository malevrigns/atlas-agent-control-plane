import unittest

from app.application.attachment_excerpt import (
    build_attachment_excerpt,
    is_pdf_attachment,
    is_text_attachment,
)


class AttachmentExcerptTest(unittest.TestCase):
    def test_text_file_is_decoded(self) -> None:
        excerpt = build_attachment_excerpt(
            filename="notes.md",
            content_type="text/markdown",
            data="# 标题\n正文内容".encode("utf-8"),
            char_budget=1000,
        )
        self.assertEqual(excerpt, "# 标题\n正文内容")

    def test_text_file_is_truncated_with_marker(self) -> None:
        excerpt = build_attachment_excerpt(
            filename="log.txt",
            content_type="text/plain",
            data=("x" * 500).encode("utf-8"),
            char_budget=100,
        )
        assert excerpt is not None
        self.assertTrue(excerpt.startswith("x" * 100))
        self.assertIn("已截断", excerpt)

    def test_unknown_binary_returns_none(self) -> None:
        excerpt = build_attachment_excerpt(
            filename="photo.png",
            content_type="image/png",
            data=b"\x89PNG\r\n",
            char_budget=1000,
        )
        self.assertIsNone(excerpt)

    def test_broken_pdf_returns_deterministic_note(self) -> None:
        excerpt = build_attachment_excerpt(
            filename="paper.pdf",
            content_type="application/pdf",
            data=b"not a real pdf",
            char_budget=1000,
        )
        assert excerpt is not None
        self.assertIn("PDF", excerpt)

    def test_type_detection(self) -> None:
        self.assertTrue(is_pdf_attachment("application/pdf", "a.bin"))
        self.assertTrue(is_pdf_attachment("application/octet-stream", "a.pdf"))
        self.assertFalse(is_pdf_attachment("text/plain", "a.txt"))
        self.assertTrue(is_text_attachment("text/plain; charset=utf-8", "a"))
        self.assertTrue(is_text_attachment("application/octet-stream", "a.py"))
        self.assertFalse(is_text_attachment("application/zip", "a.zip"))


if __name__ == "__main__":
    unittest.main()
