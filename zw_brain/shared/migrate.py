from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from zw_brain.shared.db import get_database_url

REQUIRED_TABLES = {
    "runtime_state",
    "audit_event",
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
    "application_record",
    "approval_case",
    "approval_step",
    "approval_decision",
    "delivery_task",
    "objection_case",
    "objection_evidence",
    "objection_process",
    "objection_evaluation",
    "tenant_capability_policy",
}
REQUIRED_COLUMNS = {
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
    "service_invocation_metric_projection": {"provider_region_code", "consumer_region_code", "bucket_granularity", "provider_error_count", "consumer_error_count", "gateway_error_count", "other_error_count", "apply_count", "p95_latency_ms", "last_error_code", "last_error_at"},
    "legacy_object_mapping": {"mapping_status"},
    "approval_step": {"decision_mode", "started_at", "completed_at"},
    "approval_decision": {"decision_reason"},
    "delivery_receipt": {"receipt_no", "acknowledged_at"},
}


def _assets_root() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    packaged = package_root / "_assets"
    if packaged.exists():
        return packaged
    return package_root.parents[0]


def _alembic_ini() -> Path:
    return _assets_root() / "alembic.ini"


def _alembic_script_location() -> Path:
    return _assets_root() / "alembic"


def _config() -> Config:
    cfg = Config(str(_alembic_ini()))
    cfg.set_main_option("script_location", str(_alembic_script_location()))
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def upgrade() -> None:
    command.upgrade(_config(), "head")


def reset_and_upgrade() -> None:
    engine = create_engine(get_database_url(), future=True)
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table_name in inspector.get_table_names():
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    upgrade()


def ensure_runtime_schema() -> None:
    engine = create_engine(get_database_url(), future=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not REQUIRED_TABLES.issubset(tables):
        reset_and_upgrade()
        return
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if not required_columns.issubset(columns):
            reset_and_upgrade()
            return
