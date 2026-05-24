from __future__ import annotations

import uuid
from datetime import UTC, datetime

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


class CapabilityCallRecord(Base):
    __tablename__ = "capability_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_ref: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    role_code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    input_json: Mapped[dict] = mapped_column(JSON)
    output_json: Mapped[dict] = mapped_column(JSON)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    runtime_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
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


class ExternalObjectMappingRecord(Base):
    __tablename__ = "external_object_mapping"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_system",
            "direction",
            "local_aggregate_type",
            "local_aggregate_id",
            "external_object_type",
            "external_object_id",
            name="uq_external_object_mapping_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    external_system: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(32), index=True)
    local_aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    local_aggregate_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    legacy_table: Mapped[str | None] = mapped_column(String(128), nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_object_type: Mapped[str] = mapped_column(String(128), index=True)
    external_object_id: Mapped[str] = mapped_column(String(128), index=True)
    protocol_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    last_receipt_json: Mapped[dict] = mapped_column(JSON)
    extra_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, index=True)


class AdapterRunRecord(Base):
    __tablename__ = "adapter_run_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "adapter_slug",
            "operation",
            "idempotency_key",
            name="uq_adapter_run_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    adapter_slug: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(32), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    receipt_json: Mapped[dict] = mapped_column(JSON)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


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


