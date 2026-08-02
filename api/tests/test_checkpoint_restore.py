import unittest
from uuid import uuid4

from app.application.checkpoint_service import stable_state_hash
from app.application.control_plane_service import ControlPlaneService


class FakeControlPlaneRepository:
    def __init__(self, task: dict, checkpoint: dict) -> None:
        self.task = task
        self.checkpoint = checkpoint

    async def get_task(self, task_id):
        return dict(self.task) if self.task["id"] == task_id else None

    async def get_checkpoint(self, checkpoint_id):
        return dict(self.checkpoint) if self.checkpoint["id"] == checkpoint_id else None

    async def update_task(self, task_id, *, expected_version, payload):
        if expected_version != self.task["version"]:
            return {"version_conflict": True, "current_version": self.task["version"]}
        self.task.update(payload)
        self.task["version"] += 1
        return dict(self.task)


class FakeUnitOfWork:
    def __init__(self, repository) -> None:
        self.control_plane = repository
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class CheckpointRestoreTest(unittest.IsolatedAsyncioTestCase):
    def build_uow(self):
        task_id = uuid4()
        checkpoint_id = uuid4()
        snapshot = {
            "task_id": str(task_id),
            "goal": "restore me",
            "acceptance_criteria": ["tests pass"],
            "requirements": [],
            "decisions": [],
            "progress": {"done": [], "doing": [], "blocked": []},
            "known_failures": [],
            "open_questions": [],
            "next_actions": [{"text": "continue"}],
            "must_preserve": [],
            "environment_ref": None,
            "artifacts": ["artifact:1"],
            "status": "running",
            "event_seq": 12,
        }
        task = {
            "id": task_id,
            "version": 3,
            "title": "task",
            "goal": "newer state",
            "acceptance_criteria": [],
            "requirements": [],
            "decisions": [],
            "progress": {},
            "known_failures": [],
            "open_questions": [],
            "next_actions": [],
            "must_preserve": [],
            "environment_ref": None,
            "artifact_refs": [],
            "status": "running",
            "current_event_seq": 20,
        }
        checkpoint = {
            "id": checkpoint_id,
            "task_id": task_id,
            "snapshot": snapshot,
            "state_hash": stable_state_hash(snapshot),
            "validator_report": {"valid": True},
        }
        return task_id, checkpoint_id, checkpoint, FakeUnitOfWork(
            FakeControlPlaneRepository(task, checkpoint)
        )

    async def test_verified_checkpoint_restores_and_resumes_task(self) -> None:
        task_id, checkpoint_id, _, uow = self.build_uow()

        restored = await ControlPlaneService(uow).restore_checkpoint(
            task_id,
            checkpoint_id,
            expected_version=3,
            resume=True,
        )

        self.assertTrue(restored["resumed"])
        self.assertEqual(restored["task"]["goal"], "restore me")
        self.assertEqual(restored["task"]["status"], "running")
        self.assertEqual(restored["task"]["current_event_seq"], 12)
        self.assertEqual(restored["task"]["artifact_refs"], ["artifact:1"])
        self.assertEqual(uow.commits, 1)

    async def test_restore_without_resume_forces_paused_state(self) -> None:
        task_id, checkpoint_id, _, uow = self.build_uow()

        restored = await ControlPlaneService(uow).restore_checkpoint(
            task_id,
            checkpoint_id,
            expected_version=3,
            resume=False,
        )

        self.assertFalse(restored["resumed"])
        self.assertEqual(restored["task"]["status"], "paused")

    async def test_tampered_checkpoint_is_rejected(self) -> None:
        task_id, checkpoint_id, checkpoint, uow = self.build_uow()
        checkpoint["snapshot"]["goal"] = "tampered"

        with self.assertRaisesRegex(Exception, "integrity"):
            await ControlPlaneService(uow).restore_checkpoint(
                task_id,
                checkpoint_id,
                expected_version=3,
            )


if __name__ == "__main__":
    unittest.main()
