from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from zw_brain.domain.models import Base
from zw_brain.shared.db import get_database_url

# v4.1 R15：alembic 删除；schema 用 SQLAlchemy Base.metadata 管理（drop_all + create_all）。
# REQUIRED_TABLES / REQUIRED_COLUMNS 保留为运行时自检清单（独立于 Base 的反射式校验）。

REQUIRED_TABLES = {
    "runtime_state",
    "audit_event",
    "capability_call",
    "anchor_outbox",
    "audit_receipt",
    "capability_manifest",
    "catalog_model",
    "catalog_model_field",
    "catalog_entry",
    "catalog_entry_version",
    "catalog_item",
    "resource_asset",
    "resource_channel_binding",
    "resource_schema_mapping",
    "resource_schema_snapshot",
    "metadata_gather_evidence_projection",
    "lineage_relation_projection",
    "quality_evidence_projection",
    "resource_api_test_projection",
    "gateway_runtime_status_projection",
    "service_invocation_metric_projection",
    "legacy_object_mapping",
    "external_object_mapping",
    "adapter_run_record",
    "tenant_projection",
    "org_projection",
    "region_projection",
    "role_projection",
    "actor_projection",
    "actor_org_role_binding",
    "legacy_policy_mapping_candidate",
    "topic_package",
    "topic_package_item",
    "topic_package_visibility",
    "topic_package_review_record",
    "topic_package_evidence",
    "topic_package_metric_projection",
    "application_record",
    "approval_case",
    "approval_step",
    "approval_decision",
    "delivery_task",
    "delivery_receipt",
    "delivery_subscription",
    "delivery_attempt",
    "delivery_execution_evidence",
    "exchange_metric_projection",
    "objection_case",
    "objection_evidence",
    "objection_process",
    "objection_evaluation",
    "capability_package",
    "tenant_capability_policy",
}
REQUIRED_COLUMNS = {
    "capability_call": {"call_ref", "tenant_id", "skill_id", "role_code", "status", "input_json", "output_json"},
    "catalog_model": {"model_code", "model_schema_json"},
    "catalog_model_field": {"model_code", "field_code", "field_policy_json"},
    "catalog_entry": {"region_code"},
    "catalog_entry_version": {"catalog_code", "version_no", "snapshot_json"},
    "catalog_item": {"item_code", "catalog_code", "resource_code", "item_kind"},
    "resource_asset": {"owner_org_snapshot_json", "region_code", "access_policy_json", "qos_policy_json"},
    "resource_channel_binding": {"endpoint_ref", "schema_ref"},
    "resource_schema_mapping": {"catalog_item_code", "source_schema_ref", "mapping_rule_json", "confidence_level"},
    "resource_schema_snapshot": {"snapshot_ref", "schema_json", "schema_hash"},
    "metadata_gather_evidence_projection": {"gather_task_ref", "schema_snapshot_ref", "error_summary"},
    "lineage_relation_projection": {"relation_ref", "relation_scope", "relation_rule_json"},
    "quality_evidence_projection": {"quality_ref", "quality_status", "evidence_json"},
    "gateway_runtime_status_projection": {"runtime_profile"},
    "service_invocation_metric_projection": {"provider_region_code", "consumer_region_code", "bucket_granularity", "provider_error_count", "consumer_error_count", "gateway_error_count", "other_error_count", "apply_count", "p95_latency_ms", "last_error_code", "last_error_at", "failed_count"},
    "legacy_object_mapping": {"mapping_status"},
    "external_object_mapping": {"external_system", "direction", "local_aggregate_type", "external_object_id", "last_receipt_json"},
    "adapter_run_record": {"adapter_slug", "operation", "idempotency_key", "receipt_json", "status"},
    "tenant_projection": {"tenant_id", "tenant_name", "status", "profile_json"},
    "org_projection": {"tenant_id", "org_code", "org_name", "region_code", "profile_json"},
    "actor_projection": {"tenant_id", "external_actor_id", "display_name", "role_codes_json"},
    "actor_org_role_binding": {
        "tenant_id",
        "external_actor_id",
        "org_code",
        "role_code",
        "binding_status",
        "tags_json",
        "valid_from",
        "valid_to",
        "granted_by",
        "batch_no",
        "source_priority",
        "evidence_json",
    },
    "legacy_policy_mapping_candidate": {"legacy_system", "legacy_permission_ref", "capability_id", "candidate_status"},
    "topic_package": {"package_code", "title", "scenario", "status", "display_snapshot_json"},
    "topic_package_item": {"package_code", "item_code", "ref_type", "ref_id"},
    "topic_package_visibility": {"package_code", "visibility_code", "policy_status", "condition_json"},
    "topic_package_review_record": {"package_code", "action_type", "action_result", "to_status"},
    "topic_package_evidence": {"package_code", "evidence_type", "content_json"},
    "topic_package_metric_projection": {"package_code", "metric_key", "metric_value", "metric_json"},
    "approval_step": {"decision_mode", "started_at", "completed_at"},
    "approval_decision": {"decision_reason"},
    "delivery_receipt": {"receipt_no", "acknowledged_at"},
    "delivery_subscription": {"subscription_code", "delivery_code", "resource_code", "schedule_ref_json", "policy_snapshot_json"},
    "delivery_attempt": {"attempt_code", "delivery_code", "attempt_kind", "state", "payload_json"},
    "delivery_execution_evidence": {"evidence_ref", "delivery_code", "attempt_code", "result_status", "sanitized_payload_json"},
    "exchange_metric_projection": {"metric_scope", "delivery_code", "exchange_count", "success_count", "failed_count", "summary_json"},
}


def upgrade() -> None:
    """Create all tables defined on Base.metadata. v4.1 R15: replaces alembic upgrade."""
    engine = create_engine(get_database_url(), future=True)
    Base.metadata.create_all(bind=engine)


def reset_and_upgrade() -> None:
    """Drop all existing tables and recreate from Base.metadata. v4.1 R15: drop & recreate."""
    engine = create_engine(get_database_url(), future=True)
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table_name in inspector.get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    engine.dispose()
    upgrade()


def ensure_runtime_schema() -> None:
    """Verify required tables/columns exist; reset if not (drop & recreate)."""
    engine = create_engine(get_database_url(), future=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not REQUIRED_TABLES.issubset(tables):
        engine.dispose()
        reset_and_upgrade()
        return
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not required_columns.issubset(columns):
            engine.dispose()
            reset_and_upgrade()
            return
    engine.dispose()
