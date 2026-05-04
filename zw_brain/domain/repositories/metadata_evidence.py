from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import hashlib
import json

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
    def upsert_schema_mapping(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ResourceSchemaMappingRecord:
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

    def list_schema_mappings(self, *, resource_code: str | None = None, catalog_code: str | None = None, tenant_id: str = "default") -> list[ResourceSchemaMappingRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceSchemaMappingRecord).where(ResourceSchemaMappingRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceSchemaMappingRecord.resource_code == resource_code)
            if catalog_code:
                statement = statement.where(ResourceSchemaMappingRecord.catalog_code == catalog_code)
            return list(session.execute(statement.order_by(ResourceSchemaMappingRecord.mapping_code)).scalars())

    def list_schema_snapshots(self, *, resource_code: str | None = None, binding_code: str | None = None, tenant_id: str = "default") -> list[ResourceSchemaSnapshotRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(ResourceSchemaSnapshotRecord).where(ResourceSchemaSnapshotRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(ResourceSchemaSnapshotRecord.resource_code == resource_code)
            if binding_code:
                statement = statement.where(ResourceSchemaSnapshotRecord.binding_code == binding_code)
            return list(session.execute(statement.order_by(ResourceSchemaSnapshotRecord.captured_at)).scalars())

    def list_gather_evidence(self, *, resource_code: str | None = None, status: str | None = None, tenant_id: str = "default") -> list[MetadataGatherEvidenceProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(MetadataGatherEvidenceProjectionRecord).where(MetadataGatherEvidenceProjectionRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(MetadataGatherEvidenceProjectionRecord.resource_code == resource_code)
            if status:
                statement = statement.where(MetadataGatherEvidenceProjectionRecord.status == status)
            return list(session.execute(statement.order_by(MetadataGatherEvidenceProjectionRecord.generated_at)).scalars())

    def upsert_schema_snapshot(self, payload: dict[str, Any], *, tenant_id: str = "default") -> ResourceSchemaSnapshotRecord:
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
            session.commit()
            session.refresh(record)
            return record

    def upsert_gather_evidence(self, payload: dict[str, Any], *, tenant_id: str = "default") -> MetadataGatherEvidenceProjectionRecord:
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
            session.commit()
            session.refresh(record)
            return record

    def upsert_lineage_relation(self, payload: dict[str, Any], *, tenant_id: str = "default") -> LineageRelationProjectionRecord:
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
            session.commit()
            session.refresh(record)
            return record

    def list_lineage_relations(self, *, resource_code: str | None = None, relation_scope: str | None = None, tenant_id: str = "default") -> list[LineageRelationProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(LineageRelationProjectionRecord).where(LineageRelationProjectionRecord.tenant_id == tenant_id)
            if resource_code:
                statement = statement.where(
                    (LineageRelationProjectionRecord.source_resource_code == resource_code)
                    | (LineageRelationProjectionRecord.target_resource_code == resource_code)
                )
            if relation_scope:
                statement = statement.where(LineageRelationProjectionRecord.relation_scope == relation_scope)
            return list(session.execute(statement.order_by(LineageRelationProjectionRecord.relation_ref)).scalars())

    def list_quality_evidence(self, *, target_type: str | None = None, target_ref: str | None = None, tenant_id: str = "default") -> list[QualityEvidenceProjectionRecord]:
        SessionLocal = create_session_factory()
        with SessionLocal() as session:
            statement = select(QualityEvidenceProjectionRecord).where(QualityEvidenceProjectionRecord.tenant_id == tenant_id)
            if target_type:
                statement = statement.where(QualityEvidenceProjectionRecord.target_type == target_type)
            if target_ref:
                statement = statement.where(QualityEvidenceProjectionRecord.target_ref == target_ref)
            return list(session.execute(statement.order_by(QualityEvidenceProjectionRecord.generated_at)).scalars())

    def upsert_quality_evidence(self, payload: dict[str, Any], *, tenant_id: str = "default") -> QualityEvidenceProjectionRecord:
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
            session.commit()
            session.refresh(record)
            return record
