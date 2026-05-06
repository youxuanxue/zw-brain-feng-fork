"""add catalog metadata evidence tables

Revision ID: 0002_catalog_metadata_evidence
Revises: 0001_runtime_bootstrap
Create Date: 2026-05-04 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_catalog_metadata_evidence"
down_revision = "0001_runtime_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_model",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("model_schema_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "model_code", name="uq_catalog_model_tenant_code"),
    )
    op.create_index("ix_catalog_model_tenant_id", "catalog_model", ["tenant_id"])
    op.create_index("ix_catalog_model_model_code", "catalog_model", ["model_code"])
    op.create_index("ix_catalog_model_status", "catalog_model", ["status"])

    op.create_table(
        "catalog_model_field",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column("field_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("data_type", sa.String(length=64), nullable=False),
        sa.Column("sensitive_level", sa.String(length=64), nullable=True),
        sa.Column("field_policy_json", sa.JSON(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "model_code", "field_code", name="uq_catalog_model_field_tenant_code"),
    )
    op.create_index("ix_catalog_model_field_tenant_id", "catalog_model_field", ["tenant_id"])
    op.create_index("ix_catalog_model_field_model_code", "catalog_model_field", ["model_code"])
    op.create_index("ix_catalog_model_field_field_code", "catalog_model_field", ["field_code"])

    op.create_table(
        "catalog_entry_version",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("catalog_code", sa.String(length=64), nullable=False),
        sa.Column("version_no", sa.String(length=64), nullable=False),
        sa.Column("version_status", sa.String(length=32), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("audit_ref", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "catalog_code", "version_no", name="uq_catalog_entry_version_tenant_code"),
    )
    op.create_index("ix_catalog_entry_version_tenant_id", "catalog_entry_version", ["tenant_id"])
    op.create_index("ix_catalog_entry_version_catalog_code", "catalog_entry_version", ["catalog_code"])
    op.create_index("ix_catalog_entry_version_version_status", "catalog_entry_version", ["version_status"])

    op.create_table(
        "resource_schema_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("mapping_code", sa.String(length=128), nullable=False),
        sa.Column("catalog_code", sa.String(length=64), nullable=False),
        sa.Column("catalog_item_code", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("binding_code", sa.String(length=64), nullable=False),
        sa.Column("source_schema_ref", sa.JSON(), nullable=False),
        sa.Column("mapping_rule_json", sa.JSON(), nullable=False),
        sa.Column("confidence_level", sa.String(length=32), nullable=False),
        sa.Column("evidence_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "catalog_item_code", "resource_code", "binding_code", "status", name="uq_resource_schema_mapping_current"),
    )
    op.create_index("ix_resource_schema_mapping_tenant_id", "resource_schema_mapping", ["tenant_id"])
    op.create_index("ix_resource_schema_mapping_mapping_code", "resource_schema_mapping", ["mapping_code"])
    op.create_index("ix_resource_schema_mapping_catalog_code", "resource_schema_mapping", ["catalog_code"])
    op.create_index("ix_resource_schema_mapping_catalog_item_code", "resource_schema_mapping", ["catalog_item_code"])
    op.create_index("ix_resource_schema_mapping_resource_code", "resource_schema_mapping", ["resource_code"])
    op.create_index("ix_resource_schema_mapping_binding_code", "resource_schema_mapping", ["binding_code"])
    op.create_index("ix_resource_schema_mapping_confidence_level", "resource_schema_mapping", ["confidence_level"])
    op.create_index("ix_resource_schema_mapping_status", "resource_schema_mapping", ["status"])

    op.create_table(
        "resource_schema_snapshot",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_ref", sa.String(length=128), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("binding_code", sa.String(length=64), nullable=True),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("schema_hash", sa.String(length=128), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "snapshot_ref", name="uq_resource_schema_snapshot_tenant_ref"),
    )
    op.create_index("ix_resource_schema_snapshot_tenant_id", "resource_schema_snapshot", ["tenant_id"])
    op.create_index("ix_resource_schema_snapshot_snapshot_ref", "resource_schema_snapshot", ["snapshot_ref"])
    op.create_index("ix_resource_schema_snapshot_resource_code", "resource_schema_snapshot", ["resource_code"])
    op.create_index("ix_resource_schema_snapshot_binding_code", "resource_schema_snapshot", ["binding_code"])
    op.create_index("ix_resource_schema_snapshot_schema_hash", "resource_schema_snapshot", ["schema_hash"])
    op.create_index("ix_resource_schema_snapshot_captured_at", "resource_schema_snapshot", ["captured_at"])

    op.create_table(
        "metadata_gather_evidence_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("gather_task_ref", sa.String(length=128), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=False),
        sa.Column("source_system_ref", sa.String(length=128), nullable=True),
        sa.Column("schema_snapshot_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "gather_task_ref", name="uq_metadata_gather_tenant_task"),
    )
    op.create_index("ix_metadata_gather_evidence_projection_tenant_id", "metadata_gather_evidence_projection", ["tenant_id"])
    op.create_index("ix_metadata_gather_evidence_projection_gather_task_ref", "metadata_gather_evidence_projection", ["gather_task_ref"])
    op.create_index("ix_metadata_gather_evidence_projection_resource_code", "metadata_gather_evidence_projection", ["resource_code"])
    op.create_index("ix_metadata_gather_evidence_projection_status", "metadata_gather_evidence_projection", ["status"])
    op.create_index("ix_metadata_gather_evidence_projection_generated_at", "metadata_gather_evidence_projection", ["generated_at"])

    op.create_table(
        "lineage_relation_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("relation_ref", sa.String(length=128), nullable=False),
        sa.Column("relation_scope", sa.String(length=32), nullable=False),
        sa.Column("source_resource_code", sa.String(length=64), nullable=True),
        sa.Column("source_schema_ref", sa.String(length=128), nullable=True),
        sa.Column("target_resource_code", sa.String(length=64), nullable=True),
        sa.Column("target_schema_ref", sa.String(length=128), nullable=True),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("relation_rule_json", sa.JSON(), nullable=False),
        sa.Column("source_evidence_ref", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "relation_ref", name="uq_lineage_relation_tenant_ref"),
    )
    op.create_index("ix_lineage_relation_projection_tenant_id", "lineage_relation_projection", ["tenant_id"])
    op.create_index("ix_lineage_relation_projection_relation_ref", "lineage_relation_projection", ["relation_ref"])
    op.create_index("ix_lineage_relation_projection_relation_scope", "lineage_relation_projection", ["relation_scope"])
    op.create_index("ix_lineage_relation_projection_source_resource_code", "lineage_relation_projection", ["source_resource_code"])
    op.create_index("ix_lineage_relation_projection_target_resource_code", "lineage_relation_projection", ["target_resource_code"])
    op.create_index("ix_lineage_relation_projection_relation_type", "lineage_relation_projection", ["relation_type"])
    op.create_index("ix_lineage_relation_projection_generated_at", "lineage_relation_projection", ["generated_at"])

    op.create_table(
        "quality_evidence_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("quality_ref", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_ref", sa.String(length=128), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "quality_ref", name="uq_quality_evidence_tenant_ref"),
    )
    op.create_index("ix_quality_evidence_projection_tenant_id", "quality_evidence_projection", ["tenant_id"])
    op.create_index("ix_quality_evidence_projection_quality_ref", "quality_evidence_projection", ["quality_ref"])
    op.create_index("ix_quality_evidence_projection_target_type", "quality_evidence_projection", ["target_type"])
    op.create_index("ix_quality_evidence_projection_target_ref", "quality_evidence_projection", ["target_ref"])
    op.create_index("ix_quality_evidence_projection_quality_status", "quality_evidence_projection", ["quality_status"])
    op.create_index("ix_quality_evidence_projection_generated_at", "quality_evidence_projection", ["generated_at"])


def downgrade() -> None:
    op.drop_table("quality_evidence_projection")
    op.drop_table("lineage_relation_projection")
    op.drop_table("metadata_gather_evidence_projection")
    op.drop_table("resource_schema_snapshot")
    op.drop_table("resource_schema_mapping")
    op.drop_table("catalog_entry_version")
    op.drop_table("catalog_model_field")
    op.drop_table("catalog_model")
