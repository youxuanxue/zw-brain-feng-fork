"""J2 `topic.package.create` handler — create_topic_package 从 BrainService 物理迁出（F1 turn 2）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    role = str(payload.get("role", brain._ui_state["role"]))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        record = brain._topic_package_repo().create_package(
            payload | {"actor_snapshot_json": {"actor": actor, "role": role}}
        )
        brain._append_audit_feed("topic.package.create", record.package_code, "ok", actor)
        return brain._topic_package_record_to_dict(record) | {"audit_id": audit_id}

    return brain._mutate("topic.package.create", role, confirmed, payload, mutation)
