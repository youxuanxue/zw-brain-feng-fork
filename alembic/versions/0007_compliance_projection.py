"""add compliance and ops projections (M1-M6)

Revision ID: 0007_compliance_projection
Revises: 0006_capability_call_ledger
Create Date: 2026-05-06 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_compliance_projection"
down_revision = "0006_capability_call_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compliance_case",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("case_code", sa.String(length=64), nullable=False),
        sa.Column("case_kind", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_ref", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="detected"),
        sa.Column("assignee_org_id", sa.String(length=64), nullable=True),
        sa.Column("assignee_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("detected_summary", sa.Text(), nullable=False),
        sa.Column("resolved_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "case_code", name="uq_compliance_case_tenant_code"),
    )
    for column in ["tenant_id", "case_code", "case_kind", "target_type", "target_ref", "severity", "status", "assignee_org_id", "created_at"]:
        op.create_index(f"ix_compliance_case_{column}", "compliance_case", [column])

    op.create_table(
        "compliance_rule",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_kind", sa.String(length=32), nullable=False),
        sa.Column("target_scope", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("threshold_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "rule_code", name="uq_compliance_rule_tenant_code"),
    )
    for column in ["tenant_id", "rule_code", "rule_kind", "target_scope", "review_status"]:
        op.create_index(f"ix_compliance_rule_{column}", "compliance_rule", [column])

    op.create_table(
        "risk_event_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_ref", sa.String(length=128), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_system", "source_ref", name="uq_risk_event_source"),
    )
    for column in ["tenant_id", "event_kind", "severity", "source_system", "source_ref", "target_type", "target_ref", "detected_at"]:
        op.create_index(f"ix_risk_event_{column}", "risk_event_projection", [column])

    op.create_table(
        "health_signal_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("subject_kind", sa.String(length=32), nullable=False),
        sa.Column("subject_ref", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("metric_json", sa.JSON(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "subject_kind", "subject_ref", name="uq_health_signal_subject"),
    )
    for column in ["tenant_id", "subject_kind", "subject_ref", "status", "last_observed_at"]:
        op.create_index(f"ix_health_signal_{column}", "health_signal_projection", [column])

    op.create_table(
        "standard_asset_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("asset_kind", sa.String(length=32), nullable=False),
        sa.Column("asset_ref", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "asset_kind", "asset_ref", name="uq_standard_asset_kind_ref"),
    )
    for column in ["tenant_id", "asset_kind", "asset_ref", "status", "source_system"]:
        op.create_index(f"ix_standard_asset_{column}", "standard_asset_projection", [column])

    op.create_table(
        "metric_definition_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("metric_kind", sa.String(length=32), nullable=False),
        sa.Column("target_aggregate", sa.String(length=64), nullable=False),
        sa.Column("dimension_json", sa.JSON(), nullable=False),
        sa.Column("formula_ref", sa.String(length=255), nullable=True),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "metric_code", name="uq_metric_definition_tenant_code"),
    )
    for column in ["tenant_id", "metric_code", "metric_kind", "target_aggregate", "owner_org_id"]:
        op.create_index(f"ix_metric_definition_{column}", "metric_definition_projection", [column])


def downgrade() -> None:
    op.drop_table("metric_definition_projection")
    op.drop_table("standard_asset_projection")
    op.drop_table("health_signal_projection")
    op.drop_table("risk_event_projection")
    op.drop_table("compliance_rule")
    op.drop_table("compliance_case")
