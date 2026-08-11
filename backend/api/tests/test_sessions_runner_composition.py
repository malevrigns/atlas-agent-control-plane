import unittest
from pathlib import Path
from unittest.mock import patch

from app.presentation.http.routes.sessions import build_agent_runner_service, router


EXPECTED_ROUTES = [
    ("POST", "/sessions", "create_session", ["build_session_service"]),
    ("GET", "/sessions", "list_sessions", ["build_session_service"]),
    ("GET", "/sessions/{session_id}", "get_session", ["build_session_service"]),
    ("GET", "/sessions/{session_id}/context", "get_session_context", ["build_context_engineering_service"]),
    ("GET", "/sessions/{session_id}/messages", "list_messages", ["build_session_service"]),
    ("POST", "/sessions/{session_id}/messages", "create_message", ["build_session_service"]),
    ("POST", "/sessions/{session_id}/messages/stream", "stream_message", ["build_agent_runner_service"]),
    ("POST", "/sessions/{session_id}/stop", "stop_session", ["build_session_service"]),
    ("POST", "/sessions/{session_id}/read", "clear_unread", ["build_session_service"]),
    ("GET", "/sessions/{session_id}/events", "list_events", ["build_session_service"]),
    ("POST", "/sessions/{session_id}/plan", "create_plan", ["build_planner_service"]),
    ("POST", "/sessions/{session_id}/plan/execute", "execute_plan", ["build_agent_runner_service"]),
    ("POST", "/sessions/{session_id}/plan/tasks", "start_plan_task", ["build_session_service", "get_task_queue"]),
    ("GET", "/sessions/tasks/{task_id}", "get_agent_task", ["get_task_queue"]),
    ("POST", "/sessions/tasks/{task_id}/cancel", "cancel_agent_task", ["get_task_queue"]),
    ("POST", "/sessions/tasks/{task_id}/retry", "retry_agent_task", ["get_task_queue"]),
    ("GET", "/sessions/{session_id}/tasks/latest", "recover_latest_session_task", ["get_task_queue"]),
    ("POST", "/sessions/{session_id}/files", "upload_session_file", ["build_file_service"]),
    ("GET", "/sessions/{session_id}/files", "list_session_files", ["build_file_service"]),
    ("DELETE", "/sessions/{session_id}", "delete_session", ["build_session_service"]),
]


class SessionRunnerCompositionTest(unittest.TestCase):
    def test_session_route_modules_stay_within_file_limit(self) -> None:
        routes = Path(__file__).parents[1] / "app/presentation/http/routes"
        oversized = {
            path.name: len(path.read_text(encoding="utf-8").splitlines())
            for path in routes.glob("session*.py")
            if len(path.read_text(encoding="utf-8").splitlines()) > 300
        }

        self.assertEqual(oversized, {})

    def test_session_route_contract_stays_stable(self) -> None:
        actual = []
        for route in router.routes:
            methods = sorted(route.methods or [])
            dependencies = [
                dependency.call.__name__
                for dependency in route.dependant.dependencies
            ]
            actual.append((methods[0], route.path, route.name, dependencies))

        self.assertEqual(actual, EXPECTED_ROUTES)

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