class DeliverySubscriptionRecord(Base):
    __tablename__ = "delivery_subscription"
    __table_args__ = (UniqueConstraint("tenant_id", "subscription_code", name="uq_delivery_subscription_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    subscription_code: Mapped[str] = mapped_column(String(64), index=True)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    schedule_ref_json: Mapped[dict] = mapped_column(JSON)
    policy_snapshot_json: Mapped[dict] = mapped_column(JSON)
    legacy_status_snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeliveryAttemptRecord(Base):
    __tablename__ = "delivery_attempt"
    __table_args__ = (UniqueConstraint("tenant_id", "attempt_code", name="uq_delivery_attempt_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    attempt_code: Mapped[str] = mapped_column(String(96), index=True)
    delivery_code: Mapped[str] = mapped_column(String(64), index=True)
    subscription_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_kind: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    executor_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class DeliveryExecutionEvidenceRecord(Base):
    __tablename__ = "delivery_execution_evidence"
    __table_args__ = (UniqueConstraint("tenant_id", "evidence_ref", name="uq_delivery_execution_evidence_tenant_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    evidence_ref: Mapped[str] = mapped_column(String(128), index=True)
    delivery_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_code: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    executor_kind: Mapped[str] = mapped_column(String(64), index=True)
    executor_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_kind: Mapped[str] = mapped_column(String(64), index=True)
    result_status: Mapped[str] = mapped_column(String(32), index=True)
    sanitized_payload_json: Mapped[dict] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ExchangeMetricProjectionRecord(Base):
    __tablename__ = "exchange_metric_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "metric_scope",
            "resource_code",
            "delivery_code",
            "subscription_code",
            "provider_org_id",
            "consumer_org_id",
            "bucket_granularity",
            "time_bucket",
            name="uq_exchange_metric_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_scope: Mapped[str] = mapped_column(String(64), index=True)
    resource_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    delivery_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subscription_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provider_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    consumer_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    bucket_granularity: Mapped[str] = mapped_column(String(32), index=True)
    time_bucket: Mapped[str] = mapped_column(String(32), index=True)
    exchange_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    table_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


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


class TenantProjectionRecord(Base):
    __tablename__ = "tenant_projection"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_projection_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class OrgProjectionRecord(Base):
    __tablename__ = "org_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "org_code", name="uq_org_projection_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    org_code: Mapped[str] = mapped_column(String(64), index=True)
    org_name: Mapped[str] = mapped_column(String(200))
    parent_org_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RegionProjectionRecord(Base):
    __tablename__ = "region_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "region_code", name="uq_region_projection_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    region_code: Mapped[str] = mapped_column(String(64), index=True)
    region_name: Mapped[str] = mapped_column(String(200))
    parent_region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    region_level: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RoleProjectionRecord(Base):
    __tablename__ = "role_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "role_code", name="uq_role_projection_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    role_code: Mapped[str] = mapped_column(String(64), index=True)
    role_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ActorProjectionRecord(Base):
    __tablename__ = "actor_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "external_actor_id", name="uq_actor_projection_tenant_external"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    external_actor_id: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    org_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role_codes_json: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ActorOrgRoleBindingRecord(Base):
    __tablename__ = "actor_org_role_binding"
    __table_args__ = (UniqueConstraint("tenant_id", "external_actor_id", "org_code", "role_code", name="uq_actor_org_role_binding_identity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    external_actor_id: Mapped[str] = mapped_column(String(128), index=True)
    org_code: Mapped[str] = mapped_column(String(64), index=True)
    role_code: Mapped[str] = mapped_column(String(64), index=True)
    binding_status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    tags_json: Mapped[dict] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    granted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_priority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class LegacyPolicyMappingCandidateRecord(Base):
    __tablename__ = "legacy_policy_mapping_candidate"
    __table_args__ = (UniqueConstraint("tenant_id", "legacy_system", "legacy_permission_ref", "capability_id", name="uq_legacy_policy_candidate_identity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    legacy_system: Mapped[str] = mapped_column(String(64), index=True)
    legacy_permission_ref: Mapped[str] = mapped_column(String(128), index=True)
    legacy_role_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    capability_id: Mapped[str] = mapped_column(String(128), index=True)
    surface: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    candidate_status: Mapped[str] = mapped_column(String(32), index=True, default="pending_review")
    evidence_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TopicPackageRecord(Base):
    __tablename__ = "topic_package"
    __table_args__ = (UniqueConstraint("tenant_id", "package_code", name="uq_topic_package_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(200))
    scenario: Mapped[str] = mapped_column(String(200), index=True, default="一表通 / 基层报表减负")
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    owner_org_snapshot_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    display_snapshot_json: Mapped[dict] = mapped_column(JSON)
    metric_snapshot_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TopicPackageItemRecord(Base):
    __tablename__ = "topic_package_item"
    __table_args__ = (UniqueConstraint("tenant_id", "package_code", "item_code", name="uq_topic_package_item_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    item_code: Mapped[str] = mapped_column(String(128), index=True)
    ref_type: Mapped[str] = mapped_column(String(64), index=True)
    ref_id: Mapped[str] = mapped_column(String(128), index=True)
    ref_status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    title: Mapped[str] = mapped_column(String(200))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TopicPackageVisibilityRecord(Base):
    __tablename__ = "topic_package_visibility"
    __table_args__ = (UniqueConstraint("tenant_id", "package_code", "visibility_code", name="uq_topic_visibility_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    visibility_code: Mapped[str] = mapped_column(String(128), index=True)
    org_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    region_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    surface: Mapped[str] = mapped_column(String(32), index=True, default="webui")
    intent: Mapped[str] = mapped_column(String(64), index=True, default="view")
    policy_status: Mapped[str] = mapped_column(String(32), index=True, default="pending_review")
    condition_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TopicPackageReviewRecord(Base):
    __tablename__ = "topic_package_review_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    action_result: Mapped[str] = mapped_column(String(32), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), index=True)
    reviewer_snapshot_json: Mapped[dict] = mapped_column(JSON)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TopicPackageEvidenceRecord(Base):
    __tablename__ = "topic_package_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    related_ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    related_ref_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    content_json: Mapped[dict] = mapped_column(JSON)
    submitted_by_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TopicPackageMetricProjectionRecord(Base):
    __tablename__ = "topic_package_metric_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "package_code", "metric_key", name="uq_topic_metric_tenant_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    package_code: Mapped[str] = mapped_column(String(128), index=True)
    metric_key: Mapped[str] = mapped_column(String(128), index=True)
    metric_value: Mapped[int] = mapped_column(Integer, default=0)
    metric_json: Mapped[dict] = mapped_column(JSON)
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


class ComplianceCaseRecord(Base):
    __tablename__ = "compliance_case"
    __table_args__ = (UniqueConstraint("tenant_id", "case_code", name="uq_compliance_case_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    case_code: Mapped[str] = mapped_column(String(64), index=True)
    case_kind: Mapped[str] = mapped_column(String(32), index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_ref: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True, default="medium")
    status: Mapped[str] = mapped_column(String(32), index=True, default="detected")
    assignee_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assignee_snapshot_json: Mapped[dict] = mapped_column(JSON)
    detected_summary: Mapped[str] = mapped_column(Text)
    resolved_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ComplianceRuleRecord(Base):
    __tablename__ = "compliance_rule"
    __table_args__ = (UniqueConstraint("tenant_id", "rule_code", name="uq_compliance_rule_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_kind: Mapped[str] = mapped_column(String(32), index=True)
    target_scope: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    threshold_json: Mapped[dict] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(32), index=True, default="pending_review")
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RiskEventProjectionRecord(Base):
    __tablename__ = "risk_event_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_system",
            "source_ref",
            name="uq_risk_event_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    event_kind: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True, default="medium")
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    source_ref: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    target_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    summary_json: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class HealthSignalProjectionRecord(Base):
    __tablename__ = "health_signal_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_kind",
            "subject_ref",
            name="uq_health_signal_subject",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    subject_kind: Mapped[str] = mapped_column(String(32), index=True)
    subject_ref: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="unknown")
    metric_json: Mapped[dict] = mapped_column(JSON)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class StandardAssetProjectionRecord(Base):
    __tablename__ = "standard_asset_projection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "asset_kind",
            "asset_ref",
            name="uq_standard_asset_kind_ref",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    asset_kind: Mapped[str] = mapped_column(String(32), index=True)
    asset_ref: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), index=True, default="candidate")
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class MetricDefinitionProjectionRecord(Base):
    __tablename__ = "metric_definition_projection"
    __table_args__ = (UniqueConstraint("tenant_id", "metric_code", name="uq_metric_definition_tenant_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    metric_kind: Mapped[str] = mapped_column(String(32), index=True)
    target_aggregate: Mapped[str] = mapped_column(String(64), index=True)
    dimension_json: Mapped[dict] = mapped_column(JSON)
    formula_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------------------------------------------------------------------
# E3 Wave-2 三引擎 — F1 审批流模板（schema / node / selection_rule / branch）
# 运行态 ApprovalCase* 不变；这一组是「模板/定义层」，由
# ApprovalFlowSchemaRepo 配 draft→preview→live 状态机使用。
# ---------------------------------------------------------------------------


class ApprovalFlowSchemaRecord(Base):
    __tablename__ = "approval_flow_schema"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "schema_code",
            "version",
            name="uq_approval_flow_schema_tenant_code_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), index=True, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    draft_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApprovalFlowNodeRecord(Base):
    __tablename__ = "approval_flow_node"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(String(36), index=True)
    node_code: Mapped[str] = mapped_column(String(64), index=True)
    node_name: Mapped[str] = mapped_column(String(200))
    node_type: Mapped[str] = mapped_column(String(32), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    selection_rule_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ApprovalFlowSelectionRuleRecord(Base):
    __tablename__ = "approval_flow_selection_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(String(36), index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_kind: Mapped[str] = mapped_column(String(32), index=True)
    rule_payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ApprovalFlowBranchRecord(Base):
    __tablename__ = "approval_flow_branch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schema_id: Mapped[str] = mapped_column(String(36), index=True)
    from_node_code: Mapped[str] = mapped_column(String(64), index=True)
    to_node_code: Mapped[str] = mapped_column(String(64), index=True)
    condition_kind: Mapped[str] = mapped_column(String(32), index=True, default="always")
    condition_payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------
# E3 Wave-2 三引擎 — F4 表单 schema 化（schema / section / field / validator）
# 与 ApprovalFlow* 同形：模板/定义层，配 FormSchemaRepo 走 draft→preview→live。
# 业务运行态表单实例（J1/J2 提交）不在本组；本组只承接结构契约。
# ---------------------------------------------------------------------------


class FormSchemaRecord(Base):
    __tablename__ = "form_schema"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "form_code",
            "version",
            name="uq_form_schema_tenant_code_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    form_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), index=True, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    draft_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FormSectionRecord(Base):
    __tablename__ = "form_section"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    form_schema_id: Mapped[str] = mapped_column(String(36), index=True)
    section_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    collapsible: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FormFieldRecord(Base):
    __tablename__ = "form_field"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    form_schema_id: Mapped[str] = mapped_column(String(36), index=True)
    section_code: Mapped[str] = mapped_column(String(64), index=True)
    field_code: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(200))
    field_type: Mapped[str] = mapped_column(String(32), index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    placeholder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    layout_hints_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FormValidatorRecord(Base):
    __tablename__ = "form_validator"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    form_schema_id: Mapped[str] = mapped_column(String(36), index=True)
    validator_code: Mapped[str] = mapped_column(String(64), index=True)
    applies_to_field_code: Mapped[str] = mapped_column(String(64), index=True)
    validator_kind: Mapped[str] = mapped_column(String(32), index=True)
    validator_payload_json: Mapped[dict] = mapped_column(JSON)
    error_message_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------------
# E3 Wave-2 三引擎 — F6 智能推荐前置（rule / rule_clause / history / submission）
# 与 ApprovalFlow* / FormSchema* 同形：rule 走 draft→preview→live；
# RequirementHistory 是真实 dump-dsp_require 投影（fixture-fed），
# RequirementSubmission 是引擎跑后落地的「申请意向」（recommend pick 或 fallback 人工登记）。
# ---------------------------------------------------------------------------


class RecommendationRuleRecord(Base):
    __tablename__ = "recommendation_rule"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "rule_code",
            "version",
            name="uq_recommendation_rule_tenant_code_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), index=True, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    draft_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RecommendationRuleClauseRecord(Base):
    __tablename__ = "recommendation_rule_clause"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rule_id: Mapped[str] = mapped_column(String(36), index=True)
    clause_code: Mapped[str] = mapped_column(String(64), index=True)
    clause_kind: Mapped[str] = mapped_column(String(32), index=True)
    clause_payload_json: Mapped[dict] = mapped_column(JSON)
    weight: Mapped[float] = mapped_column(default=1.0)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RequirementHistoryRecord(Base):
    __tablename__ = "requirement_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source_require_id: Mapped[str] = mapped_column(String(64), index=True)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RequirementSubmissionRecord(Base):
    __tablename__ = "requirement_submission"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    submitted_by: Mapped[str] = mapped_column(String(128))
    intent_text: Mapped[str] = mapped_column(Text)
    submission_kind: Mapped[str] = mapped_column(String(32), index=True)
    target_catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recommendation_audit_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
