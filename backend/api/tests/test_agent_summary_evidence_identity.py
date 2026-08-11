import unittest

from app.application.agent_summary_service import AgentSummaryService
from app.core.exceptions import AppException
from app.domain.sessions.entities import SessionEvent
from tests.test_final_answer_builder import (
    FakeModel,
    FakeUow,
    build_reflection_event,
    build_tool_event,
)


class AgentSummaryEvidenceIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_retry_and_replan_outputs_are_excluded(self) -> None:
        service = AgentSummaryService(FakeUow(), FakeModel())
        plan = {
            "id": "plan-1",
            "goal": "produce accepted evidence",
            "steps": [{"id": "step", "title": "collect evidence"}],
        }
        cases = (
            ("retry", 1, 0, 2, 0),
            ("replan", 1, 0, 1, 1),
        )
        for action, old_attempt, old_revision, new_attempt, new_revision in cases:
            with self.subTest(action=action):
                rejected = build_tool_event(
                    "step",
                    "safe_echo",
                    "REJECTED_OUTPUT",
                    attempt=old_attempt,
                    plan_revision=old_revision,
                )
                accepted = build_tool_event(
                    "step",
                    "safe_echo",
                    "ACCEPTED_OUTPUT",
                    attempt=new_attempt,
                    plan_revision=new_revision,
                )
                events = [
                    rejected,
                    build_reflection_event(
                        "step",
                        old_attempt,
                        action,
                        plan_revision=old_revision,
                    ),
                    accepted,
                    build_reflection_event(
                        "step",
                        new_attempt,
                        plan_revision=new_revision,
                    ),
                ]

                evidence = service.build_evidence(plan, events)

                self.assertNotIn("REJECTED_OUTPUT", evidence)
                self.assertIn("ACCEPTED_OUTPUT", evidence)

    async def test_evidence_does_not_cross_run_boundaries(self) -> None:
        service = AgentSummaryService(FakeUow(), FakeModel())
        rejected = build_tool_event(
            "step",
            "safe_echo",
            "OLD_RUN_OUTPUT",
            attempt=1,
            run_id="run-old",
        )
        accepted = build_tool_event(
            "step",
            "safe_echo",
            "NEW_RUN_OUTPUT",
            attempt=1,
            run_id="run-new",
        )
        events = [
            rejected,
            build_reflection_event("step", 1, "retry", run_id="run-old"),
            accepted,
            build_reflection_event("step", 1, run_id="run-new"),
        ]

        evidence = service.build_evidence({"id": "plan-1", "steps": []}, events)

        self.assertNotIn("OLD_RUN_OUTPUT", evidence)
        self.assertIn("NEW_RUN_OUTPUT", evidence)

    async def test_malformed_evidence_identity_is_explicit(self) -> None:
        service = AgentSummaryService(FakeUow(), FakeModel())
        event = build_tool_event("step", "safe_echo", "output")
        malformed_payload = dict(event.payload)
        malformed_payload.pop("run_id")
        malformed = SessionEvent(
            id=event.id,
            session_id=event.session_id,
            type=event.type,
            payload=malformed_payload,
            created_at=event.created_at,
        )
        reflection = build_reflection_event("step", 2)

        with self.assertRaisesRegex(AppException, "run_id"):
            service.build_evidence({}, [malformed, reflection])


if __name__ == "__main__":
    unittest.main()
