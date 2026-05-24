"""infra `legacy.sharezone.mapping.import` handler — import_legacy_sharezone_mapping 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        record = brain._topic_package_repo().import_legacy_sharezone(
            payload | {"actor_snapshot_json": {"actor": actor, "role": role}}
        )
        brain._append_audit_feed("legacy.sharezone.mapping.import", record.package_code, "ok", actor)
        return brain._topic_package_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("legacy.sharezone.mapping.import", role, confirmed, payload, mutation)
