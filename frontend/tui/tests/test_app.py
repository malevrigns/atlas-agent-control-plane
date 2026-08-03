import unittest

from atlas_agent_tui.app import AtlasTui


class AtlasTuiSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_app_mounts_in_offline_mode(self) -> None:
        app = AtlasTui()
        app.api.base_url = "http://127.0.0.1:1"
        app.api.timeout = 0.2
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            self.assertIsNotNone(app.query_one("#task-list"))
            self.assertIsNotNone(app.query_one("#audit-log"))


if __name__ == "__main__":
    unittest.main()
