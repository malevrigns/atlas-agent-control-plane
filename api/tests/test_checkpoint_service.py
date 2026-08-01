import unittest

from app.application.checkpoint_service import CheckpointValidator, stable_state_hash


def snapshot() -> dict:
    return {
        "goal": "完成运行时改造",
        "acceptance_criteria": ["测试通过"],
        "requirements": [{"id": "REQ-1", "text": "保留兼容", "evidence": ["event:1"]}],
        "decisions": [{"id": "DEC-1", "text": "使用控制平面", "evidence": ["event:2"]}],
        "progress": {"done": [], "doing": [], "blocked": []},
        "known_failures": [],
        "open_questions": [],
        "next_actions": [{"text": "运行测试"}],
        "must_preserve": ["保留兼容"],
        "environment_ref": "env:1",
    }


class CheckpointValidatorTest(unittest.TestCase):
    def test_hash_is_stable(self) -> None:
        first = snapshot()
        second = dict(reversed(list(first.items())))
        self.assertEqual(stable_state_hash(first), stable_state_hash(second))

    def test_parent_constraint_cannot_disappear(self) -> None:
        child = snapshot()
        child["must_preserve"] = []
        result = CheckpointValidator().validate(
            child,
            covered_event_start=10,
            covered_event_end=20,
            parent_snapshot=snapshot(),
        )
        self.assertFalse(result.valid)
        self.assertIn("must_preserve", result.errors[0])


if __name__ == "__main__":
    unittest.main()
