"""B1 system_ops handlers — 3 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.domain.dispute_snapshot_projection import enrich_disputes_snapshot
from zw_brain.domain.provider_snapshot_projection import enrich_provider_snapshot, enrich_zones_snapshot
from zw_brain.domain.schemas import describe_schemas
from zw_brain.domain.web_snapshot_redaction import redact_webui_snapshot
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _toggle_outage(brain, role: str, confirmed: bool) -> dict[str, Any]:
    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        brain._ui_state["brainOutage"] = not brain._ui_state["brainOutage"]
        brain._append_audit_feed(
            "dashboard.snapshot-toggle",
            "brain",
            "warning" if brain._ui_state["brainOutage"] else "ok",
            actor,
        )
        return {"brainOutage": brain._ui_state["brainOutage"]}

    return brain._mutate("system.toggle_outage", role, confirmed, {}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_system_toggle_outage(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _toggle_outage(brain, str(payload.get("role", ctx.role)), bool(payload.get("confirmed")))

def handler_system_snapshot(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    role = str(payload.get("role", ctx.role))
    tenant_id = str(payload.get("tenant_id") or get_runtime_tenant_id())
    enriched = enrich_provider_snapshot(brain.snapshot(), tenant_id=tenant_id)
    enriched = enrich_zones_snapshot(enriched, tenant_id=tenant_id)
    enriched = enrich_disputes_snapshot(enriched, tenant_id=tenant_id)
    if role in {"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"}:
        enriched["delivery_tasks"] = brain.list_delivery_tasks()
    return redact_webui_snapshot(enriched, role)

def handler_system_schema_info(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return {"schemas": describe_schemas()}

