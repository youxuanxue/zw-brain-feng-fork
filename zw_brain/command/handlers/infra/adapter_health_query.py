"""infra `adapter.cascade.health.query` handler — query_adapter_health 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    adapter_slug = payload.get("adapter_slug")
    runs = [
        brain._adapter_run_record_to_dict(item)
        for item in brain._external_adapter_repo().list_run_records(
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
