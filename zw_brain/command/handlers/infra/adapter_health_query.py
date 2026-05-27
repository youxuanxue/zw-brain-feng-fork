"""infra `adapter.cascade.health.query` handler — query_adapter_health 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import adapter as adapter_ser
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    adapter_slug = payload.get("adapter_slug")
    runs = [
        adapter_ser.adapter_run_to_dict(item)
        for item in deps.repos.external_adapter.list_run_records(
            tenant_id=_DEFAULT_TENANT_ID,
            adapter_slug=str(adapter_slug) if adapter_slug else None,
        )
    ]
    failures = [item for item in runs if item["status"] in {"failed", "partial"}]
    return {
        "items": runs,
        "summary": {
            "run_count": len(runs),
            "failure_count": len(failures),
            "last_status": runs[-1]["status"] if runs else "unknown",
        },
    }
