from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from zw_brain.domain.models import (
    LineageRelationProjectionRecord,
    MetadataGatherEvidenceProjectionRecord,
    QualityEvidenceProjectionRecord,
    ResourceSchemaMappingRecord,
    ResourceSchemaSnapshotRecord,
)
from zw_brain.domain.repositories.legacy_mapping import upsert_legacy_mapping_in_session
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.sanitization import safe_json


def _now() -> datetime:
    return datetime.now(UTC)


def _stable_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(safe_json(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MetadataEvidenceRepository:
    def upsert_schema_mapping(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ResourceSchemaMappingRecord:
        SessionLocal = create_session_factory()
        now = _now()
        mapping_code = str(
            payload.get("mapping_code")
            or f"{payload['catalog_item_code']}:{payload['resource_code']}:{payload['binding_code']}"
        )
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceSchemaMappingRecord).where(
                    ResourceSchemaMappingRecord.tenant_id == tenant_id,
                    ResourceSchemaMappingRecord.mapping_code == mapping_code,
                )
            ).scalar_one_or_none()
            if record is None:
                record = ResourceSchemaMappingRecord(
                    tenant_id=tenant_id,
                    mapping_code=mapping_code,
                    catalog_code=str(payload["catalog_code"]),
                    catalog_item_code=str(payload["catalog_item_code"]),
                    resource_code=str(payload["resource_code"]),
                    binding_code=str(payload["binding_code"]),
                    source_schema_ref=safe_json(payload.get("source_schema_ref") or {}),
                    mapping_rule_json=safe_json(payload.get("mapping_rule_json") or {}),
                    confidence_level=str(payload.get("confidence_level", "confirmed")),
                    evidence_ref=payload.get("evidence_ref"),
                    status=str(payload.get("status", "active")),
                    confirmed_by=payload.get("confirmed_by"),
                    confirmed_at=payload.get("confirmed_at") or now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.catalog_code = str(payload.get("catalog_code", record.catalog_code))
                record.catalog_item_code = str(payload.get("catalog_item_code", record.catalog_item_code))
                record.resource_code = str(payload.get("resource_code", record.resource_code))
                record.binding_code = str(payload.get("binding_code", record.binding_code))
                record.source_schema_ref = safe_json(payload.get("source_schema_ref") or record.source_schema_ref)
                record.mapping_rule_json = safe_json(payload.get("mapping_rule_json") or record.mapping_rule_json)
                record.confidence_level = str(payload.get("confidence_level", record.confidence_level))
                record.evidence_ref = payload.get("evidence_ref", record.evidence_ref)
                record.status = str(payload.get("status", record.status))
                record.confirmed_by = payload.get("confirmed_by", record.confirmed_by)
                record.confirmed_at = payload.get("confirmed_at", record.confirmed_at)
                record.updated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": payload.get("source_ref") or record.evidence_ref or mapping_code,
                    "legacy_object_ref": payload.get("legacy_object_ref") or mapping_code,
                    "canonical_type": "resource_schema_mapping",
                    "canonical_ref": mapping_code,
                    "evidence_json": {
                        "catalog_item_code": record.catalog_item_code,
                        "resource_code": record.resource_code,
                        "binding_code": record.binding_code,
                    },
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def list_schema_mappings(
        self,
        *,
        resource_code: str | None = None,
        resource_codes: list[str] | None = None,
        catalog_code: str | None = None,
        include_inactive: bool = True,
        tenant_id: str = "sd-default",
    ) -> list[ResourceSchemaMappingRecord]:
        # resource_codes (plural IN) perf knob mirrors legacy_mapping.list_mappings(canonical_refs=):
        # 空 list → 不发查询直接 []; None → 维持 tenant-only 全量。
        if resource_codes is not None and not resource_codes:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceSchemaMappingRecord).where(ResourceSchemaMappingRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceSchemaMappingRecord.resource_code == resource_code)
            if resource_codes:
                statement = statement.where(ResourceSchemaMappingRecord.resource_code.in_(resource_codes))
            if catalog_code:
                statement = statement.where(ResourceSchemaMappingRecord.catalog_code == catalog_code)
            if not include_inactive:
                statement = statement.where(ResourceSchemaMappingRecord.status == "active")
            return list(session.execute(statement.order_by(ResourceSchemaMappingRecord.mapping_code)).scalars())

    def rebind_catalog_code(self, legacy_catalog_code: str, catalog_code: str, *, tenant_id: str = "sd-default") -> int:
        if legacy_catalog_code == catalog_code:
            return 0
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            records = list(
                session.execute(
                    select(ResourceSchemaMappingRecord).where(
                        ResourceSchemaMappingRecord.tenant_id == tenant_id,
                        ResourceSchemaMappingRecord.catalog_code == legacy_catalog_code,
                    )
                ).scalars()
            )
            for record in records:
                record.catalog_code = catalog_code
            session.commit()
            return len(records)

    def list_schema_snapshots(self, *, resource_code: str | None = None, resource_codes: list[str] | None = None, binding_code: str | None = None, tenant_id: str = "sd-default") -> list[ResourceSchemaSnapshotRecord]:
        # resource_codes (plural IN) perf knob mirrors legacy_mapping.list_mappings(canonical_refs=):
        # 空 list → 不发查询直接 []; None → 维持 tenant-only 全量。
        if resource_codes is not None and not resource_codes:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceSchemaSnapshotRecord).where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceSchemaSnapshotRecord.resource_code == resource_code)
            if resource_codes:
                statement = statement.where(ResourceSchemaSnapshotRecord.resource_code.in_(resource_codes))
            if binding_code:
                statement = statement.where(ResourceSchemaSnapshotRecord.binding_code == binding_code)
            return list(session.execute(statement.order_by(ResourceSchemaSnapshotRecord.captured_at)).scalars())

    def list_schema_snapshots_by_binding_codes(self, binding_codes: list[str], *, tenant_id: str = "sd-default") -> list[ResourceSchemaSnapshotRecord]:
        """Batched binding_code lookup (single IN-query, no per-code N+1).

        Used by the schema-view bridge: a resource_asset.resource_code rarely keys
        resource_schema_snapshot directly (snapshots are keyed by db_meta_table.meta_id),
        but resource_schema_mapping.binding_code does match snapshot.binding_code. The
        handler resolves a resource's active mapping binding_codes, then fetches all
        snapshots for them here in one query (in_()) to avoid N+1 on the read path.
        """
        codes = [c for c in dict.fromkeys(binding_codes) if c]
        if not codes:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = (
                select(ResourceSchemaSnapshotRecord)
                .where(
                    ResourceSchemaSnapshotRecord.tenant_id == tenant_id,
                    ResourceSchemaSnapshotRecord.binding_code.in_(codes),
                )
                .order_by(ResourceSchemaSnapshotRecord.captured_at)
            )
            return list(session.execute(statement).scalars())

    def list_gather_evidence(self, *, resource_code: str | None = None, resource_codes: list[str] | None = None, status: str | None = None, tenant_id: str = "sd-default") -> list[MetadataGatherEvidenceProjectionRecord]:
        # resource_codes (plural IN) perf knob mirrors legacy_mapping.list_mappings(canonical_refs=):
        # 空 list → 不发查询直接 []; None → 维持 tenant-only 全量。
        if resource_codes is not None and not resource_codes:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(MetadataGatherEvidenceProjectionRecord).where(MetadataGatherEvidenceProjectionRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(MetadataGatherEvidenceProjectionRecord.resource_code == resource_code)
            if resource_codes:
                statement = statement.where(MetadataGatherEvidenceProjectionRecord.resource_code.in_(resource_codes))
            if status:
                statement = statement.where(MetadataGatherEvidenceProjectionRecord.status == status)
            return list(session.execute(statement.order_by(MetadataGatherEvidenceProjectionRecord.generated_at)).scalars())

    def upsert_schema_snapshot(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> ResourceSchemaSnapshotRecord:
        SessionLocal = create_session_factory()
        now = _now()
        schema_json = safe_json(payload.get("schema_json") or {})
        snapshot_ref = str(payload.get("snapshot_ref") or f"{payload['resource_code']}:{_stable_hash(schema_json)[:16]}")
        with SessionLocal() as session:
            record = session.execute(
                select(ResourceSchemaSnapshotRecord).where(
                    ResourceSchemaSnapshotRecord.tenant_id == tenant_id,
                    ResourceSchemaSnapshotRecord.snapshot_ref == snapshot_ref,
                )
            ).scalar_one_or_none()
            if record is None:
                record = ResourceSchemaSnapshotRecord(
                    tenant_id=tenant_id,
                    snapshot_ref=snapshot_ref,
                    resource_code=str(payload["resource_code"]),
                    binding_code=payload.get("binding_code"),
                    schema_json=schema_json,
                    source_ref=payload.get("source_ref"),
                    schema_hash=str(payload.get("schema_hash") or _stable_hash(schema_json)),
                    captured_at=payload.get("captured_at") or now,
                    created_at=now,
                )
                session.add(record)
            else:
                record.resource_code = str(payload.get("resource_code", record.resource_code))
                record.binding_code = payload.get("binding_code", record.binding_code)
                record.schema_json = schema_json
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.schema_hash = str(payload.get("schema_hash") or _stable_hash(schema_json))
                record.captured_at = payload.get("captured_at", record.captured_at)
            if record.source_ref:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": record.source_ref,
                        "legacy_object_ref": payload.get("legacy_object_ref") or snapshot_ref,
                        "canonical_type": "resource_schema_snapshot",
                        "canonical_ref": snapshot_ref,
                        "evidence_json": {"resource_code": record.resource_code, "binding_code": record.binding_code},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
            session.refresh(record)
            return record

    def upsert_gather_evidence(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> MetadataGatherEvidenceProjectionRecord:
        SessionLocal = create_session_factory()
        now = _now()
        gather_task_ref = str(payload["gather_task_ref"])
        with SessionLocal() as session:
            record = session.execute(
                select(MetadataGatherEvidenceProjectionRecord).where(
                    MetadataGatherEvidenceProjectionRecord.tenant_id == tenant_id,
                    MetadataGatherEvidenceProjectionRecord.gather_task_ref == gather_task_ref,
                )
            ).scalar_one_or_none()
            if record is None:
                record = MetadataGatherEvidenceProjectionRecord(
                    tenant_id=tenant_id,
                    gather_task_ref=gather_task_ref,
                    resource_code=str(payload["resource_code"]),
                    source_system_ref=payload.get("source_system_ref"),
                    schema_snapshot_ref=payload.get("schema_snapshot_ref"),
                    status=str(payload.get("status", "pending")),
                    error_summary=payload.get("error_summary"),
                    evidence_json=safe_json(payload.get("evidence_json") or {}),
                    started_at=payload.get("started_at"),
                    finished_at=payload.get("finished_at"),
                    generated_at=now,
                )
                session.add(record)
            else:
                record.resource_code = str(payload.get("resource_code", record.resource_code))
                record.source_system_ref = payload.get("source_system_ref", record.source_system_ref)
                record.schema_snapshot_ref = payload.get("schema_snapshot_ref", record.schema_snapshot_ref)
                record.status = str(payload.get("status", record.status))
                record.error_summary = payload.get("error_summary", record.error_summary)
                record.evidence_json = safe_json(payload.get("evidence_json") or record.evidence_json)
                record.started_at = payload.get("started_at", record.started_at)
                record.finished_at = payload.get("finished_at", record.finished_at)
                record.generated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": payload.get("source_ref") or record.source_system_ref or gather_task_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or gather_task_ref,
                    "canonical_type": "metadata_gather_evidence_projection",
                    "canonical_ref": gather_task_ref,
                    "evidence_json": {"resource_code": record.resource_code, "status": record.status},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def upsert_lineage_relation(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> LineageRelationProjectionRecord:
        SessionLocal = create_session_factory()
        now = _now()
        relation_ref = str(payload["relation_ref"])
        with SessionLocal() as session:
            record = session.execute(
                select(LineageRelationProjectionRecord).where(
                    LineageRelationProjectionRecord.tenant_id == tenant_id,
                    LineageRelationProjectionRecord.relation_ref == relation_ref,
                )
            ).scalar_one_or_none()
            if record is None:
                record = LineageRelationProjectionRecord(
                    tenant_id=tenant_id,
                    relation_ref=relation_ref,
                    relation_scope=str(payload.get("relation_scope", "table")),
                    source_resource_code=payload.get("source_resource_code"),
                    source_schema_ref=payload.get("source_schema_ref"),
                    target_resource_code=payload.get("target_resource_code"),
                    target_schema_ref=payload.get("target_schema_ref"),
                    relation_type=str(payload.get("relation_type", "imported")),
                    relation_rule_json=safe_json(payload.get("relation_rule_json") or {}),
                    source_evidence_ref=payload.get("source_evidence_ref"),
                    generated_at=now,
                )
                session.add(record)
            else:
                record.relation_scope = str(payload.get("relation_scope", record.relation_scope))
                record.source_resource_code = payload.get("source_resource_code", record.source_resource_code)
                record.source_schema_ref = payload.get("source_schema_ref", record.source_schema_ref)
                record.target_resource_code = payload.get("target_resource_code", record.target_resource_code)
                record.target_schema_ref = payload.get("target_schema_ref", record.target_schema_ref)
                record.relation_type = str(payload.get("relation_type", record.relation_type))
                record.relation_rule_json = safe_json(payload.get("relation_rule_json") or record.relation_rule_json)
                record.source_evidence_ref = payload.get("source_evidence_ref", record.source_evidence_ref)
                record.generated_at = now
            upsert_legacy_mapping_in_session(
                session,
                {
                    "source_ref": payload.get("source_ref") or record.source_evidence_ref or relation_ref,
                    "legacy_object_ref": payload.get("legacy_object_ref") or relation_ref,
                    "canonical_type": "lineage_relation_projection",
                    "canonical_ref": relation_ref,
                    "evidence_json": {"relation_scope": record.relation_scope, "relation_type": record.relation_type},
                },
                tenant_id=tenant_id,
            )
            session.commit()
            session.refresh(record)
            return record

    def list_lineage_relations(self, *, resource_code: str | None = None, resource_codes: list[str] | None = None, relation_scope: str | None = None, tenant_id: str = "sd-default") -> list[LineageRelationProjectionRecord]:
        # resource_codes (plural IN) perf knob mirrors legacy_mapping.list_mappings(canonical_refs=);
        # 保留 OR(source|target) 语义同单数 resource_code。
        # 空 list → 不发查询直接 []; None → 维持 tenant-only 全量。
        if resource_codes is not None and not resource_codes:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(LineageRelationProjectionRecord).where(LineageRelationProjectionRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(
                    (LineageRelationProjectionRecord.source_resource_code == resource_code)
                    | (LineageRelationProjectionRecord.target_resource_code == resource_code)
                )
            if resource_codes:
                statement = statement.where(
                    LineageRelationProjectionRecord.source_resource_code.in_(resource_codes)
                    | LineageRelationProjectionRecord.target_resource_code.in_(resource_codes)
                )
            if relation_scope:
                statement = statement.where(LineageRelationProjectionRecord.relation_scope == relation_scope)
            return list(session.execute(statement.order_by(LineageRelationProjectionRecord.relation_ref)).scalars())

    def list_quality_evidence(self, *, target_type: str | None = None, target_ref: str | None = None, target_refs: list[str] | None = None, tenant_id: str = "sd-default") -> list[QualityEvidenceProjectionRecord]:
        # target_refs (plural IN) perf knob mirrors legacy_mapping.list_mappings(canonical_refs=);
        # keyed by target_ref (NOT resource_code); 与 target_type 单数过滤组合 AND。
        # 空 list → 不发查询直接 []; None → 维持 tenant-only 全量。
        if target_refs is not None and not target_refs:
            return []
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(QualityEvidenceProjectionRecord).where(QualityEvidenceProjectionRecord.tenant_id == tenant_id)
            if target_type:
                statement = statement.where(QualityEvidenceProjectionRecord.target_type == target_type)
            if target_ref:
                statement = statement.where(QualityEvidenceProjectionRecord.target_ref == target_ref)
            if target_refs:
                statement = statement.where(QualityEvidenceProjectionRecord.target_ref.in_(target_refs))
            return list(session.execute(statement.order_by(QualityEvidenceProjectionRecord.generated_at)).scalars())

    def upsert_quality_evidence(self, payload: dict[str, Any], *, tenant_id: str = "sd-default") -> QualityEvidenceProjectionRecord:
        SessionLocal = create_session_factory()
        now = _now()
        quality_ref = str(payload["quality_ref"])
        with SessionLocal() as session:
            record = session.execute(
                select(QualityEvidenceProjectionRecord).where(
                    QualityEvidenceProjectionRecord.tenant_id == tenant_id,
                    QualityEvidenceProjectionRecord.quality_ref == quality_ref,
                )
            ).scalar_one_or_none()
            if record is None:
                record = QualityEvidenceProjectionRecord(
                    tenant_id=tenant_id,
                    quality_ref=quality_ref,
                    target_type=str(payload["target_type"]),
                    target_ref=str(payload["target_ref"]),
                    quality_status=str(payload["quality_status"]),
                    score=payload.get("score"),
                    evidence_json=safe_json(payload.get("evidence_json") or {}),
                    source_ref=payload.get("source_ref"),
                    generated_at=now,
                )
                session.add(record)
            else:
                record.target_type = str(payload.get("target_type", record.target_type))
                record.target_ref = str(payload.get("target_ref", record.target_ref))
                record.quality_status = str(payload.get("quality_status", record.quality_status))
                record.score = payload.get("score", record.score)
                record.evidence_json = safe_json(payload.get("evidence_json") or record.evidence_json)
                record.source_ref = payload.get("source_ref", record.source_ref)
                record.generated_at = now
            if record.source_ref:
                upsert_legacy_mapping_in_session(
                    session,
                    {
                        "source_ref": record.source_ref,
                        "legacy_object_ref": payload.get("legacy_object_ref") or quality_ref,
                        "canonical_type": "quality_evidence_projection",
                        "canonical_ref": quality_ref,
                        "evidence_json": {"target_type": record.target_type, "target_ref": record.target_ref, "quality_status": record.quality_status},
                    },
                    tenant_id=tenant_id,
                )
            session.commit()
            session.refresh(record)
            return record
