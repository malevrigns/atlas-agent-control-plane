import unittest
from unittest.mock import patch

from app.presentation.http.routes.sessions import build_agent_runner_service


class SessionRunnerCompositionTest(unittest.TestCase):
    def test_route_delegates_default_composition_to_runner(self) -> None:
        db_session = object()
        runner = object()

        with patch(
            "app.presentation.http.routes.sessions.AgentRunnerService.from_uow",
            return_value=runner,
        ) as from_uow:
            result = build_agent_runner_service(db_session)

        self.assertIs(result, runner)
        args, kwargs = from_uow.call_args
        self.assertEqual(kwargs, {})
        self.assertIs(args[0].db_session, db_session)


if __name__ == "__main__":
    unittest.main()
