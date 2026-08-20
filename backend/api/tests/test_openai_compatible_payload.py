import unittest

from app.core.exceptions import AppException
from app.domain.llm.entities import LLMMessage
from app.infrastructure.llm.openai_compatible import OpenAICompatibleClient


class OpenAICompatibleMessagePayloadTest(unittest.TestCase):
    """Ensure every outgoing chat message carries the `name` field.

    Some OpenAI-compatible gateways require `name` on every message even
    though the OpenAI spec marks it optional. Multi-turn conversations fail
    on the first assistant history message without this field.
    """

    @staticmethod
    def _client() -> OpenAICompatibleClient:
        return OpenAICompatibleClient(
            api_key="test-key",
            base_url="http://provider.invalid",
            provider="test",
            timeout_seconds=1,
        )

    def test_system_user_assistant_messages_get_role_derived_name(self) -> None:
        client = self._client()
        for role in ("system", "user", "assistant"):
            with self.subTest(role=role):
                payload = client._build_message_payload(
                    LLMMessage(role=role, content="hi")
                )
                self.assertEqual(payload["name"], role)

    def test_tool_message_keeps_explicit_name_and_tool_call_id(self) -> None:
        client = self._client()
        payload = client._build_message_payload(
            LLMMessage(role="tool", content="ok", name="bash", tool_call_id="call-1")
        )
        self.assertEqual(payload["name"], "bash")
        self.assertEqual(payload["tool_call_id"], "call-1")

    def test_tool_message_without_name_is_rejected(self) -> None:
        client = self._client()
        with self.assertRaises(AppException):
            client._build_message_payload(LLMMessage(role="tool", content="ok"))


if __name__ == "__main__":
    unittest.main()
