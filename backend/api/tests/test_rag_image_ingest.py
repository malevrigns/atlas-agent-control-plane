import unittest

from app.core.exceptions import AppException
from app.domain.rag.entities import KnowledgeDocumentStatus, KnowledgeSourceType
from tests.test_rag_service import build_service


class FakeVisionLLMService:
    """视觉模型替身：记录调用并返回固定解析文本。"""

    def __init__(self, *, enabled: bool = True, text: str = "") -> None:
        self.enabled = enabled
        self.text = text or "## 部署流程图\n1. 停止服务\n2. 备份数据\n3. 重启并验证"
        self.calls: list[dict] = []

        class _Defaults:
            vision_model = "fake-vl" if enabled else ""

        class _Config:
            llm = _Defaults()

        self.config = _Config()

    def vision_enabled(self) -> bool:
        return self.enabled

    async def vision_extract(self, *, image_bytes: bytes, content_type: str, **kwargs) -> str:
        if not self.enabled:
            raise AppException(message="vision model is not configured", code=503, status_code=503)
        self.calls.append({"bytes": len(image_bytes), "content_type": content_type})
        return self.text


class RagImageIngestTest(unittest.IsolatedAsyncioTestCase):
    async def test_image_is_extracted_and_ingested(self) -> None:
        service, _uow, store = build_service()
        vision = FakeVisionLLMService()
        service._llm_service = vision  # noqa: SLF001 - 测试注入替身
        knowledge_base = await service.create_knowledge_base(name="多模态库")

        document = await service.ingest_image_document(
            knowledge_base.id,
            filename="deploy-flow.png",
            content_type="image/png",
            data=b"\x89PNG fake bytes",
        )

        # 视觉模型被调用，解析文本走标准摄取管线并 ready。
        self.assertEqual(len(vision.calls), 1)
        self.assertIs(document.status, KnowledgeDocumentStatus.ready)
        self.assertIs(document.source_type, KnowledgeSourceType.image)
        self.assertEqual(document.source_ref, "deploy-flow.png")
        self.assertEqual(document.title, "deploy-flow")
        self.assertIn("部署流程图", document.content)
        self.assertGreater(document.chunk_count, 0)
        self.assertGreater(len(store.records), 0)
        self.assertEqual(document.metadata.get("vision_model"), "fake-vl")

    async def test_non_image_content_type_is_rejected(self) -> None:
        service, _uow, _store = build_service()
        service._llm_service = FakeVisionLLMService()
        knowledge_base = await service.create_knowledge_base(name="多模态库")

        with self.assertRaises(AppException) as context:
            await service.ingest_image_document(
                knowledge_base.id,
                filename="doc.pdf",
                content_type="application/pdf",
                data=b"%PDF",
            )
        self.assertEqual(context.exception.status_code, 400)

    async def test_missing_vision_model_gives_clear_error(self) -> None:
        service, _uow, _store = build_service()
        service._llm_service = FakeVisionLLMService(enabled=False)
        knowledge_base = await service.create_knowledge_base(name="多模态库")

        with self.assertRaises(AppException) as context:
            await service.ingest_image_document(
                knowledge_base.id,
                filename="a.png",
                content_type="image/png",
                data=b"png",
            )
        self.assertEqual(context.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
