import unittest

from app.application.agent_harness_service import AgentHarnessService
from app.domain.harness.entities import HarnessCase, HarnessExpectation


def build_case() -> HarnessCase:
    return HarnessCase(
        id="browser_observation",
        title="浏览器观察任务",
        task="请访问 https://example.com 并截图观察页面",
        description="验证浏览器工具链路。",
        tags=["browser"],
        expectation=HarnessExpectation(
            required_events=["message_created", "plan_created", "task_done"],
            required_tools=["browser_open", "browser_screenshot"],
            required_files=[],
            forbidden_events=["task_error"],
        ),
    )


class AgentHarnessServiceTest(unittest.TestCase):
    # ===================== 第1步：模拟运行应生成可通过断言的事件流 =====================
    def test_simulated_run_passes_required_assertions(self) -> None:
        service = AgentHarnessService()

        run = service.run_case("browser_observation")

        self.assertEqual(run.status, "passed")
        self.assertEqual(run.mode, "simulate")
        self.assertTrue(run.events)
        self.assertTrue(all(assertion.passed for assertion in run.assertions))

    # ===================== 第2步：缺少关键工具调用时断言应失败 =====================
    def test_evaluate_events_reports_missing_required_tool(self) -> None:
        service = AgentHarnessService()
        case = build_case()
        events = [
            {"type": "message_created", "payload": {}},
            {"type": "plan_created", "payload": {}},
            {"type": "task_done", "payload": {}},
        ]

        assertions = service.evaluate_events(case, events)
        failed = [assertion for assertion in assertions if not assertion.passed]

        self.assertEqual(
            [assertion.name for assertion in failed],
            [
                "required_tool:browser_open",
                "required_tool:browser_screenshot",
            ],
        )

    # ===================== 第3步：运行结果应支持按 run_id 回放 =====================
    def test_replay_returns_saved_run_events(self) -> None:
        service = AgentHarnessService()
        run = service.run_case("browser_observation")

        replayed = service.replay_run(run.id)

        self.assertEqual(replayed.id, run.id)
        self.assertEqual(replayed.events, run.events)


if __name__ == "__main__":
    unittest.main()
