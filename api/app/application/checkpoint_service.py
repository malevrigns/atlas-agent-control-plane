import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.domain.control_plane.entities import CheckpointValidation


def stable_state_hash(snapshot: dict[str, Any]) -> str:
    """Return a deterministic hash for a materialized task snapshot."""

    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


class CheckpointValidator:
    """Validate that a checkpoint is evidence-bound and resume-safe."""

    REQUIRED_KEYS = {
        "goal",
        "acceptance_criteria",
        "requirements",
        "decisions",
        "progress",
        "known_failures",
        "open_questions",
        "next_actions",
        "must_preserve",
    }

    def validate(
        self,
        snapshot: dict[str, Any],
        *,
        covered_event_start: int,
        covered_event_end: int,
        parent_snapshot: dict[str, Any] | None = None,
    ) -> CheckpointValidation:
        errors: list[str] = []
        warnings: list[str] = []
        inherited: list[str] = []

        missing = sorted(self.REQUIRED_KEYS - snapshot.keys())
        if missing:
            errors.append(f"snapshot missing required fields: {', '.join(missing)}")
        if covered_event_start < 0 or covered_event_end < covered_event_start:
            errors.append("covered event range is invalid")

        for field_name in ("requirements", "decisions"):
            items = snapshot.get(field_name, [])
            if not isinstance(items, list):
                errors.append(f"{field_name} must be a list")
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{field_name}[{index}] must be an object")
                    continue
                evidence = item.get("evidence") or item.get("source_event_id")
                if not evidence:
                    errors.append(f"{field_name}[{index}] has no evidence")

        current_preserve = {
            str(value) for value in snapshot.get("must_preserve", []) if value
        }
        if parent_snapshot:
            previous_preserve = {
                str(value)
                for value in parent_snapshot.get("must_preserve", [])
                if value
            }
            inherited = sorted(previous_preserve & current_preserve)
            lost = sorted(previous_preserve - current_preserve)
            if lost:
                errors.append(
                    "must_preserve constraints were dropped: " + ", ".join(lost)
                )

        if not snapshot.get("next_actions") and snapshot.get("status") not in {
            "completed",
            "cancelled",
        }:
            warnings.append("active task has no next action")
        if snapshot.get("environment_ref") is None:
            warnings.append("checkpoint has no environment fingerprint reference")

        return CheckpointValidation(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            inherited_constraints=inherited,
        )


def checkpoint_report(validation: CheckpointValidation) -> dict[str, Any]:
    return {
        "valid": validation.valid,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "inherited_constraints": validation.inherited_constraints,
        "validated_at": datetime.now(UTC).isoformat(),
    }
