import unittest
from uuid import uuid4

from app.application.memory_write_gate import MemoryWriteGate
from app.domain.memories.entities import (
    MemoryAuthority,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemorySensitivity,
    MemoryStatus,
)


class MemoryWriteGateTest(unittest.TestCase):
    def test_inferred_memory_cannot_be_verified(self) -> None:
        candidate = MemoryCandidate(
            kind=MemoryKind.project_fact,
            content="项目使用 PostgreSQL",
            importance=3,
            reason="inferred",
            scope=MemoryScope.project,
            project_id="atlas",
            provenance=["event:1"],
            authority=MemoryAuthority.agent_inferred,
        )
        decision = MemoryWriteGate().evaluate(
            candidate,
            requested_status=MemoryStatus.verified,
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.target_status, MemoryStatus.candidate)

    def test_verified_bug_lesson_requires_test_evidence(self) -> None:
        candidate = MemoryCandidate(
            kind=MemoryKind.bug_lesson,
            content="连接池过小导致请求排队",
            importance=5,
            reason="test",
            scope=MemoryScope.task,
            task_id=uuid4(),
            provenance=["event:1"],
            authority=MemoryAuthority.test_verified,
            verification={"evidence": ["artifact:repro"], "tests": ["artifact:test"]},
        )
        decision = MemoryWriteGate().evaluate(candidate, requested_status=MemoryStatus.verified)
        self.assertEqual(decision.target_status, MemoryStatus.verified)

    def test_secrets_are_not_persisted(self) -> None:
        candidate = MemoryCandidate(
            kind=MemoryKind.project_fact,
            content="token=abc123",
            importance=3,
            reason="secret",
            scope=MemoryScope.project,
            project_id="atlas",
            sensitivity=MemorySensitivity.secret,
        )
        decision = MemoryWriteGate().evaluate(candidate)
        self.assertFalse(decision.accepted)


if __name__ == "__main__":
    unittest.main()
