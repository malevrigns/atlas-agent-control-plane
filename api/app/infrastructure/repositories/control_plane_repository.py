from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.control_plane import (
    AgentTaskModel,
    ArtifactModel,
    CheckpointModel,
    EnvironmentSnapshotModel,
    RetrievalTraceModel,
    TaskDecisionModel,
    TaskRequirementModel,
    ToolInvocationModel,
)


class SqlAlchemyControlPlaneRepository:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        requirements = list(payload.pop("requirements", []))
        decisions = list(payload.pop("decisions", []))
        model = AgentTaskModel(**payload)
        self.db_session.add(model)
        await self.db_session.flush()
        await self._replace_task_facts(model.id, requirements, decisions)
        await self.db_session.refresh(model)
        return await self._task_payload(model)

    async def get_task(self, task_id: UUID) -> dict[str, Any] | None:
        model = await self.db_session.get(AgentTaskModel, task_id)
        return await self._task_payload(model) if model else None

    async def list_tasks(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.db_session.execute(
            select(AgentTaskModel)
            .where(AgentTaskModel.project_id == project_id)
            .order_by(AgentTaskModel.updated_at.desc())
            .limit(limit)
        )
        return [await self._task_payload(model) for model in result.scalars()]

    async def update_task(
        self,
        task_id: UUID,
        *,
        expected_version: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        model = await self.db_session.get(AgentTaskModel, task_id)
        if model is None:
            return None
        if model.version != expected_version:
            return {"version_conflict": True, "current_version": model.version}
        requirements = payload.pop("requirements", None)
        decisions = payload.pop("decisions", None)
        for key, value in payload.items():
            setattr(model, key, value)
        model.version += 1
        model.updated_at = datetime.now(UTC)
        if requirements is not None or decisions is not None:
            current = await self._task_payload(model)
            await self._replace_task_facts(
                task_id,
                list(requirements if requirements is not None else current["requirements"]),
                list(decisions if decisions is not None else current["decisions"]),
            )
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return await self._task_payload(model)

    async def create_checkpoint(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = CheckpointModel(**payload)
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return self._checkpoint_payload(model)

    async def get_checkpoint(self, checkpoint_id: UUID) -> dict[str, Any] | None:
        model = await self.db_session.get(CheckpointModel, checkpoint_id)
        return self._checkpoint_payload(model) if model else None

    async def list_checkpoints(self, task_id: UUID, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.db_session.execute(
            select(CheckpointModel)
            .where(CheckpointModel.task_id == task_id)
            .order_by(CheckpointModel.created_at.desc())
            .limit(limit)
        )
        return [self._checkpoint_payload(model) for model in result.scalars()]

    async def get_artifact_by_hash(self, sha256: str) -> dict[str, Any] | None:
        result = await self.db_session.execute(
            select(ArtifactModel).where(ArtifactModel.sha256 == sha256)
        )
        model = result.scalar_one_or_none()
        return self._artifact_payload(model) if model else None

    async def create_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = ArtifactModel(**payload)
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return self._artifact_payload(model)

    async def get_artifact(self, artifact_id: UUID) -> dict[str, Any] | None:
        model = await self.db_session.get(ArtifactModel, artifact_id)
        return self._artifact_payload(model) if model else None

    async def create_environment_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.db_session.execute(
            select(EnvironmentSnapshotModel).where(
                EnvironmentSnapshotModel.project_id == payload["project_id"],
                EnvironmentSnapshotModel.fingerprint == payload["fingerprint"],
            )
        )
        existing = result.scalar_one_or_none()
        model = existing or EnvironmentSnapshotModel(**payload)
        if existing is None:
            self.db_session.add(model)
            await self.db_session.flush()
            await self.db_session.refresh(model)
        return {
            "id": model.id,
            "task_id": model.task_id,
            "project_id": model.project_id,
            "fingerprint": model.fingerprint,
            "snapshot": dict(model.snapshot),
            "sensitivity": model.sensitivity,
            "created_at": model.created_at,
        }

    async def record_retrieval_trace(self, payload: dict[str, Any]) -> UUID:
        model = RetrievalTraceModel(**payload)
        self.db_session.add(model)
        await self.db_session.flush()
        return model.id

    async def get_tool_invocation_by_idempotency(
        self,
        tool_name: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        result = await self.db_session.execute(
            select(ToolInvocationModel).where(
                ToolInvocationModel.tool_name == tool_name,
                ToolInvocationModel.idempotency_key == idempotency_key,
            )
        )
        model = result.scalar_one_or_none()
        return self._tool_invocation_payload(model) if model else None

    async def create_tool_invocation(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = ToolInvocationModel(**payload)
        self.db_session.add(model)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return self._tool_invocation_payload(model)

    async def finish_tool_invocation(
        self,
        invocation_id: UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        model = await self.db_session.get(ToolInvocationModel, invocation_id)
        if model is None:
            return None
        for key, value in payload.items():
            setattr(model, key, value)
        await self.db_session.flush()
        await self.db_session.refresh(model)
        return self._tool_invocation_payload(model)

    async def list_tool_invocations(
        self,
        *,
        project_id: str,
        task_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(ToolInvocationModel).where(ToolInvocationModel.project_id == project_id)
        if task_id:
            stmt = stmt.where(ToolInvocationModel.task_id == task_id)
        result = await self.db_session.execute(
            stmt.order_by(ToolInvocationModel.started_at.desc()).limit(limit)
        )
        return [self._tool_invocation_payload(model) for model in result.scalars()]

    async def _replace_task_facts(
        self,
        task_id: UUID,
        requirements: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> None:
        await self.db_session.execute(delete(TaskRequirementModel).where(TaskRequirementModel.task_id == task_id))
        await self.db_session.execute(delete(TaskDecisionModel).where(TaskDecisionModel.task_id == task_id))
        for index, item in enumerate(requirements, start=1):
            self.db_session.add(TaskRequirementModel(
                task_id=task_id,
                requirement_key=str(item.get("id") or f"REQ-{index:03d}"),
                text_value=str(item.get("text") or ""),
                status=str(item.get("status") or "active"),
                source_event_id=item.get("source_event_id"),
                evidence=list(item.get("evidence") or ([f"event:{item['source_event_id']}"] if item.get("source_event_id") else [])),
            ))
        for index, item in enumerate(decisions, start=1):
            self.db_session.add(TaskDecisionModel(
                task_id=task_id,
                decision_key=str(item.get("id") or f"DEC-{index:03d}"),
                text_value=str(item.get("text") or ""),
                status=str(item.get("status") or "active"),
                evidence=list(item.get("evidence") or []),
            ))
        await self.db_session.flush()

    async def _task_payload(self, model: AgentTaskModel) -> dict[str, Any]:
        requirement_result = await self.db_session.execute(
            select(TaskRequirementModel)
            .where(TaskRequirementModel.task_id == model.id)
            .order_by(TaskRequirementModel.created_at)
        )
        decision_result = await self.db_session.execute(
            select(TaskDecisionModel)
            .where(TaskDecisionModel.task_id == model.id)
            .order_by(TaskDecisionModel.created_at)
        )
        return {
            "id": model.id,
            "session_id": model.session_id,
            "project_id": model.project_id,
            "title": model.title,
            "goal": model.goal,
            "acceptance_criteria": list(model.acceptance_criteria or []),
            "status": model.status,
            "requirements": [
                {"id": item.requirement_key, "text": item.text_value, "status": item.status, "source_event_id": item.source_event_id, "evidence": list(item.evidence or [])}
                for item in requirement_result.scalars()
            ],
            "decisions": [
                {"id": item.decision_key, "text": item.text_value, "status": item.status, "evidence": list(item.evidence or [])}
                for item in decision_result.scalars()
            ],
            "progress": dict(model.progress or {}),
            "known_failures": list(model.known_failures or []),
            "open_questions": list(model.open_questions or []),
            "next_actions": list(model.next_actions or []),
            "must_preserve": list(model.must_preserve or []),
            "environment_ref": model.environment_ref,
            "artifact_refs": list(model.artifact_refs or []),
            "current_event_seq": model.current_event_seq,
            "version": model.version,
            "state_hash": model.state_hash,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }

    @staticmethod
    def _checkpoint_payload(model: CheckpointModel) -> dict[str, Any]:
        return {column: getattr(model, column) for column in [
            "id", "task_id", "parent_checkpoint_id", "kind", "covered_event_start",
            "covered_event_end", "snapshot", "state_hash", "validator_report", "created_at",
        ]}

    @staticmethod
    def _artifact_payload(model: ArtifactModel) -> dict[str, Any]:
        return {
            "id": model.id, "sha256": model.sha256, "kind": model.kind,
            "media_type": model.media_type, "size_bytes": model.size_bytes,
            "storage_path": model.storage_path, "project_id": model.project_id,
            "task_id": model.task_id, "source_event_id": model.source_event_id,
            "metadata": dict(model.metadata_json or {}), "sensitivity": model.sensitivity,
            "created_at": model.created_at,
        }

    @staticmethod
    def _tool_invocation_payload(model: ToolInvocationModel) -> dict[str, Any]:
        return {column: getattr(model, column) for column in [
            "id", "tool_name", "tool_version", "task_id", "session_id", "project_id",
            "idempotency_key", "request_hash", "risk_level", "permissions", "decision",
            "decision_reason", "status", "arguments", "output_preview", "artifact_id",
            "error", "duration_ms", "started_at", "finished_at",
        ]}
