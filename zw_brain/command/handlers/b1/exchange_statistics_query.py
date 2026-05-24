"""B1 `ops.exchange.statistics.query` handler — query_exchange_statistics 物理迁出（F1 turn 2）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    filters: dict[str, Any] = {}
    if payload.get("metric_scope") is not None:
        filters["metric_scope"] = payload.get("metric_scope")
    if payload.get("resource_code") is not None:
        filters["resource_code"] = payload.get("resource_code")
    if payload.get("delivery_code") is not None:
        filters["delivery_code"] = payload.get("delivery_code")
    metrics = [
        brain._exchange_metric_record_to_dict(item)
        for item in brain._delivery_repo().list_exchange_metrics(**filters, tenant_id=_DEFAULT_TENANT_ID)
    ]
    return {"items": metrics, "summary": brain._exchange_metric_summary(metrics)}
