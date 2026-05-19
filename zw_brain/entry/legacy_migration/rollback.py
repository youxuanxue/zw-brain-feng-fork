"""M0 rollback: invalidate legacy mappings + optionally suspend canonical records.

Semantics
---------
A rollback marks every `legacy_object_mapping` row in the requested scope
with `mapping_status = "rolled_back"`. The canonical records themselves are
left intact by default so the audit chain stays inspectable; they can be
re-emitted by re-running the importer (which will create fresh mappings).

When `--also-suspend-canonical` is passed, rollback additionally flips the
status column on a known subset of canonical records (catalog_entry,
resource_asset, application_record, approval_case) to `suspended` so that
operators can quickly hide partially-migrated records from end-user views (J1 找数→用数 / J2 挂数→维数 / J3 看全局→处异常 旅程).

Scope can be expressed three ways (pick exactly one):

    --legacy-system=dsp_catalog       (typical: rollback one schema)
    --source-ref-prefix=dsp_catalog:data_catalog:
    --batch-id=B-2026-05-16-01        (matches evidence_json.import_batch_id)

A dry-run lists what would change without writing. `--commit` is required
for any state-changing operation; both `--commit` and `--dry-run` cannot
be combined.

Every rollback emits one `audit_event(kind="migration.rollback")` summarizing
scope, counts, and operator. Individual mapping flips are not audited (they
are derivable from the summary + mapping table).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

# Avoid importing zw_brain.adapters.* — entry layer must not depend on adapter layer.
from zw_brain.domain.models import (
    ApplicationRecord,
    ApprovalCaseRecord,
    AuditEventRecord,
    CatalogEntryRecord,
    LegacyObjectMappingRecord,
    ResourceAssetRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.migrate import ensure_runtime_schema

DEFAULT_TENANT = "sd-default"

# Canonical types whose status columns we know how to flip. Keep this list
# narrow and obvious — other canonical types (objection, topic_package,
# delivery_task, ...) have their own lifecycle states and should not be
# touched by a blanket rollback.
_CANONICAL_SUSPEND_TABLE = {
    "catalog_entry": (CatalogEntryRecord, "lifecycle_status", "suspended"),
    "resource_asset": (ResourceAssetRecord, "lifecycle_status", "suspended"),
    "application_record": (ApplicationRecord, "status", "suspended"),
    "approval_case": (ApprovalCaseRecord, "current_status", "suspended"),
}


def rollback(
    *,
    tenant_id: str = DEFAULT_TENANT,
    legacy_system: str | None = None,
    source_ref_prefix: str | None = None,
    batch_id: str | None = None,
    dry_run: bool = True,
    also_suspend_canonical: bool = False,
    actor: str = "m0-migration",
) -> dict[str, Any]:
    """Roll back legacy mappings for the requested scope.

    Returns a report dict with counts, scanned mapping ids, suspended
    canonical refs (when applicable), and the audit_event id.
    """
    scope_count = sum(
        1 for x in (legacy_system, source_ref_prefix, batch_id) if x
    )
    if scope_count == 0:
        raise ValueError("must specify exactly one of --legacy-system, --source-ref-prefix, --batch-id")
    if scope_count > 1:
        raise ValueError("specify only one scope at a time")

    ensure_runtime_schema()
    SessionLocal = create_session_factory()
    audit_id = str(uuid.uuid4())
    suspended_by_type: dict[str, int] = {}
    suspended_skipped: dict[str, int] = {}
    scanned_ids: list[str] = []
    rolled_back = 0
    already_rolled_back = 0
    canonical_refs_suspended: list[tuple[str, str]] = []
    statement = _build_scope_statement(tenant_id, legacy_system, source_ref_prefix, batch_id)

    with SessionLocal() as session:
        mappings = list(session.execute(statement).scalars())
        for mapping in mappings:
            scanned_ids.append(mapping.id)
            if mapping.mapping_status == "rolled_back":
                already_rolled_back += 1
                continue
            if not dry_run:
                mapping.mapping_status = "rolled_back"
                evidence = dict(mapping.evidence_json or {})
                evidence.setdefault("rollback_history", []).append(
                    {
                        "audit_id": audit_id,
                        "actor": actor,
                        "at": _utcnow_iso(),
                        "previous_status": "mapped",
                    }
                )
                mapping.evidence_json = evidence
            rolled_back += 1

        if also_suspend_canonical and not dry_run:
            for mapping in mappings:
                handler = _CANONICAL_SUSPEND_TABLE.get(mapping.canonical_type)
                if handler is None:
                    suspended_skipped[mapping.canonical_type] = (
                        suspended_skipped.get(mapping.canonical_type, 0) + 1
                    )
                    continue
                record_cls, status_col, target_value = handler
                session.execute(
                    update(record_cls)
                    .where(record_cls.tenant_id == tenant_id)
                    .where(record_cls.id == mapping.canonical_ref)
                    .values({status_col: target_value})
                )
                suspended_by_type[mapping.canonical_type] = (
                    suspended_by_type.get(mapping.canonical_type, 0) + 1
                )
                canonical_refs_suspended.append((mapping.canonical_type, mapping.canonical_ref))

        if not dry_run:
            session.add(
                AuditEventRecord(
                    request_id=audit_id,
                    actor=actor,
                    skill_id="legacy.migration.rollback",
                    phase="completed",
                    payload_json={
                        "tenant_id": tenant_id,
                        "scope": {
                            "legacy_system": legacy_system,
                            "source_ref_prefix": source_ref_prefix,
                            "batch_id": batch_id,
                        },
                        "rolled_back": rolled_back,
                        "already_rolled_back": already_rolled_back,
                        "also_suspend_canonical": also_suspend_canonical,
                        "suspended_by_type": suspended_by_type,
                        "suspended_skipped": suspended_skipped,
                    },
                )
            )
            session.commit()

    return {
        "audit_id": audit_id if not dry_run else None,
        "dry_run": dry_run,
        "tenant_id": tenant_id,
        "scope": {
            "legacy_system": legacy_system,
            "source_ref_prefix": source_ref_prefix,
            "batch_id": batch_id,
        },
        "scanned": len(scanned_ids),
        "rolled_back": rolled_back,
        "already_rolled_back": already_rolled_back,
        "also_suspend_canonical": also_suspend_canonical,
        "suspended_by_type": suspended_by_type,
        "suspended_skipped": suspended_skipped,
        "sample_mapping_ids": scanned_ids[:10],
    }


def _build_scope_statement(
    tenant_id: str,
    legacy_system: str | None,
    source_ref_prefix: str | None,
    batch_id: str | None,
):
    statement = select(LegacyObjectMappingRecord).where(
        LegacyObjectMappingRecord.tenant_id == tenant_id
    )
    if legacy_system:
        statement = statement.where(LegacyObjectMappingRecord.legacy_system == legacy_system)
    if source_ref_prefix:
        # source_ref is indexed; prefix scan is acceptable for one-time rollback.
        statement = statement.where(LegacyObjectMappingRecord.source_ref.like(f"{source_ref_prefix}%"))
    if batch_id:
        # batch_id lives inside evidence_json — SQLite JSON access pattern.
        statement = statement.where(
            LegacyObjectMappingRecord.evidence_json["import_batch_id"].as_string() == batch_id
        )
    return statement


def _utcnow_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", default=DEFAULT_TENANT)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--legacy-system", help="Match LegacyObjectMappingRecord.legacy_system (typical: schema name)")
    scope.add_argument("--source-ref-prefix", help="Match LegacyObjectMappingRecord.source_ref LIKE prefix%%")
    scope.add_argument("--batch-id", help="Match evidence_json.import_batch_id exactly")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true", help="Actually apply the rollback (writes mapping_status + audit_event)")
    parser.add_argument("--also-suspend-canonical", action="store_true", help="Flip status to suspended on catalog_entry / resource_asset / application_record / approval_case")
    parser.add_argument("--actor", default="m0-migration")
    parser.add_argument("--report", type=Path, default=None, help="Write report JSON to this path (optional)")
    args = parser.parse_args(argv)

    report = rollback(
        tenant_id=args.tenant,
        legacy_system=args.legacy_system,
        source_ref_prefix=args.source_ref_prefix,
        batch_id=args.batch_id,
        dry_run=args.dry_run and not args.commit,
        also_suspend_canonical=args.also_suspend_canonical,
        actor=args.actor,
    )
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
