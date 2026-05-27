"""J1 direct_access handlers — 2 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import get_runtime_tenant_id

_DEFAULT_TENANT_ID = get_runtime_tenant_id()


# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _query_direct_access_catalog(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """List active catalog_entry that flag direct-access eligibility."""
    from sqlalchemy import select  # noqa: PLC0415

    from zw_brain.domain.models import CatalogEntryRecord  # noqa: PLC0415
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        entries = session.execute(
            select(CatalogEntryRecord)
            .where(CatalogEntryRecord.tenant_id == tenant_id)
            .where(CatalogEntryRecord.lifecycle_status == "active")
            .limit(limit * 4)  # filter applied in python; cap pre-filter
        ).scalars().all()
    items = [
        {
            "catalog_code": e.catalog_code,
            "title": e.title,
            "owner_org_id": e.owner_org_id,
            "region_code": e.region_code,
            "direct_access_eligible": True,
        }
        for e in entries
        if isinstance(e.summary_json, dict) and e.summary_json.get("direct_access_eligible") is True
    ][:limit]
    return {"items": items, "total": len(items)}

def _list_direct_access_delivery(brain, deps, ctx, payload: dict[str, Any]) -> dict[str, Any]:
    """List delivery_task rows whose payload_json marks direct-access delivery."""
    from sqlalchemy import select  # noqa: PLC0415

    from zw_brain.domain.models import DeliveryTaskRecord  # noqa: PLC0415
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    limit = max(1, min(int(payload.get("limit") or 50), 200))
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        tasks = session.execute(
            select(DeliveryTaskRecord)
            .where(DeliveryTaskRecord.tenant_id == tenant_id)
            .limit(limit * 4)
        ).scalars().all()
    items = []
    for t in tasks:
        payload_json = t.payload_json if isinstance(t.payload_json, dict) else {}
        grant = payload_json.get("access_grant_snapshot") if isinstance(payload_json.get("access_grant_snapshot"), dict) else {}
        if grant.get("direct_access") is True or payload_json.get("direct_access") is True:
            items.append(
                {
                    "delivery_code": t.delivery_code,
                    "application_code": t.application_code,
                    "state": t.state,
                    "channel": t.channel,
                    "has_direct_access_flag": True,
                }
            )
        if len(items) >= limit:
            break
    return {"items": items, "total": len(items)}


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_direct_access_catalog_query(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _query_direct_access_catalog(brain, deps, ctx, payload)

def handler_direct_access_delivery_list(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _list_direct_access_delivery(brain, deps, ctx, payload)

