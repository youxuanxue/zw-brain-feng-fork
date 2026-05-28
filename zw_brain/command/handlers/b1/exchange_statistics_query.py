"""B1 `ops.exchange.statistics.query` handler — query_exchange_statistics 物理迁出（F1 turn 2）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.command.serializers import delivery as delivery_ser
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    filters: dict[str, Any] = {}
    if payload.get("metric_scope") is not None:
        filters["metric_scope"] = payload.get("metric_scope")
    if payload.get("resource_code") is not None:
        filters["resource_code"] = payload.get("resource_code")
    if payload.get("delivery_code") is not None:
        filters["delivery_code"] = payload.get("delivery_code")
    metrics = [
        delivery_ser.exchange_metric_to_dict(item)
        for item in deps.repos.delivery.list_exchange_metrics(**filters, tenant_id=_DEFAULT_TENANT_ID)
    ]
    return {"items": metrics, "summary": brain._exchange_metric_summary(metrics)}
