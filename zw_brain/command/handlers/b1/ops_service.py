"""B1 ops_service handlers — 2 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

import copy

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import ops_metrics as ops_metrics_ser

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _query_service_invocations(
    brain,
    *,
    resource_code: Any = None,
    capability_id: Any = None,
    metric_scope: Any = None,
) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        metrics = copy.deepcopy(brain._snapshot.get("service_invocation_metrics", []))
        if resource_code:
            metrics = [item for item in metrics if item.get("resource_code") == resource_code]
        if capability_id:
            metrics = [item for item in metrics if item.get("capability_id") == capability_id]
        if metric_scope:
            metrics = [item for item in metrics if item.get("metric_scope") == metric_scope]
    else:
        metrics = [
            ops_metrics_ser.metric_to_dict(item)
            for item in store.service_invocation_repo.list_metrics(
                resource_code=str(resource_code) if resource_code else None,
                capability_id=str(capability_id) if capability_id else None,
                metric_scope=str(metric_scope) if metric_scope else None,
            )
        ]
    return {"items": metrics, "summary": brain._metric_summary(metrics)}

def _query_service_report(brain) -> dict[str, Any]:
    store = brain._state_store.database_store
    if store is None:
        gateways = copy.deepcopy(brain._snapshot.get("gateway_runtime_statuses", []))
        metrics = copy.deepcopy(brain._snapshot.get("service_invocation_metrics", []))
    else:
        gateways = [ops_metrics_ser.gateway_to_dict(item) for item in store.gateway_runtime_repo.list_statuses()]
        metrics = [ops_metrics_ser.metric_to_dict(item) for item in store.service_invocation_repo.list_metrics()]
    offline = sum(1 for item in gateways if item.get("status") != "online")
    metric_summary = brain._metric_summary(metrics)
    return {
        "gateways": gateways,
        "metrics": metrics,
        "summary": {
            "gatewayCount": len(gateways),
            "gatewayWarnings": offline,
            "invokeCount": metric_summary["invokeCount"],
            "failedCount": metric_summary["failedCount"],
            "errorCount": metric_summary["errorCount"],
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_ops_service_invocation_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_service_invocations(brain, resource_code=payload.get("resource_code"), capability_id=payload.get("capability_id"), metric_scope=payload.get("metric_scope"))

def handler_ops_service_report_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_service_report(brain)

