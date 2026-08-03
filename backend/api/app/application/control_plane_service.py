import hashlib
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from app.application.checkpoint_service import CheckpointValidator, checkpoint_report, stable_state_hash
from app.application.unit_of_work import UnitOfWork
from app.core.config import settings
from app.core.exceptions import AppException


class ContentAddressedArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.artifact_dir).resolve()

    def persist(self, content: bytes) -> tuple[str, str]:
        sha256 = hashlib.sha256(content).hexdigest()
        path = self.root / sha256[:2] / sha256[2:4] / sha256
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
        return sha256, str(path)


class ControlPlaneService:
    _SENSITIVE_KEY = re.compile(r"(?i)(token|secret|password|api.?key|cookie|private.?key)")

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self.validator = CheckpointValidator()
        self.artifact_store = ContentAddressedArtifactStore()

    async def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = self._task_snapshot(payload)
        payload = dict(payload)
        payload["state_hash"] = stable_state_hash(snapshot)
        task = await self.uow.control_plane.create_task(payload)
        await self.uow.commit()
        return task

    async def list_tasks(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self.uow.control_plane.list_tasks(project_id, limit)

    async def get_task(self, task_id: UUID) -> dict[str, Any]:
        task = await self.uow.control_plane.get_task(task_id)
        if task is None:
            raise AppException(message="task state not found", code=404, status_code=404)
        return task

    async def update_task(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        current = await self.get_task(task_id)
        merged = {**current, **{key: value for key, value in patch.items() if value is not None}}
        patch = {key: value for key, value in patch.items() if value is not None}
        patch["state_hash"] = stable_state_hash(self._task_snapshot(merged))
        updated = await self.uow.control_plane.update_task(
            task_id,
            expected_version=expected_version,
            payload=patch,
        )
        if updated is None:
            raise AppException(message="task state not found", code=404, status_code=404)
        if updated.get("version_conflict"):
            raise AppException(
                message=f"task version conflict; current version is {updated['current_version']}",
                code=409,
                status_code=409,
            )
        await self.uow.commit()
        return updated

    async def create_checkpoint(
        self,
        task_id: UUID,
        *,
        kind: str,
        parent_checkpoint_id: UUID | None,
        covered_event_start: int,
        covered_event_end: int,
    ) -> dict[str, Any]:
        task = await self.get_task(task_id)
        snapshot = self._task_snapshot(task)
        parent_snapshot = None
        if parent_checkpoint_id:
            parent = await self.uow.control_plane.get_checkpoint(parent_checkpoint_id)
            if parent is None or parent["task_id"] != task_id:
                raise AppException(message="parent checkpoint not found", code=404, status_code=404)
            parent_snapshot = dict(parent["snapshot"])
        validation = self.validator.validate(
            snapshot,
            covered_event_start=covered_event_start,
            covered_event_end=covered_event_end,
            parent_snapshot=parent_snapshot,
        )
        if not validation.valid:
            raise AppException(
                message="checkpoint validation failed: " + "; ".join(validation.errors),
                code=422,
                status_code=422,
            )
        checkpoint = await self.uow.control_plane.create_checkpoint({
            "task_id": task_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "kind": kind,
            "covered_event_start": covered_event_start,
            "covered_event_end": covered_event_end,
            "snapshot": snapshot,
            "state_hash": stable_state_hash(snapshot),
            "validator_report": checkpoint_report(validation),
        })
        await self.uow.commit()
        return checkpoint

    async def list_checkpoints(self, task_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
        await self.get_task(task_id)
        return await self.uow.control_plane.list_checkpoints(task_id, limit)

    async def restore_checkpoint(
        self,
        task_id: UUID,
        checkpoint_id: UUID,
        *,
        expected_version: int,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Restore a validated snapshot with optimistic concurrency control."""

        checkpoint = await self.uow.control_plane.get_checkpoint(checkpoint_id)
        if checkpoint is None or checkpoint["task_id"] != task_id:
            raise AppException(message="checkpoint not found", code=404, status_code=404)
        snapshot = dict(checkpoint["snapshot"])
        if stable_state_hash(snapshot) != checkpoint["state_hash"]:
            raise AppException(
                message="checkpoint integrity verification failed",
                code=409,
                status_code=409,
            )
        if not bool((checkpoint.get("validator_report") or {}).get("valid")):
            raise AppException(
                message="checkpoint is not marked as restorable",
                code=422,
                status_code=422,
            )

        restorable_fields = {
            "goal",
            "acceptance_criteria",
            "requirements",
            "decisions",
            "progress",
            "known_failures",
            "open_questions",
            "next_actions",
            "must_preserve",
            "environment_ref",
            "status",
        }
        patch = {key: snapshot[key] for key in restorable_fields if key in snapshot}
        if patch.get("environment_ref"):
            patch["environment_ref"] = UUID(str(patch["environment_ref"]))
        patch["artifact_refs"] = list(snapshot.get("artifacts") or [])
        patch["current_event_seq"] = int(snapshot.get("event_seq") or 0)
        patch["status"] = "running" if resume else "paused"
        task = await self.update_task(
            task_id,
            expected_version=expected_version,
            patch=patch,
        )
        return {
            "checkpoint_id": checkpoint_id,
            "resumed": resume,
            "task": task,
        }

    async def persist_artifact(
        self,
        content: bytes,
        *,
        kind: str,
        media_type: str,
        project_id: str,
        task_id: UUID | None = None,
        source_event_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        sensitivity: str = "internal",
    ) -> dict[str, Any]:
        sha256, storage_path = self.artifact_store.persist(content)
        existing = await self.uow.control_plane.get_artifact_by_hash(sha256)
        if existing:
            return existing
        artifact = await self.uow.control_plane.create_artifact({
            "sha256": sha256,
            "kind": kind,
            "media_type": media_type,
            "size_bytes": len(content),
            "storage_path": storage_path,
            "project_id": project_id,
            "task_id": task_id,
            "source_event_id": source_event_id,
            "metadata_json": metadata or {},
            "sensitivity": sensitivity,
        })
        await self.uow.commit()
        return artifact

    async def capture_environment(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        task_id: UUID | None = None,
    ) -> dict[str, Any]:
        redacted = self._redact_mapping(snapshot)
        fingerprint = stable_state_hash(redacted)
        result = await self.uow.control_plane.create_environment_snapshot({
            "task_id": task_id,
            "project_id": project_id,
            "fingerprint": fingerprint,
            "snapshot": redacted,
            "sensitivity": "confidential",
        })
        await self.uow.commit()
        return result

    @staticmethod
    def _task_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": str(payload.get("id")) if payload.get("id") else None,
            "goal": payload.get("goal", ""),
            "acceptance_criteria": payload.get("acceptance_criteria", []),
            "requirements": payload.get("requirements", []),
            "decisions": payload.get("decisions", []),
            "progress": payload.get("progress", {"done": [], "doing": [], "blocked": []}),
            "known_failures": payload.get("known_failures", []),
            "open_questions": payload.get("open_questions", []),
            "next_actions": payload.get("next_actions", []),
            "must_preserve": payload.get("must_preserve", []),
            "environment_ref": str(payload.get("environment_ref")) if payload.get("environment_ref") else None,
            "artifacts": payload.get("artifact_refs", []),
            "status": payload.get("status", "pending"),
            "event_seq": payload.get("current_event_seq", 0),
        }

    @classmethod
    def _redact_mapping(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "[REDACTED]" if cls._SENSITIVE_KEY.search(str(key)) else cls._redact_mapping(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._redact_mapping(item) for item in value]
        return value
