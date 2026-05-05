"""add p0 external adapter records

Revision ID: 0004_p0_external_adapter_records
Revises: 0003_exchange_delivery_records
Create Date: 2026-05-05 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_p0_external_adapter_records"
down_revision = "0003_exchange_delivery_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_object_mapping",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("external_system", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("local_aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("local_aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("legacy_table", sa.String(length=128), nullable=True),
        sa.Column("legacy_id", sa.String(length=128), nullable=True),
        sa.Column("external_object_type", sa.String(length=128), nullable=False),
        sa.Column("external_object_id", sa.String(length=128), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=True),
        sa.Column("batch_no", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_receipt_json", sa.JSON(), nullable=False),
        sa.Column("extra_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
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
    op.create_index("ix_external_object_mapping_tenant_id", "external_object_mapping", ["tenant_id"])
    op.create_index("ix_external_object_mapping_external_system", "external_object_mapping", ["external_system"])
    op.create_index("ix_external_object_mapping_direction", "external_object_mapping", ["direction"])
    op.create_index("ix_external_object_mapping_local_aggregate_type", "external_object_mapping", ["local_aggregate_type"])
    op.create_index("ix_external_object_mapping_local_aggregate_id", "external_object_mapping", ["local_aggregate_id"])
    op.create_index("ix_external_object_mapping_external_object_type", "external_object_mapping", ["external_object_type"])
    op.create_index("ix_external_object_mapping_external_object_id", "external_object_mapping", ["external_object_id"])
    op.create_index("ix_external_object_mapping_batch_no", "external_object_mapping", ["batch_no"])
    op.create_index("ix_external_object_mapping_status", "external_object_mapping", ["status"])
    op.create_index("ix_external_object_mapping_updated_at", "external_object_mapping", ["updated_at"])

    op.create_table(
        "adapter_run_record",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("adapter_slug", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("receipt_json", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "adapter_slug", "operation", "idempotency_key", name="uq_adapter_run_idempotency"),
    )
    op.create_index("ix_adapter_run_record_tenant_id", "adapter_run_record", ["tenant_id"])
    op.create_index("ix_adapter_run_record_adapter_slug", "adapter_run_record", ["adapter_slug"])
    op.create_index("ix_adapter_run_record_operation", "adapter_run_record", ["operation"])
    op.create_index("ix_adapter_run_record_direction", "adapter_run_record", ["direction"])
    op.create_index("ix_adapter_run_record_source_ref", "adapter_run_record", ["source_ref"])
    op.create_index("ix_adapter_run_record_idempotency_key", "adapter_run_record", ["idempotency_key"])
    op.create_index("ix_adapter_run_record_status", "adapter_run_record", ["status"])
    op.create_index("ix_adapter_run_record_started_at", "adapter_run_record", ["started_at"])


def downgrade() -> None:
    op.drop_table("adapter_run_record")
    op.drop_table("external_object_mapping")
