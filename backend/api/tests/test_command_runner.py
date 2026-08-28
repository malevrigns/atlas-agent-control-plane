"""SubprocessCommandRunner 的生产实现测试。

真实子进程极简用例（echo/exit/timeout），保证 exit code 语义与
domain 层 AcceptanceGate 的约定一致。
"""

import sys
import unittest

from app.infrastructure.acceptance.command_runner import SubprocessCommandRunner


@unittest.skipIf(sys.platform != "win32", "命令形态按 Windows shell 书写")
class SubprocessCommandRunnerWindowsTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_command_returns_zero_and_output(self) -> None:
        outcome = await SubprocessCommandRunner().run("echo hello", 10, "")
        self.assertEqual(outcome.exit_code, 0)
        self.assertIn("hello", outcome.output)
        self.assertIsNone(outcome.error)

    async def test_failing_command_returns_nonzero_exit(self) -> None:
        outcome = await SubprocessCommandRunner().run("exit 3", 10, "")
        self.assertEqual(outcome.exit_code, 3)

    async def test_timeout_returns_none_exit_code_with_reason(self) -> None:
        outcome = await SubprocessCommandRunner().run("ping -n 30 127.0.0.1", 1, "")
        self.assertIsNone(outcome.exit_code)
        self.assertIn("timed out", outcome.error or "")

    async def test_output_truncated_to_limit(self) -> None:
        outcome = await SubprocessCommandRunner().run(
            "python -c \"print('x' * 20000)\"", 15, ""
        )
        self.assertLessEqual(len(outcome.output), 8000)


if __name__ == "__main__":
    unittest.main()
