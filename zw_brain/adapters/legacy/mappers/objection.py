"""dsp_handling → ObjectionCase aggregate mapper.

Step 8 of the bridging chain (last). Closes the township-fill demo arc — application/delivery is
already in canonical form; this mapper attaches the corresponding 异议 (objections) so
the WebUI can show 申请 → 交付 → 异议 → 评价 end-to-end.

Tables → records:
  data_objection           → ObjectionCaseRecord (preserves legacy id)
  data_objection_process   → ObjectionProcessRecord
  data_objection_evaluate  → ObjectionEvaluationRecord
  data_objection_authz     → ObjectionEvidenceRecord(evidence_type='authorization')
  data_objection_catalog   → ObjectionEvidenceRecord(evidence_type='catalog')
  data_objection_content   → ObjectionEvidenceRecord(evidence_type='quality')
  data_objection_resource  → ObjectionEvidenceRecord(evidence_type='resource')
  data_objection_use       → ObjectionEvidenceRecord(evidence_type='usage')

Sensitive fields (contact / phone / handler_phone / creator_email) flow through raw
into the JSON payloads of the canonical records — read-side mask layer must apply.
No real secrets in dsp_handling.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from zw_brain.adapters.legacy._common import ImportStats, coerce_int, finish_run, schema_from_dump_name
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.models import (
    ObjectionCaseRecord,
    ObjectionEvaluationRecord,
    ObjectionEvidenceRecord,
    ObjectionProcessRecord,
)
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json

OBJECTION_KIND_BY_TYPE: dict[str, str] = {
    "1": "catalog_quality",
    "2": "resource_quality",
    "3": "authorization",
    "4": "usage",
}
OBJECTION_TARGET_BY_TYPE: dict[str, str] = {
    "1": "catalog",
    "2": "resource",
    "3": "authorization",
    "4": "delivery",
}
STATUS_MAP: dict[str, str] = {
    "1": "draft",
    "2": "submitted",
    "3": "platform_investigating",
    "4": "provider_investigating",
    "5": "rejected",
    "6": "resolved",
    "7": "provider_investigating",
    "9": "platform_investigating",
    "91": "resolved",
    "92": "rejected",
    "93": "closed",
}


class ObjectionMapper:
    HANDLED_TABLES = {
        "data_objection",
        "data_objection_process",
        "data_objection_evaluate",
        "data_objection_authz",
        "data_objection_catalog",
        "data_objection_content",
        "data_objection_resource",
        "data_objection_use",
    }
    ADAPTER_SLUG = "legacy.objection.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # Group rows by parent objection_id so we can apply children alongside parent.
        objections: list[dict[str, Any]] = []
        children: dict[str, dict[str, list[dict[str, Any]]]] = {}
        child_source_counts: dict[str, int] = {}

        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            if table == "data_objection":
                if str(row.get("status")) == "0":  # 0 = legacy "deleted"
                    stats.skip(f"{table}.status_deleted")
                    continue
                objections.append(row)
            else:
                child_source_counts[table] = child_source_counts.get(table, 0) + 1
                obj_id = row.get("objection_id")
                if obj_id is None:
                    stats.skip(f"{table}.no_objection_id")
                    continue
                children.setdefault(obj_id, {}).setdefault(table, []).append(row)

        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            for objection in objections:
                obj_id = objection["id"]
                kid_buckets = children.get(obj_id, {})
                self._upsert_case(session, objection, kid_buckets, legacy_system)
                stats.bump("data_objection")
                for table, rows in kid_buckets.items():
                    stats.counts[f"{table}.attached"] = stats.counts.get(f"{table}.attached", 0) + len(rows)
            session.commit()

        for table, source_count in child_source_counts.items():
            attached = stats.counts.get(f"{table}.attached", 0)
            already_skipped = sum(
                count
                for key, count in stats.skipped.items()
                if key.startswith(f"{table}.")
            )
            orphan_count = source_count - attached - already_skipped
            if orphan_count > 0:
                stats.skipped[f"{table}.orphan_or_deleted_parent"] = stats.skipped.get(
                    f"{table}.orphan_or_deleted_parent", 0
                ) + orphan_count

        # legacy_object_mapping for each objection (separate session — repo manages own)
        for objection in objections:
            self.legacy_repo.upsert_mapping(
                {
                    "source_ref": f"{legacy_system}:data_objection:{objection['id']}",
                    "legacy_system": legacy_system,
                    "legacy_object_type": "data_objection",
                    "legacy_object_ref": objection["id"],
                    "canonical_type": "ObjectionCaseRecord",
                    "canonical_ref": objection["id"],
                    "evidence_json": {
                        "title": objection.get("objection_title"),
                        "objection_type": objection.get("objection_type"),
                    },
                },
                tenant_id=self.tenant_id,
            )

        finish_run(self.adapter_repo, stats, adapter_slug=self.ADAPTER_SLUG, dump_path=dump_path, started_at=started_at, tenant_id=self.tenant_id)
        return stats

    def _upsert_case(
        self,
        session: Any,
        objection: dict[str, Any],
        kid_buckets: dict[str, list[dict[str, Any]]],
        legacy_system: str,
    ) -> None:
        obj_id = objection["id"]
        existing = session.execute(
            select(ObjectionCaseRecord).where(ObjectionCaseRecord.id == obj_id)
        ).scalar_one_or_none()

        objection_type = str(objection.get("objection_type") or "")
        target_type = OBJECTION_TARGET_BY_TYPE.get(objection_type, "resource")
        target_id = str(objection.get("objection_data_id") or obj_id)
        kind = OBJECTION_KIND_BY_TYPE.get(objection_type, "usage")
        status = STATUS_MAP.get(str(objection.get("status") or ""), "submitted")
        title = objection.get("objection_title") or "未命名异议"

        # contact + phone + creator_email + creator_phone are business-visible sensitive
        complainant_snapshot = {
            "dept_id": objection.get("objection_dept_id"),
            "dept_name": objection.get("objection_dept_name"),
            "creator_id": objection.get("creator_id"),
            "creator_name": objection.get("creator_name"),
            "contact_name": objection.get("contact"),
            "contact_phone": objection.get("phone"),
            "creator_email": objection.get("creator_email"),
            "creator_phone": objection.get("creator_phone"),
        }
        provider_snapshot = {
            "org_id": objection.get("data_org_id"),
            "org_name": objection.get("data_org_name"),
            "data_name": objection.get("objection_data_name"),
        }

        if existing is None:
            existing = ObjectionCaseRecord(
                id=obj_id,
                tenant_id=self.tenant_id,
                objection_kind=kind,
                target_type=target_type,
                target_id=target_id,
                related_application_id=None,
                title=title,
                complainant_org_id=str(objection.get("objection_dept_id") or "unknown"),
                complainant_org_snapshot_json=safe_json(complainant_snapshot),
                provider_org_id=str(objection.get("data_org_id") or "unknown"),
                provider_org_snapshot_json=safe_json(provider_snapshot),
                basis_text=objection.get("objection_title"),
                expected_result=None,
                status=status,
                resolved_summary=None,
            )
            session.add(existing)
            session.flush()
        else:
            existing.objection_kind = kind
            existing.target_type = target_type
            existing.target_id = target_id
            existing.title = title
            existing.complainant_org_id = str(objection.get("objection_dept_id") or "unknown")
            existing.complainant_org_snapshot_json = safe_json(complainant_snapshot)
            existing.provider_org_id = str(objection.get("data_org_id") or "unknown")
            existing.provider_org_snapshot_json = safe_json(provider_snapshot)
            existing.basis_text = objection.get("objection_title")
            existing.status = status
            existing.row_version = (existing.row_version or 1) + 1

        # Wipe + replay children. Idempotent against re-runs because the unique parent
        # owns the children; if any child row has been edited in zw-brain since import,
        # this re-import overwrites it (intentional, mapper is the SoT for legacy data).
        for child_model in (ObjectionProcessRecord, ObjectionEvaluationRecord, ObjectionEvidenceRecord):
            session.execute(delete(child_model).where(child_model.objection_id == obj_id))

        for proc in kid_buckets.get("data_objection_process", []):
            session.add(
                ObjectionProcessRecord(
                    objection_id=obj_id,
                    node_name=str(proc.get("node_name") or "未命名节点"),
                    handler_org_id=proc.get("org_id"),
                    handler_snapshot_json=safe_json({
                        "org_id": proc.get("org_id"),
                        "org_name": proc.get("org_name"),
                        "user_code": proc.get("user_code"),
                        "user_name": proc.get("user_name"),
                        "handler_name": proc.get("handler_name"),
                        "handler_phone": proc.get("handler_phone"),
                    }),
                    action_type=str(proc.get("inspect_status") or "investigate"),
                    action_result=_action_result_from(proc.get("handler_result")),
                    opinion=proc.get("opinion"),
                )
            )

        for ev in kid_buckets.get("data_objection_evaluate", []):
            session.add(
                ObjectionEvaluationRecord(
                    objection_id=obj_id,
                    evaluator_snapshot_json=safe_json({
                        "creator_id": ev.get("creator_id"),
                        "creator_name": ev.get("creator_name"),
                        "org_id": ev.get("org_id"),
                        "org_name": ev.get("org_name"),
                    }),
                    solved_flag=str(ev.get("solved")) == "1",
                    overall_score=coerce_int(ev.get("whole_score") or ev.get("score"), 0) or None,
                    timeliness_score=coerce_int(ev.get("time_score"), 0) or None,
                    result_score=coerce_int(ev.get("result_score"), 0) or None,
                    comment=ev.get("content"),
                )
            )

        evidence_table_to_type = {
            "data_objection_authz": "authorization",
            "data_objection_catalog": "catalog",
            "data_objection_content": "quality",
            "data_objection_resource": "resource",
            "data_objection_use": "usage",
        }
        for child_table, evidence_type in evidence_table_to_type.items():
            for ev in kid_buckets.get(child_table, []):
                session.add(
                    ObjectionEvidenceRecord(
                        objection_id=obj_id,
                        evidence_type=evidence_type,
                        content_json=safe_json(ev),
                        submitted_by_json=safe_json({"source": f"{legacy_system}:{child_table}"}),
                    )
                )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _action_result_from(handler_result: Any) -> str:
    if handler_result in ("1", 1, True):
        return "pass"
    if handler_result in ("0", 0, False):
        return "fail"
    return "pending"
