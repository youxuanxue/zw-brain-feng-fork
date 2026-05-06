"""bootstrap runtime, audit, outbox, core aggregates, and capability registry tables

Revision ID: 0001_runtime_bootstrap
Revises:
Create Date: 2026-04-27 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_runtime_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("ui_state_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_event_request_id", "audit_event", ["request_id"])
    op.create_index("ix_audit_event_skill_id", "audit_event", ["skill_id"])
    op.create_index("ix_audit_event_occurred_at", "audit_event", ["occurred_at"])
    op.create_table(
        "anchor_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_anchor_outbox_request_id", "anchor_outbox", ["request_id"])
    op.create_index("ix_anchor_outbox_skill_id", "anchor_outbox", ["skill_id"])
    op.create_index("ix_anchor_outbox_delivered", "anchor_outbox", ["delivered"])
    op.create_table(
        "audit_receipt",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("tx_hash", sa.String(length=128), nullable=False),
        sa.Column("block_height", sa.Integer(), nullable=True),
        sa.Column("receipt_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_receipt_request_id", "audit_receipt", ["request_id"])
    op.create_index("ix_audit_receipt_skill_id", "audit_receipt", ["skill_id"])
    op.create_index("ix_audit_receipt_content_hash", "audit_receipt", ["content_hash"])
    op.create_index("ix_audit_receipt_chain_id", "audit_receipt", ["chain_id"])
    op.create_index("ix_audit_receipt_tx_hash", "audit_receipt", ["tx_hash"])
    op.create_index("ix_audit_receipt_confirmed_at", "audit_receipt", ["confirmed_at"])
    op.create_table(
        "capability_manifest",
        sa.Column("skill_id", sa.String(length=128), primary_key=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("registry_source", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "catalog_entry",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("catalog_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("region_code", sa.String(length=64), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_catalog_entry_tenant_id", "catalog_entry", ["tenant_id"])
    op.create_index("ix_catalog_entry_catalog_code", "catalog_entry", ["catalog_code"])
    op.create_index("ix_catalog_entry_lifecycle_status", "catalog_entry", ["lifecycle_status"])
    op.create_index("ix_catalog_entry_region_code", "catalog_entry", ["region_code"])
    op.create_table(
        "catalog_item",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=False),
        sa.Column("catalog_code", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("item_kind", sa.String(length=32), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "item_code", name="uq_catalog_item_tenant_code"),
    )
    op.create_index("ix_catalog_item_tenant_id", "catalog_item", ["tenant_id"])
    op.create_index("ix_catalog_item_item_code", "catalog_item", ["item_code"])
    op.create_index("ix_catalog_item_catalog_code", "catalog_item", ["catalog_code"])
    op.create_index("ix_catalog_item_resource_code", "catalog_item", ["resource_code"])
    op.create_index("ix_catalog_item_item_kind", "catalog_item", ["item_kind"])
    op.create_table(
        "resource_asset",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("resource_kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("owner_org_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("region_code", sa.String(length=64), nullable=True),
        sa.Column("catalog_code", sa.String(length=64), nullable=True),
        sa.Column("access_policy_json", sa.JSON(), nullable=False),
        sa.Column("qos_policy_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "resource_code", name="uq_resource_asset_tenant_code"),
    )
    op.create_index("ix_resource_asset_tenant_id", "resource_asset", ["tenant_id"])
    op.create_index("ix_resource_asset_resource_code", "resource_asset", ["resource_code"])
    op.create_index("ix_resource_asset_resource_kind", "resource_asset", ["resource_kind"])
    op.create_index("ix_resource_asset_lifecycle_status", "resource_asset", ["lifecycle_status"])
    op.create_index("ix_resource_asset_region_code", "resource_asset", ["region_code"])
    op.create_table(
        "resource_channel_binding",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("binding_code", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("channel_kind", sa.String(length=64), nullable=False),
        sa.Column("route_ref", sa.String(length=255), nullable=True),
        sa.Column("endpoint_ref", sa.JSON(), nullable=False),
        sa.Column("schema_ref", sa.JSON(), nullable=False),
        sa.Column("auth_ref", sa.String(length=128), nullable=True),
        sa.Column("request_schema_json", sa.JSON(), nullable=False),
        sa.Column("response_schema_json", sa.JSON(), nullable=False),
        sa.Column("gateway_policy_json", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "binding_code", name="uq_resource_channel_binding_tenant_code"),
    )
    op.create_index("ix_resource_channel_binding_tenant_id", "resource_channel_binding", ["tenant_id"])
    op.create_index("ix_resource_channel_binding_binding_code", "resource_channel_binding", ["binding_code"])
    op.create_index("ix_resource_channel_binding_resource_code", "resource_channel_binding", ["resource_code"])
    op.create_index("ix_resource_channel_binding_lifecycle_status", "resource_channel_binding", ["lifecycle_status"])
    op.create_table(
        "resource_api_test_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("test_ref", sa.String(length=128), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("binding_code", sa.String(length=64), nullable=True),
        sa.Column("test_result", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("tested_by", sa.String(length=128), nullable=True),
        sa.Column("tested_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "test_ref", name="uq_resource_api_test_tenant_ref"),
    )
    op.create_index("ix_resource_api_test_projection_tenant_id", "resource_api_test_projection", ["tenant_id"])
    op.create_index("ix_resource_api_test_projection_test_ref", "resource_api_test_projection", ["test_ref"])
    op.create_index("ix_resource_api_test_projection_resource_code", "resource_api_test_projection", ["resource_code"])
    op.create_index("ix_resource_api_test_projection_binding_code", "resource_api_test_projection", ["binding_code"])
    op.create_index("ix_resource_api_test_projection_test_result", "resource_api_test_projection", ["test_result"])
    op.create_index("ix_resource_api_test_projection_lifecycle_status", "resource_api_test_projection", ["lifecycle_status"])
    op.create_index("ix_resource_api_test_projection_tested_at", "resource_api_test_projection", ["tested_at"])
    op.create_table(
        "gateway_runtime_status_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("gateway_instance_id", sa.String(length=128), nullable=False),
        sa.Column("gateway_address_ref", sa.String(length=128), nullable=True),
        sa.Column("runtime_profile", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_reported_at", sa.DateTime(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "gateway_instance_id", name="uq_gateway_runtime_tenant_instance"),
    )
    op.create_index("ix_gateway_runtime_status_projection_tenant_id", "gateway_runtime_status_projection", ["tenant_id"])
    op.create_index("ix_gateway_runtime_status_projection_gateway_instance_id", "gateway_runtime_status_projection", ["gateway_instance_id"])
    op.create_index("ix_gateway_runtime_status_projection_status", "gateway_runtime_status_projection", ["status"])
    op.create_index("ix_gateway_runtime_status_projection_last_reported_at", "gateway_runtime_status_projection", ["last_reported_at"])
    op.create_index("ix_gateway_runtime_status_projection_generated_at", "gateway_runtime_status_projection", ["generated_at"])
    op.create_table(
        "service_invocation_metric_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("metric_scope", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=True),
        sa.Column("capability_id", sa.String(length=128), nullable=True),
        sa.Column("provider_org_id", sa.String(length=64), nullable=True),
        sa.Column("consumer_org_id", sa.String(length=64), nullable=True),
        sa.Column("provider_region_code", sa.String(length=64), nullable=True),
        sa.Column("consumer_region_code", sa.String(length=64), nullable=True),
        sa.Column("consumer_region", sa.String(length=64), nullable=True),
        sa.Column("consumer_app_ref", sa.String(length=128), nullable=True),
        sa.Column("bucket_granularity", sa.String(length=32), nullable=False),
        sa.Column("time_bucket", sa.String(length=32), nullable=False),
        sa.Column("invoke_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("provider_error_count", sa.Integer(), nullable=False),
        sa.Column("consumer_error_count", sa.Integer(), nullable=False),
        sa.Column("gateway_error_count", sa.Integer(), nullable=False),
        sa.Column("other_error_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("apply_count", sa.Integer(), nullable=False),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=True),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("source_event_ref", sa.String(length=128), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
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
    op.create_index("ix_service_invocation_metric_projection_tenant_id", "service_invocation_metric_projection", ["tenant_id"])
    op.create_index("ix_service_invocation_metric_projection_metric_scope", "service_invocation_metric_projection", ["metric_scope"])
    op.create_index("ix_service_invocation_metric_projection_resource_code", "service_invocation_metric_projection", ["resource_code"])
    op.create_index("ix_service_invocation_metric_projection_capability_id", "service_invocation_metric_projection", ["capability_id"])
    op.create_index("ix_service_invocation_metric_projection_provider_org_id", "service_invocation_metric_projection", ["provider_org_id"])
    op.create_index("ix_service_invocation_metric_projection_consumer_org_id", "service_invocation_metric_projection", ["consumer_org_id"])
    op.create_index("ix_service_invocation_metric_projection_provider_region_code", "service_invocation_metric_projection", ["provider_region_code"])
    op.create_index("ix_service_invocation_metric_projection_consumer_region_code", "service_invocation_metric_projection", ["consumer_region_code"])
    op.create_index("ix_service_invocation_metric_projection_bucket_granularity", "service_invocation_metric_projection", ["bucket_granularity"])
    op.create_index("ix_service_invocation_metric_projection_time_bucket", "service_invocation_metric_projection", ["time_bucket"])
    op.create_index("ix_service_invocation_metric_projection_generated_at", "service_invocation_metric_projection", ["generated_at"])
    op.create_table(
        "legacy_object_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("legacy_system", sa.String(length=64), nullable=False),
        sa.Column("legacy_object_type", sa.String(length=128), nullable=False),
        sa.Column("legacy_object_ref", sa.String(length=255), nullable=False),
        sa.Column("canonical_type", sa.String(length=128), nullable=False),
        sa.Column("canonical_ref", sa.String(length=255), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("mapping_status", sa.String(length=32), nullable=False, server_default="mapped"),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("mapped_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "legacy_system",
            "legacy_object_type",
            "legacy_object_ref",
            "canonical_type",
            "canonical_ref",
            name="uq_legacy_object_mapping_identity",
        ),
    )
    op.create_index("ix_legacy_object_mapping_tenant_id", "legacy_object_mapping", ["tenant_id"])
    op.create_index("ix_legacy_object_mapping_legacy_system", "legacy_object_mapping", ["legacy_system"])
    op.create_index("ix_legacy_object_mapping_legacy_object_type", "legacy_object_mapping", ["legacy_object_type"])
    op.create_index("ix_legacy_object_mapping_legacy_object_ref", "legacy_object_mapping", ["legacy_object_ref"])
    op.create_index("ix_legacy_object_mapping_canonical_type", "legacy_object_mapping", ["canonical_type"])
    op.create_index("ix_legacy_object_mapping_canonical_ref", "legacy_object_mapping", ["canonical_ref"])
    op.create_index("ix_legacy_object_mapping_source_ref", "legacy_object_mapping", ["source_ref"])
    op.create_index("ix_legacy_object_mapping_mapping_status", "legacy_object_mapping", ["mapping_status"])
    op.create_index("ix_legacy_object_mapping_mapped_at", "legacy_object_mapping", ["mapped_at"])
    op.create_table(
        "application_record",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("application_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applicant_name", sa.String(length=128), nullable=False),
        sa.Column("applicant_org", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_application_record_tenant_id", "application_record", ["tenant_id"])
    op.create_index("ix_application_record_application_code", "application_record", ["application_code"])
    op.create_index("ix_application_record_status", "application_record", ["status"])
    op.create_table(
        "approval_case",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("application_code", sa.String(length=64), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("decision_payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_approval_case_tenant_id", "approval_case", ["tenant_id"])
    op.create_index("ix_approval_case_application_code", "approval_case", ["application_code"])
    op.create_index("ix_approval_case_current_status", "approval_case", ["current_status"])
    op.create_table(
        "approval_step",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("approval_case_id", sa.String(length=36), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=128), nullable=False),
        sa.Column("decision_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approver_scope_json", sa.JSON(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_approval_step_approval_case_id", "approval_step", ["approval_case_id"])
    op.create_index("ix_approval_step_status", "approval_step", ["status"])
    op.create_table(
        "approval_decision",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("step_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("actor_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_approval_decision_step_id", "approval_decision", ["step_id"])
    op.create_index("ix_approval_decision_decision", "approval_decision", ["decision"])
    op.create_table(
        "delivery_task",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("delivery_code", sa.String(length=64), nullable=False),
        sa.Column("application_code", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_delivery_task_tenant_id", "delivery_task", ["tenant_id"])
    op.create_index("ix_delivery_task_delivery_code", "delivery_task", ["delivery_code"])
    op.create_index("ix_delivery_task_application_code", "delivery_task", ["application_code"])
    op.create_index("ix_delivery_task_state", "delivery_task", ["state"])
    op.create_table(
        "delivery_receipt",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("delivery_code", sa.String(length=64), nullable=False),
        sa.Column("receipt_type", sa.String(length=32), nullable=False),
        sa.Column("receipt_no", sa.String(length=128), nullable=True),
        sa.Column("receipt_status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_delivery_receipt_delivery_code", "delivery_receipt", ["delivery_code"])
    op.create_index("ix_delivery_receipt_receipt_status", "delivery_receipt", ["receipt_status"])
    op.create_table(
        "capability_package",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("package_slug", sa.String(length=128), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("source_org", sa.String(length=128), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_capability_package_package_slug", "capability_package", ["package_slug"])
    op.create_index("ix_capability_package_review_status", "capability_package", ["review_status"])
    op.create_table(
        "tenant_capability_policy",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_slug", sa.String(length=128), nullable=False),
        sa.Column("policy_status", sa.String(length=32), nullable=False),
        sa.Column("policy_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "objection_case",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("objection_kind", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("related_application_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("complainant_org_id", sa.String(length=64), nullable=False),
        sa.Column("complainant_org_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("provider_org_id", sa.String(length=64), nullable=False),
        sa.Column("provider_org_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("basis_text", sa.Text(), nullable=True),
        sa.Column("expected_result", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolved_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_objection_case_tenant_id", "objection_case", ["tenant_id"])
    op.create_index("ix_objection_case_status", "objection_case", ["status"])
    op.create_index("ix_objection_case_target_type", "objection_case", ["target_type"])
    op.create_table(
        "objection_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("objection_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("submitted_by_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_objection_evidence_objection_id", "objection_evidence", ["objection_id"])
    op.create_index("ix_objection_evidence_type", "objection_evidence", ["evidence_type"])
    op.create_table(
        "objection_process",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("objection_id", sa.String(length=36), nullable=False),
        sa.Column("node_name", sa.String(length=128), nullable=False),
        sa.Column("handler_org_id", sa.String(length=64), nullable=True),
        sa.Column("handler_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("action_result", sa.String(length=32), nullable=False),
        sa.Column("opinion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_objection_process_objection_id", "objection_process", ["objection_id"])
    op.create_table(
        "objection_evaluation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("objection_id", sa.String(length=36), nullable=False),
        sa.Column("evaluator_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("solved_flag", sa.Boolean(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("timeliness_score", sa.Integer(), nullable=True),
        sa.Column("result_score", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_objection_evaluation_objection_id", "objection_evaluation", ["objection_id"])

def downgrade() -> None:
    op.drop_index("ix_objection_evaluation_objection_id", table_name="objection_evaluation")
    op.drop_table("objection_evaluation")
    op.drop_index("ix_objection_process_objection_id", table_name="objection_process")
    op.drop_table("objection_process")
    op.drop_index("ix_objection_evidence_type", table_name="objection_evidence")
    op.drop_index("ix_objection_evidence_objection_id", table_name="objection_evidence")
    op.drop_table("objection_evidence")
    op.drop_index("ix_objection_case_target_type", table_name="objection_case")
    op.drop_index("ix_objection_case_status", table_name="objection_case")
    op.drop_index("ix_objection_case_tenant_id", table_name="objection_case")
    op.drop_table("objection_case")
    op.drop_index("ix_tenant_capability_policy_policy_status", table_name="tenant_capability_policy")
    op.drop_index("ix_tenant_capability_policy_package_slug", table_name="tenant_capability_policy")
    op.drop_index("ix_tenant_capability_policy_tenant_id", table_name="tenant_capability_policy")
    op.drop_table("tenant_capability_policy")
    op.drop_index("ix_capability_package_review_status", table_name="capability_package")
    op.drop_index("ix_capability_package_package_slug", table_name="capability_package")
    op.drop_table("capability_package")
    op.drop_index("ix_delivery_receipt_receipt_status", table_name="delivery_receipt")
    op.drop_index("ix_delivery_receipt_delivery_code", table_name="delivery_receipt")
    op.drop_table("delivery_receipt")
    op.drop_index("ix_delivery_task_state", table_name="delivery_task")
    op.drop_index("ix_delivery_task_application_code", table_name="delivery_task")
    op.drop_index("ix_delivery_task_delivery_code", table_name="delivery_task")
    op.drop_index("ix_delivery_task_tenant_id", table_name="delivery_task")
    op.drop_table("delivery_task")
    op.drop_index("ix_approval_decision_decision", table_name="approval_decision")
    op.drop_index("ix_approval_decision_step_id", table_name="approval_decision")
    op.drop_table("approval_decision")
    op.drop_index("ix_approval_step_status", table_name="approval_step")
    op.drop_index("ix_approval_step_approval_case_id", table_name="approval_step")
    op.drop_table("approval_step")
    op.drop_index("ix_approval_case_current_status", table_name="approval_case")
    op.drop_index("ix_approval_case_application_code", table_name="approval_case")
    op.drop_index("ix_approval_case_tenant_id", table_name="approval_case")
    op.drop_table("approval_case")
    op.drop_index("ix_application_record_status", table_name="application_record")
    op.drop_index("ix_application_record_application_code", table_name="application_record")
    op.drop_index("ix_application_record_tenant_id", table_name="application_record")
    op.drop_table("application_record")
    op.drop_index("ix_catalog_entry_region_code", table_name="catalog_entry")
    op.drop_index("ix_catalog_entry_lifecycle_status", table_name="catalog_entry")
    op.drop_index("ix_catalog_item_item_kind", table_name="catalog_item")
    op.drop_index("ix_catalog_item_resource_code", table_name="catalog_item")
    op.drop_index("ix_catalog_item_catalog_code", table_name="catalog_item")
    op.drop_index("ix_catalog_item_item_code", table_name="catalog_item")
    op.drop_index("ix_catalog_item_tenant_id", table_name="catalog_item")
    op.drop_table("catalog_item")
    op.drop_index("ix_service_invocation_metric_projection_generated_at", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_bucket_granularity", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_consumer_region_code", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_provider_region_code", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_time_bucket", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_consumer_org_id", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_provider_org_id", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_capability_id", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_resource_code", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_metric_scope", table_name="service_invocation_metric_projection")
    op.drop_index("ix_service_invocation_metric_projection_tenant_id", table_name="service_invocation_metric_projection")
    op.drop_table("service_invocation_metric_projection")
    op.drop_index("ix_gateway_runtime_status_projection_generated_at", table_name="gateway_runtime_status_projection")
    op.drop_index("ix_gateway_runtime_status_projection_last_reported_at", table_name="gateway_runtime_status_projection")
    op.drop_index("ix_gateway_runtime_status_projection_status", table_name="gateway_runtime_status_projection")
    op.drop_index("ix_gateway_runtime_status_projection_gateway_instance_id", table_name="gateway_runtime_status_projection")
    op.drop_index("ix_gateway_runtime_status_projection_tenant_id", table_name="gateway_runtime_status_projection")
    op.drop_table("gateway_runtime_status_projection")
    op.drop_index("ix_resource_channel_binding_lifecycle_status", table_name="resource_channel_binding")
    op.drop_index("ix_resource_channel_binding_resource_code", table_name="resource_channel_binding")
    op.drop_index("ix_resource_channel_binding_binding_code", table_name="resource_channel_binding")
    op.drop_index("ix_resource_channel_binding_tenant_id", table_name="resource_channel_binding")
    op.drop_table("resource_channel_binding")
    op.drop_index("ix_resource_api_test_projection_tested_at", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_lifecycle_status", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_test_result", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_binding_code", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_resource_code", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_test_ref", table_name="resource_api_test_projection")
    op.drop_index("ix_resource_api_test_projection_tenant_id", table_name="resource_api_test_projection")
    op.drop_table("resource_api_test_projection")
    op.drop_index("ix_resource_asset_region_code", table_name="resource_asset")
    op.drop_index("ix_resource_asset_lifecycle_status", table_name="resource_asset")
    op.drop_index("ix_resource_asset_resource_kind", table_name="resource_asset")
    op.drop_index("ix_resource_asset_resource_code", table_name="resource_asset")
    op.drop_index("ix_resource_asset_tenant_id", table_name="resource_asset")
    op.drop_table("resource_asset")
    op.drop_index("ix_legacy_object_mapping_mapped_at", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_mapping_status", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_source_ref", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_canonical_ref", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_canonical_type", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_legacy_object_ref", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_legacy_object_type", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_legacy_system", table_name="legacy_object_mapping")
    op.drop_index("ix_legacy_object_mapping_tenant_id", table_name="legacy_object_mapping")
    op.drop_table("legacy_object_mapping")
    op.drop_index("ix_catalog_entry_catalog_code", table_name="catalog_entry")
    op.drop_index("ix_catalog_entry_tenant_id", table_name="catalog_entry")
    op.drop_table("catalog_entry")
    op.drop_table("capability_manifest")
    op.drop_index("ix_audit_receipt_confirmed_at", table_name="audit_receipt")
    op.drop_index("ix_audit_receipt_tx_hash", table_name="audit_receipt")
    op.drop_index("ix_audit_receipt_chain_id", table_name="audit_receipt")
    op.drop_index("ix_audit_receipt_content_hash", table_name="audit_receipt")
    op.drop_index("ix_audit_receipt_skill_id", table_name="audit_receipt")
    op.drop_index("ix_audit_receipt_request_id", table_name="audit_receipt")
    op.drop_table("audit_receipt")
    op.drop_index("ix_anchor_outbox_delivered", table_name="anchor_outbox")
    op.drop_index("ix_anchor_outbox_skill_id", table_name="anchor_outbox")
    op.drop_index("ix_anchor_outbox_request_id", table_name="anchor_outbox")
    op.drop_table("anchor_outbox")
    op.drop_index("ix_audit_event_occurred_at", table_name="audit_event")
    op.drop_index("ix_audit_event_skill_id", table_name="audit_event")
    op.drop_index("ix_audit_event_request_id", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_table("runtime_state")
