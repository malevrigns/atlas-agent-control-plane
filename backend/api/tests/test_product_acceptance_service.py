import unittest

from app.application.product_acceptance_service import ProductAcceptanceService


class ProductAcceptanceServiceTest(unittest.TestCase):
    # ===================== 第1步：最终验收清单必须覆盖成熟 Agent 产品核心体验 =====================
    def test_acceptance_items_cover_mature_agent_experience(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()
        item_ids = {item.key for item in checklist.items}

        self.assertIn("natural_conversation", item_ids)
        self.assertIn("agent_plan_execution", item_ids)
        self.assertIn("streaming_timeline", item_ids)
        self.assertIn("tool_preview_surface", item_ids)
        self.assertIn("context_and_memory", item_ids)
        self.assertIn("multi_agent_collaboration", item_ids)
        self.assertIn("harness_regression", item_ids)
        self.assertIn("browser_vnc_observation", item_ids)
        self.assertIn("failure_recovery", item_ids)
        self.assertIn("structured_error_experience", item_ids)
        self.assertIn("file_parsing_references", item_ids)
        self.assertIn("final_answer_citations", item_ids)
        self.assertIn("compose_startup", item_ids)

    # ===================== 第2步：每个验收项都要给出证据、验证步骤和相关接口 =====================
    def test_every_acceptance_item_has_evidence_steps_and_routes(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()

        for item in checklist.items:
            self.assertTrue(item.evidence)
            self.assertTrue(item.verify_steps)
            self.assertTrue(item.related_routes)
            self.assertIn(item.status, {"ready", "needs_manual_check"})

    # ===================== 第3步：汇总信息应能告诉前端有多少项已经具备自动验收证据 =====================
    def test_summary_counts_ready_and_manual_items(self) -> None:
        service = ProductAcceptanceService()

        checklist = service.get_checklist()

        self.assertEqual(checklist.summary.total, len(checklist.items))
        self.assertEqual(
            checklist.summary.ready + checklist.summary.needs_manual_check,
            checklist.summary.total,
        )
        self.assertGreater(checklist.summary.ready, 0)


if __name__ == "__main__":
    unittest.main()
