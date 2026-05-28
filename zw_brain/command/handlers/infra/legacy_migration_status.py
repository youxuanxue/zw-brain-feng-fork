"""infra `legacy.migration.status.query` handler — get_legacy_migration_status 物理迁出（F1 turn 3）。

Aggregate M0 acceptance state for the P0 WebUI page (业务运营员 / 安全审计员).
Reads `legacy_object_mapping`, `adapter_run_record`, and recent
`audit_event(kind='migration.*')` rows in one shot. Returns counts by
canonical_type and legacy_system, the latest 20 adapter runs, the
latest 5 rollback events, and a fixed 11-card work-queue status
derived from the same data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from zw_brain.command.deps import HandlerDeps, SkillContext
from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID


def handler(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    from sqlalchemy import desc, func, select  # noqa: PLC0415 — keep import-cost local

    from zw_brain.domain.models import (  # noqa: PLC0415
        AdapterRunRecord,
        AuditEventRecord,
        LegacyObjectMappingRecord,
    )
    from zw_brain.shared.db import create_session_factory  # noqa: PLC0415

    tenant_id = str(payload.get("tenant_id") or _DEFAULT_TENANT_ID)
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        mapping_rows = session.execute(
            select(
                LegacyObjectMappingRecord.canonical_type,
                LegacyObjectMappingRecord.legacy_system,
                LegacyObjectMappingRecord.mapping_status,
                func.count(LegacyObjectMappingRecord.id),
            )
            .where(LegacyObjectMappingRecord.tenant_id == tenant_id)
            .group_by(
                LegacyObjectMappingRecord.canonical_type,
                LegacyObjectMappingRecord.legacy_system,
                LegacyObjectMappingRecord.mapping_status,
            )
        ).all()
        recent_adapter_runs = session.execute(
            select(AdapterRunRecord)
            .where(AdapterRunRecord.tenant_id == tenant_id)
            .order_by(desc(AdapterRunRecord.finished_at))
            .limit(20)
        ).scalars().all()
        recent_rollbacks = session.execute(
            select(AuditEventRecord)
            .where(AuditEventRecord.skill_id == "legacy.migration.rollback")
            .order_by(desc(AuditEventRecord.occurred_at))
            .limit(5)
        ).scalars().all()

    totals = {"mappings": 0, "mapped": 0, "conflicted": 0, "rolled_back": 0, "other": 0}
    by_canonical: dict[str, dict[str, int]] = {}
    by_legacy: dict[str, dict[str, int]] = {}
    for canonical_type, legacy_system, mapping_status, count in mapping_rows:
        totals["mappings"] += count
        bucket = mapping_status if mapping_status in {"mapped", "conflicted", "rolled_back"} else "other"
        totals[bucket] = totals.get(bucket, 0) + count
        c = by_canonical.setdefault(canonical_type, {"total": 0, "mapped": 0, "conflicted": 0, "rolled_back": 0})
        c["total"] += count
        c[bucket] = c.get(bucket, 0) + count
        leg = by_legacy.setdefault(legacy_system, {"total": 0, "mapped": 0, "conflicted": 0, "rolled_back": 0})
        leg["total"] += count
        leg[bucket] = leg.get(bucket, 0) + count

    adapter_runs = [
        {
            "adapter_slug": run.adapter_slug,
            "operation": run.operation,
            "status": run.status,
            "target_count": run.target_count,
            "success_count": run.success_count,
            "failure_count": run.failure_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error_summary": run.error_summary,
        }
        for run in recent_adapter_runs
    ]
    rollbacks = [
        {
            "audit_id": ev.request_id,
            "actor": ev.actor,
            "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
            "scope": (ev.payload_json or {}).get("scope") if isinstance(ev.payload_json, dict) else None,
            "rolled_back": (ev.payload_json or {}).get("rolled_back") if isinstance(ev.payload_json, dict) else None,
            "suspended_by_type": (ev.payload_json or {}).get("suspended_by_type") if isinstance(ev.payload_json, dict) else None,
        }
        for ev in recent_rollbacks
        if isinstance(ev.payload_json, dict) and ev.payload_json.get("tenant_id") == tenant_id
    ]

    work_queue_cards = deps.services.governance.build_m0_work_queue_cards(
        totals=totals,
        by_canonical=by_canonical,
        adapter_runs=adapter_runs,
        rollbacks=rollbacks,
    )

    return {
        "tenant_id": tenant_id,
        "totals": totals,
        "by_canonical_type": [
            {"canonical_type": k, **v} for k, v in sorted(by_canonical.items())
        ],
        "by_legacy_system": [
            {"legacy_system": k, **v} for k, v in sorted(by_legacy.items())
        ],
        "recent_adapter_runs": adapter_runs,
        "recent_rollbacks": rollbacks,
        "work_queue_cards": work_queue_cards,
    }
