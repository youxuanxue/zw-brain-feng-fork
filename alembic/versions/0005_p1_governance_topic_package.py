"""add p1 governance and topic package projections

Revision ID: 0005_p1_governance_topic_package
Revises: 0004_p0_external_adapter_records
Create Date: 2026-05-05 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_p1_governance_topic_package"
down_revision = "0004_p0_external_adapter_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_projection_tenant"),
    )
    op.create_index("ix_tenant_projection_tenant_id", "tenant_projection", ["tenant_id"])
    op.create_index("ix_tenant_projection_status", "tenant_projection", ["status"])

    op.create_table(
        "org_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("org_code", sa.String(length=64), nullable=False),
        sa.Column("org_name", sa.String(length=200), nullable=False),
        sa.Column("parent_org_code", sa.String(length=64), nullable=True),
        sa.Column("region_code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "org_code", name="uq_org_projection_tenant_code"),
    )
    for column in ["tenant_id", "org_code", "parent_org_code", "region_code", "status"]:
        op.create_index(f"ix_org_projection_{column}", "org_projection", [column])

    op.create_table(
        "region_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("region_code", sa.String(length=64), nullable=False),
        sa.Column("region_name", sa.String(length=200), nullable=False),
        sa.Column("parent_region_code", sa.String(length=64), nullable=True),
        sa.Column("region_level", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "region_code", name="uq_region_projection_tenant_code"),
    )
    for column in ["tenant_id", "region_code", "parent_region_code", "region_level", "status"]:
        op.create_index(f"ix_region_projection_{column}", "region_projection", [column])

    op.create_table(
        "role_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("role_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "role_code", name="uq_role_projection_tenant_code"),
    )
    for column in ["tenant_id", "role_code", "status"]:
        op.create_index(f"ix_role_projection_{column}", "role_projection", [column])

    op.create_table(
        "actor_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("external_actor_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("org_code", sa.String(length=64), nullable=True),
        sa.Column("role_codes_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_actor_id", name="uq_actor_projection_tenant_external"),
    )
    for column in ["tenant_id", "external_actor_id", "org_code", "status"]:
        op.create_index(f"ix_actor_projection_{column}", "actor_projection", [column])

    op.create_table(
        "legacy_policy_mapping_candidate",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("legacy_system", sa.String(length=64), nullable=False),
        sa.Column("legacy_permission_ref", sa.String(length=128), nullable=False),
        sa.Column("legacy_role_ref", sa.String(length=128), nullable=True),
        sa.Column("capability_id", sa.String(length=128), nullable=False),
        sa.Column("surface", sa.String(length=32), nullable=True),
        sa.Column("candidate_status", sa.String(length=32), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "legacy_system", "legacy_permission_ref", "capability_id", name="uq_legacy_policy_candidate_identity"),
    )
    for column in ["tenant_id", "legacy_system", "legacy_permission_ref", "legacy_role_ref", "capability_id", "surface", "candidate_status"]:
        op.create_index(f"ix_legacy_policy_mapping_candidate_{column}", "legacy_policy_mapping_candidate", [column])

    op.create_table(
        "topic_package",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("scenario", sa.String(length=200), nullable=False),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("owner_org_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("metric_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "package_code", name="uq_topic_package_tenant_code"),
    )
    for column in ["tenant_id", "package_code", "scenario", "owner_org_id", "status"]:
        op.create_index(f"ix_topic_package_{column}", "topic_package", [column])

    op.create_table(
        "topic_package_item",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("item_code", sa.String(length=128), nullable=False),
        sa.Column("ref_type", sa.String(length=64), nullable=False),
        sa.Column("ref_id", sa.String(length=128), nullable=False),
        sa.Column("ref_status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "package_code", "item_code", name="uq_topic_package_item_tenant_code"),
    )
    for column in ["tenant_id", "package_code", "item_code", "ref_type", "ref_id", "ref_status"]:
        op.create_index(f"ix_topic_package_item_{column}", "topic_package_item", [column])

    op.create_table(
        "topic_package_visibility",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("visibility_code", sa.String(length=128), nullable=False),
        sa.Column("org_code", sa.String(length=64), nullable=True),
        sa.Column("role_code", sa.String(length=64), nullable=True),
        sa.Column("region_code", sa.String(length=64), nullable=True),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("policy_status", sa.String(length=32), nullable=False),
        sa.Column("condition_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "package_code", "visibility_code", name="uq_topic_visibility_tenant_code"),
    )
    for column in ["tenant_id", "package_code", "visibility_code", "org_code", "role_code", "region_code", "surface", "intent", "policy_status"]:
        op.create_index(f"ix_topic_package_visibility_{column}", "topic_package_visibility", [column])

    op.create_table(
        "topic_package_review_record",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_result", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("reviewer_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("opinion", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for column in ["tenant_id", "package_code", "action_type", "action_result", "to_status"]:
        op.create_index(f"ix_topic_package_review_record_{column}", "topic_package_review_record", [column])

    op.create_table(
        "topic_package_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("related_ref_type", sa.String(length=64), nullable=True),
        sa.Column("related_ref_id", sa.String(length=128), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("submitted_by_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for column in ["tenant_id", "package_code", "evidence_type", "related_ref_type", "related_ref_id"]:
        op.create_index(f"ix_topic_package_evidence_{column}", "topic_package_evidence", [column])

    op.create_table(
        "topic_package_metric_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("package_code", sa.String(length=128), nullable=False),
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column("metric_value", sa.Integer(), nullable=False),
        sa.Column("metric_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "package_code", "metric_key", name="uq_topic_metric_tenant_key"),
    )
    for column in ["tenant_id", "package_code", "metric_key"]:
        op.create_index(f"ix_topic_package_metric_projection_{column}", "topic_package_metric_projection", [column])


def downgrade() -> None:
    op.drop_table("topic_package_metric_projection")
    op.drop_table("topic_package_evidence")
    op.drop_table("topic_package_review_record")
    op.drop_table("topic_package_visibility")
    op.drop_table("topic_package_item")
    op.drop_table("topic_package")
    op.drop_table("legacy_policy_mapping_candidate")
    op.drop_table("actor_projection")
    op.drop_table("role_projection")
    op.drop_table("region_projection")
    op.drop_table("org_projection")
    op.drop_table("tenant_projection")
