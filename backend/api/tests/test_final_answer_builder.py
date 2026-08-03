import json
import unittest
from datetime import UTC, datetime
from uuid import uuid4

from app.application.react_agent_service import ReActAgentService
from app.domain.sessions.entities import SessionEvent, SessionEventType


def build_tool_event(step_id: str, tool_name: str, output: str, arguments: dict | None = None) -> SessionEvent:
    return SessionEvent(
        id=uuid4(),
        session_id=uuid4(),
        type=SessionEventType.tool_called,
        payload={
            "plan_id": "plan-1",
            "step_id": step_id,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "output": output,
        },
        created_at=datetime.now(UTC),
    )


class FinalAnswerBuilderTest(unittest.TestCase):
    # ===================== 第1步：最终回答应从工具输出中整理证据 =====================
    def test_rule_based_final_answer_contains_sources_files_and_artifacts(self) -> None:
        service = ReActAgentService.__new__(ReActAgentService)
        plan = {
            "goal": "整理 AI 新闻并生成报告",
            "steps": [
                {"id": "search", "title": "搜索新闻资料"},
                {"id": "file", "title": "读取上传文件"},
                {"id": "shell", "title": "生成报告文件"},
            ],
        }
        search_output = json.dumps(
            {
                "kind": "search_results",
                "query": "AI news",
                "items": [
                    {
                        "title": "OpenAI releases agent update",
                        "url": "https://example.com/openai",
                        "snippet": "Agent update details.",
                    },
                    {
                        "title": "Microsoft announces AI tools",
                        "url": "https://example.com/microsoft",
                        "snippet": "AI tools details.",
                    },
                ],
            },
            ensure_ascii=False,
        )
        events = [
            build_tool_event("search", "search_web", search_output, {"query": "AI news"}),
            build_tool_event(
                "file",
                "file_read",
                "文件：requirements.md\n第 3 行：需要输出引用来源和最终建议。",
            ),
            build_tool_event(
                "shell",
                "shell_exec",
                "命令：python build_report.py\n退出码：0\n输出文件：/workspace/report.md",
            ),
        ]

        answer = service._build_rule_based_final_answer(plan, events)

        self.assertIn("## 总结", answer)
        self.assertIn("## 证据与引用", answer)
        self.assertIn("OpenAI releases agent update", answer)
        self.assertIn("https://example.com/openai", answer)
        self.assertIn("requirements.md", answer)
        self.assertIn("## 产物", answer)
        self.assertIn("/workspace/report.md", answer)
        self.assertIn("## 下一步建议", answer)


if __name__ == "__main__":
    unittest.main()
