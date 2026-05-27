"""J2 `topic.package.create` handler — create_topic_package 从 BrainService 物理迁出（F1 turn 2）。"""

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
        record = deps.repos.topic_package.create_package(
            payload | {"actor_snapshot_json": {"actor": actor, "role": role}}
        )
        deps.append_audit_feed("topic.package.create", record.package_code, "ok", actor)
        return topic_package_ser.topic_package_to_dict(record) | {"audit_id": audit_id}

    return deps.write(ctx, payload, mutation)
