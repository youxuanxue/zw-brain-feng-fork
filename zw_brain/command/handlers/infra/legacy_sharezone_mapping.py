"""infra `legacy.sharezone.mapping.import` handler — import_legacy_sharezone_mapping 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass



from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import topic_package as topic_package_ser


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    confirmed = bool(payload.get("confirmed"))

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        record = deps.repos.topic_package.import_legacy_sharezone(
            payload | {"actor_snapshot_json": {"actor": actor, "role": role}}
        )
        deps.append_audit_feed("legacy.sharezone.mapping.import", record.package_code, "ok", actor)
        return topic_package_ser.topic_package_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)
