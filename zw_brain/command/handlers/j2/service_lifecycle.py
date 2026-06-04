"""J2 service_lifecycle handlers — 1 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.brain import BrainServiceError, NotFoundError
from zw_brain.command.deps import HandlerDeps, SkillContext

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _publish_or_suspend_service(brain, deps, ctx, service_id: str, action: str, role: str, confirmed: bool) -> dict[str, Any]:
    # Action C — provider is read-then-mutated (service["status"] = ...,
    # provider["overview"][3]["value"] = ...); use brain_legacy escape hatch
    # to keep in-place semantics until Action D retires the snapshot dict.
    provider = deps.brain_legacy._snapshot["provider"]
    service = next((item for item in provider["services"] if item["id"] == service_id), None)
    if service is None:
        raise NotFoundError(service_id)
    if action not in {"publish", "suspend"}:
        raise BrainServiceError(f"unsupported service action: {action}")

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        if action == "publish":
            service["status"] = "在线"
            service["note"] = f"已由 {actor} 确认发布，保持对主旅程的稳定供给。"
            provider["aiGovernance"]["summary"] = "这项关键数据服务已上线，接下来可以继续完善填报模板、把目录挂到对应专区，方便办事人查到。"
            event_type = "service.publish"
            result = "published"
        else:
            service["status"] = "暂停"
            service["note"] = f"已由 {actor} 主动暂停，避免异常服务继续暴露到主旅程。"
            provider["aiGovernance"]["summary"] = "供给侧关键服务已暂停，需先完成核查后再重新发布。"
            event_type = "service.suspend"
            result = "suspended"
        provider["overview"][3]["value"] = str(sum(1 for item in provider["services"] if item["status"] != "在线"))
        deps.append_audit_feed(event_type, service_id, "ok", actor)
        return {"service_id": service_id, "status": service["status"], "result": result}

    return deps.write(ctx, {"service_id": service_id, "action": action}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_service_publish_or_suspend(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _publish_or_suspend_service(brain, deps, ctx, str(payload["service_id"]), str(payload["action"]), str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

