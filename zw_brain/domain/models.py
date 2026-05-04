from __future__ import annotations

from datetime import UTC, datetime
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from zw_brain.shared.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class RuntimeStateRecord(Base):
    __tablename__ = "runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    ui_state_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AuditEventRecord(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    phase: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class AnchorOutboxRecord(Base):
    __tablename__ = "anchor_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), unique=True)
    chain_id: Mapped[str] = mapped_column(String(64), default="mock-chain")
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditReceiptRecord(Base):
    __tablename__ = "audit_receipt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    chain_id: Mapped[str] = mapped_column(String(64), index=True)
    tx_hash: Mapped[str] = mapped_column(String(128), index=True)
    block_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_json: Mapped[dict] = mapped_column(JSON)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CapabilityManifestRecord(Base):
    __tablename__ = "capability_manifest"

    skill_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    registry_source: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CatalogModelRecord(Base):
    __tablename__ = "catalog_model"
    __table_args__ = (UniqueConstraint("tenant_id", "model_code", name="uq_catalog_model_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_schema_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CatalogModelFieldRecord(Base):
    __tablename__ = "catalog_model_field"
    __table_args__ = (UniqueConstraint("tenant_id", "model_code", "field_code", name="uq_catalog_model_field_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_code: Mapped[str] = mapped_column(String(64), index=True)
    field_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    data_type: Mapped[str] = mapped_column(String(64), default="string")
    sensitive_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field_policy_json: Mapped[dict] = mapped_column(JSON)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CatalogEntryRecord(Base):
    __tablename__ = "catalog_entry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    catalog_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    lifecycle_status: Mapped[str] = mapped_column(String(32), index=True)
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CatalogEntryVersionRecord(Base):
    __tablename__ = "catalog_entry_version"
    __table_args__ = (UniqueConstraint("tenant_id", "catalog_code", "version_no", name="uq_catalog_entry_version_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    catalog_code: Mapped[str] = mapped_column(String(64), index=True)
    version_no: Mapped[str] = mapped_column(String(64))
    version_status: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    audit_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CatalogItemRecord(Base):
    __tablename__ = "catalog_item"
    __table_args__ = (UniqueConstraint("tenant_id", "item_code", name="uq_catalog_item_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    item_code: Mapped[str] = mapped_column(String(64), index=True)
    catalog_code: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    item_kind: Mapped[str] = mapped_column(String(32), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResourceAssetRecord(Base):
    __tablename__ = "resource_asset"
    __table_args__ = (UniqueConstraint("tenant_id", "resource_code", name="uq_resource_asset_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    resource_kind: Mapped[str] = mapped_column(String(32), index=True, default="api")
    title: Mapped[str] = mapped_column(String(200))
    lifecycle_status: Mapped[str] = mapped_column(String(32), index=True)
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_org_snapshot_json: Mapped[dict] = mapped_column(JSON)
    region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    catalog_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_policy_json: Mapped[dict] = mapped_column(JSON)
    qos_policy_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResourceChannelBindingRecord(Base):
    __tablename__ = "resource_channel_binding"
    __table_args__ = (UniqueConstraint("tenant_id", "binding_code", name="uq_resource_channel_binding_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    binding_code: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    channel_kind: Mapped[str] = mapped_column(String(64))
    route_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint_ref: Mapped[dict] = mapped_column(JSON)
    schema_ref: Mapped[dict] = mapped_column(JSON)
    auth_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_schema_json: Mapped[dict] = mapped_column(JSON)
    response_schema_json: Mapped[dict] = mapped_column(JSON)
    gateway_policy_json: Mapped[dict] = mapped_column(JSON)
    lifecycle_status: Mapped[str] = mapped_column(String(32), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResourceSchemaMappingRecord(Base):
    __tablename__ = "resource_schema_mapping"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "catalog_item_code",
            "resource_code",
            "binding_code",
            "status",
            name="uq_resource_schema_mapping_current",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    mapping_code: Mapped[str] = mapped_column(String(128), index=True)
    catalog_code: Mapped[str] = mapped_column(String(64), index=True)
    catalog_item_code: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    binding_code: Mapped[str] = mapped_column(String(64), index=True)
    source_schema_ref: Mapped[dict] = mapped_column(JSON)
    mapping_rule_json: Mapped[dict] = mapped_column(JSON)
    confidence_level: Mapped[str] = mapped_column(String(32), index=True, default="confirmed")
    evidence_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResourceSchemaSnapshotRecord(Base):
    __tablename__ = "resource_schema_snapshot"
    __table_args__ = (UniqueConstraint("tenant_id", "snapshot_ref", name="uq_resource_schema_snapshot_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_ref: Mapped[str] = mapped_column(String(128), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    binding_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    schema_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_hash: Mapped[str] = mapped_column(String(128), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class MetadataGatherEvidenceProjectionRecord(Base):
    __tablename__ = "metadata_gather_evidence_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "gather_task_ref", name="uq_metadata_gather_tenant_task"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    gather_task_ref: Mapped[str] = mapped_column(String(128), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    source_system_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_snapshot_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class LineageRelationProjectionRecord(Base):
    __tablename__ = "lineage_relation_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "relation_ref", name="uq_lineage_relation_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    relation_ref: Mapped[str] = mapped_column(String(128), index=True)
    relation_scope: Mapped[str] = mapped_column(String(32), index=True)
    source_resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_schema_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_schema_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(64), index=True)
    relation_rule_json: Mapped[dict] = mapped_column(JSON)
    source_evidence_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class QualityEvidenceProjectionRecord(Base):
    __tablename__ = "quality_evidence_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "quality_ref", name="uq_quality_evidence_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    quality_ref: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_ref: Mapped[str] = mapped_column(String(128), index=True)
    quality_status: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class ResourceApiTestProjectionRecord(Base):
    __tablename__ = "resource_api_test_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "test_ref", name="uq_resource_api_test_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    test_ref: Mapped[str] = mapped_column(String(128), index=True)
    resource_code: Mapped[str] = mapped_column(String(64), index=True)
    binding_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    test_result: Mapped[str] = mapped_column(String(32), index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    tested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tested_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class GatewayRuntimeStatusProjectionRecord(Base):
    __tablename__ = "gateway_runtime_status_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "gateway_instance_id", name="uq_gateway_runtime_tenant_instance"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    gateway_instance_id: Mapped[str] = mapped_column(String(128), index=True)
    gateway_address_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class ServiceInvocationMetricProjectionRecord(Base):
    __tablename__ = "service_invocation_metric_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "metric_scope",
            "resource_code",
            "capability_id",
            "provider_org_id",
            "consumer_org_id",
            "provider_region_code",
            "consumer_region_code",
            "bucket_granularity",
            "time_bucket",
            name="uq_service_invocation_metric_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_scope: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    capability_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    consumer_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    consumer_region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    consumer_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consumer_app_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bucket_granularity: Mapped[str] = mapped_column(String(32), default="day", index=True)
    time_bucket: Mapped[str] = mapped_column(String(32), index=True)
    invoke_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    provider_error_count: Mapped[int] = mapped_column(Integer, default=0)
    consumer_error_count: Mapped[int] = mapped_column(Integer, default=0)
    gateway_error_count: Mapped[int] = mapped_column(Integer, default=0)
    other_error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    apply_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p95_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_event_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class LegacyObjectMappingRecord(Base):
    __tablename__ = "legacy_object_mapping"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "legacy_system",
            "legacy_object_type",
            "legacy_object_ref",
            "canonical_type",
            "canonical_ref",
            name="uq_legacy_object_mapping_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_system: Mapped[str] = mapped_column(String(64), index=True)
    legacy_object_type: Mapped[str] = mapped_column(String(128), index=True)
    legacy_object_ref: Mapped[str] = mapped_column(String(255), index=True)
    canonical_type: Mapped[str] = mapped_column(String(128), index=True)
    canonical_ref: Mapped[str] = mapped_column(String(255), index=True)
    source_ref: Mapped[str] = mapped_column(String(255), index=True)
    mapping_status: Mapped[str] = mapped_column(String(32), default="mapped", index=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    mapped_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class ApplicationRecord(Base):
    __tablename__ = "application_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    application_code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    applicant_name: Mapped[str] = mapped_column(String(128))
    applicant_org: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[dict] = mapped_column(JSON)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApprovalCaseRecord(Base):
    __tablename__ = "approval_case"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    application_code: Mapped[str] = mapped_column(String(64), index=True)
    current_status: Mapped[str] = mapped_column(String(32), index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    decision_payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApprovalStepRecord(Base):
    __tablename__ = "approval_step"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    approval_case_id: Mapped[str] = mapped_column(String(36), index=True)
    step_no: Mapped[int] = mapped_column(Integer, default=1)
    step_name: Mapped[str] = mapped_column(String(128))
    decision_mode: Mapped[str] = mapped_column(String(32), default="single")
    status: Mapped[str] = mapped_column(String(32), index=True)
    approver_scope_json: Mapped[dict] = mapped_column(JSON)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ApprovalDecisionRecord(Base):
    __tablename__ = "approval_decision"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    step_id: Mapped[str] = mapped_column(String(36), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_snapshot_json: Mapped[dict] = mapped_column(JSON)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DeliveryTaskRecord(Base):
    __tablename__ = "delivery_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)
    application_code: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    channel: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeliveryReceiptRecord(Base):
    __tablename__ = "delivery_receipt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)
    receipt_type: Mapped[str] = mapped_column(String(32), index=True)
    receipt_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    receipt_status: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CapabilityPackageRecord(Base):
    __tablename__ = "capability_package"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    package_slug: Mapped[str] = mapped_column(String(128), index=True)
    review_status: Mapped[str] = mapped_column(String(32), index=True)
    source_org: Mapped[str] = mapped_column(String(128))
    manifest_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TenantCapabilityPolicyRecord(Base):
    __tablename__ = "tenant_capability_policy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_slug: Mapped[str] = mapped_column(String(128), index=True)
    policy_status: Mapped[str] = mapped_column(String(32), index=True)
    policy_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ObjectionCaseRecord(Base):
    __tablename__ = "objection_case"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    objection_kind: Mapped[str] = mapped_column(String(32), index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    related_application_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    complainant_org_id: Mapped[str] = mapped_column(String(64))
    complainant_org_snapshot_json: Mapped[dict] = mapped_column(JSON)
    provider_org_id: Mapped[str] = mapped_column(String(64))
    provider_org_snapshot_json: Mapped[dict] = mapped_column(JSON)
    basis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    resolved_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)


class ObjectionEvidenceRecord(Base):
    __tablename__ = "objection_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    objection_id: Mapped[str] = mapped_column(String(36), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    content_json: Mapped[dict] = mapped_column(JSON)
    submitted_by_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ObjectionProcessRecord(Base):
    __tablename__ = "objection_process"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    objection_id: Mapped[str] = mapped_column(String(36), index=True)
    node_name: Mapped[str] = mapped_column(String(128))
    handler_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handler_snapshot_json: Mapped[dict] = mapped_column(JSON)
    action_type: Mapped[str] = mapped_column(String(32))
    action_result: Mapped[str] = mapped_column(String(32))
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ObjectionEvaluationRecord(Base):
    __tablename__ = "objection_evaluation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    objection_id: Mapped[str] = mapped_column(String(36), index=True)
    evaluator_snapshot_json: Mapped[dict] = mapped_column(JSON)
    solved_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeliness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
