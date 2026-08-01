import unittest

from atlas_agent_tui.api import AtlasApiError, unwrap


class ApiPayloadTest(unittest.TestCase):
    def test_unwraps_api_data(self) -> None:
        self.assertEqual(unwrap({"data": {"items": [1]}}), {"items": [1]})

    def test_raises_api_error(self) -> None:
        with self.assertRaises(AtlasApiError):
            unwrap({"error": {"message": "denied"}})


if __name__ == "__main__":
    unittest.main()
