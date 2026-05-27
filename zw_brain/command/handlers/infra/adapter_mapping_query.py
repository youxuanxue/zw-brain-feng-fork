"""infra `adapter.external.mapping.query` handler — query_external_mappings 物理迁出（F1 turn 3）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.serializers import adapter as adapter_ser
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


def handler(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    mappings = [
        adapter_ser.external_mapping_to_dict(item)
        for item in brain._external_adapter_repo().list_mappings(
            external_system=str(payload["external_system"]) if payload.get("external_system") else None,
            local_aggregate_type=str(payload["local_aggregate_type"]) if payload.get("local_aggregate_type") else None,
            local_aggregate_id=str(payload["local_aggregate_id"]) if payload.get("local_aggregate_id") else None,
            status=str(payload["status"]) if payload.get("status") else None,
            tenant_id=_DEFAULT_TENANT_ID,
        )
    ]
    return {"items": mappings, "total": len(mappings)}
