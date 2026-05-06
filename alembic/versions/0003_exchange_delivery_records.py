"""add exchange delivery canonical records

Revision ID: 0003_exchange_delivery_records
Revises: 0002_catalog_metadata_evidence
Create Date: 2026-05-04 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_exchange_delivery_records"
down_revision = "0002_catalog_metadata_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_subscription",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("subscription_code", sa.String(length=64), nullable=False),
        sa.Column("delivery_code", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schedule_ref_json", sa.JSON(), nullable=False),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("legacy_status_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "subscription_code", name="uq_delivery_subscription_tenant_code"),
    )
    op.create_index("ix_delivery_subscription_tenant_id", "delivery_subscription", ["tenant_id"])
    op.create_index("ix_delivery_subscription_subscription_code", "delivery_subscription", ["subscription_code"])
    op.create_index("ix_delivery_subscription_delivery_code", "delivery_subscription", ["delivery_code"])
    op.create_index("ix_delivery_subscription_resource_code", "delivery_subscription", ["resource_code"])
    op.create_index("ix_delivery_subscription_status", "delivery_subscription", ["status"])

    op.create_table(
        "delivery_attempt",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_code", sa.String(length=96), nullable=False),
        sa.Column("delivery_code", sa.String(length=64), nullable=False),
        sa.Column("subscription_code", sa.String(length=64), nullable=True),
        sa.Column("attempt_kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("executor_ref", sa.String(length=128), nullable=True),
        sa.Column("evidence_ref", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "attempt_code", name="uq_delivery_attempt_tenant_code"),
    )
    op.create_index("ix_delivery_attempt_tenant_id", "delivery_attempt", ["tenant_id"])
    op.create_index("ix_delivery_attempt_attempt_code", "delivery_attempt", ["attempt_code"])
    op.create_index("ix_delivery_attempt_delivery_code", "delivery_attempt", ["delivery_code"])
    op.create_index("ix_delivery_attempt_subscription_code", "delivery_attempt", ["subscription_code"])
    op.create_index("ix_delivery_attempt_attempt_kind", "delivery_attempt", ["attempt_kind"])
    op.create_index("ix_delivery_attempt_state", "delivery_attempt", ["state"])

    op.create_table(
        "delivery_execution_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_ref", sa.String(length=128), nullable=False),
        sa.Column("delivery_code", sa.String(length=64), nullable=True),
        sa.Column("attempt_code", sa.String(length=96), nullable=True),
        sa.Column("executor_kind", sa.String(length=64), nullable=False),
        sa.Column("executor_ref", sa.String(length=128), nullable=True),
        sa.Column("evidence_kind", sa.String(length=64), nullable=False),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("sanitized_payload_json", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "evidence_ref", name="uq_delivery_execution_evidence_tenant_ref"),
    )
    op.create_index("ix_delivery_execution_evidence_tenant_id", "delivery_execution_evidence", ["tenant_id"])
    op.create_index("ix_delivery_execution_evidence_evidence_ref", "delivery_execution_evidence", ["evidence_ref"])
    op.create_index("ix_delivery_execution_evidence_delivery_code", "delivery_execution_evidence", ["delivery_code"])
    op.create_index("ix_delivery_execution_evidence_attempt_code", "delivery_execution_evidence", ["attempt_code"])
    op.create_index("ix_delivery_execution_evidence_executor_kind", "delivery_execution_evidence", ["executor_kind"])
    op.create_index("ix_delivery_execution_evidence_evidence_kind", "delivery_execution_evidence", ["evidence_kind"])
    op.create_index("ix_delivery_execution_evidence_result_status", "delivery_execution_evidence", ["result_status"])
    op.create_index("ix_delivery_execution_evidence_captured_at", "delivery_execution_evidence", ["captured_at"])

    op.create_table(
        "exchange_metric_projection",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("metric_scope", sa.String(length=64), nullable=False),
        sa.Column("resource_code", sa.String(length=64), nullable=True),
        sa.Column("delivery_code", sa.String(length=64), nullable=True),
        sa.Column("subscription_code", sa.String(length=64), nullable=True),
        sa.Column("provider_org_id", sa.String(length=64), nullable=True),
        sa.Column("consumer_org_id", sa.String(length=64), nullable=True),
        sa.Column("bucket_granularity", sa.String(length=32), nullable=False),
        sa.Column("time_bucket", sa.String(length=32), nullable=False),
        sa.Column("exchange_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
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
    op.create_index("ix_exchange_metric_projection_tenant_id", "exchange_metric_projection", ["tenant_id"])
    op.create_index("ix_exchange_metric_projection_metric_scope", "exchange_metric_projection", ["metric_scope"])
    op.create_index("ix_exchange_metric_projection_resource_code", "exchange_metric_projection", ["resource_code"])
    op.create_index("ix_exchange_metric_projection_delivery_code", "exchange_metric_projection", ["delivery_code"])
    op.create_index("ix_exchange_metric_projection_subscription_code", "exchange_metric_projection", ["subscription_code"])
    op.create_index("ix_exchange_metric_projection_provider_org_id", "exchange_metric_projection", ["provider_org_id"])
    op.create_index("ix_exchange_metric_projection_consumer_org_id", "exchange_metric_projection", ["consumer_org_id"])
    op.create_index("ix_exchange_metric_projection_bucket_granularity", "exchange_metric_projection", ["bucket_granularity"])
    op.create_index("ix_exchange_metric_projection_time_bucket", "exchange_metric_projection", ["time_bucket"])
    op.create_index("ix_exchange_metric_projection_generated_at", "exchange_metric_projection", ["generated_at"])


def downgrade() -> None:
    op.drop_table("exchange_metric_projection")
    op.drop_table("delivery_execution_evidence")
    op.drop_table("delivery_attempt")
    op.drop_table("delivery_subscription")
