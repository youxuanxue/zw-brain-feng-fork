"""Live disputes projection for WebUI snapshot — merge DB objection cases."""

from __future__ import annotations

import copy
from typing import Any

from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id


def _case_to_dispute_item(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "topic": record.title,
        "type": record.objection_kind,
        "status": record.status,
        "targetType": record.target_type,
        "targetId": record.target_id,
        "owner": record.provider_org_id or record.complainant_org_id,
        "createdAt": record.created_at.isoformat() if getattr(record, "created_at", None) else "",
        "repository": {
            "objectionKind": record.objection_kind,
            "targetType": record.target_type,
            "status": record.status,
        },
    }


def enrich_disputes_snapshot(snapshot: dict[str, Any], *, tenant_id: str | None = None) -> dict[str, Any]:
    """Merge live objection cases into snapshot disputes (deep copy)."""
    out = copy.deepcopy(snapshot)
    items: list[dict[str, Any]] = copy.deepcopy(out.get("disputes") or [])
    by_id = {str(item.get("id")): item for item in items if item.get("id")}

    repo = ObjectionRepository()
    for record in repo.list_cases(tenant_id=tenant_id or get_runtime_tenant_id()):
        live = _case_to_dispute_item(record)
        existing = by_id.get(record.id)
        if existing is None:
            items.append(live)
            by_id[record.id] = live
            continue
        existing["status"] = live["status"]
        existing["title"] = live["title"]
        existing["topic"] = live["topic"]
        existing["type"] = live["type"]
        existing["targetType"] = live["targetType"]
        existing["targetId"] = live["targetId"]
        existing["owner"] = live["owner"]
        existing["repository"] = live["repository"]

    out["disputes"] = items
    return out
