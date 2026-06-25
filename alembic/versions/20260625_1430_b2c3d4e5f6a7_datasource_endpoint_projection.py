"""datasource endpoint projection table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-25 14:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    table_name = "datasource_endpoint_projection"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("endpoint_id", sa.String(length=64), nullable=False),
            sa.Column("connection_ref", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("db_name", sa.String(length=150), nullable=False),
            sa.Column("db_type", sa.String(length=32), nullable=False),
            sa.Column("host_ref", sa.String(length=128), nullable=True),
            sa.Column("port", sa.Integer(), nullable=True),
            sa.Column("org_code", sa.String(length=64), nullable=True),
            sa.Column("org_name", sa.String(length=255), nullable=True),
            sa.Column("contact_name", sa.String(length=100), nullable=True),
            sa.Column("contact_phone", sa.String(length=32), nullable=True),
            sa.Column("data_partition", sa.String(length=32), nullable=False),
            sa.Column("connectivity_status", sa.String(length=32), nullable=False),
            sa.Column("secret_ref", sa.String(length=128), nullable=True),
            sa.Column("metadata_database_id", sa.String(length=64), nullable=True),
            sa.Column("node_id", sa.String(length=64), nullable=True),
            sa.Column("node_name", sa.String(length=128), nullable=True),
            sa.Column("remark", sa.String(length=300), nullable=True),
            sa.Column("source_ref", sa.String(length=128), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "endpoint_id", name="uq_datasource_endpoint_tenant_id"),
        )
        op.create_index("ix_datasource_endpoint_partition", table_name, ["tenant_id", "data_partition"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_connection_ref"), table_name, ["connection_ref"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_connectivity_status"), table_name, ["connectivity_status"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_data_partition"), table_name, ["data_partition"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_endpoint_id"), table_name, ["endpoint_id"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_metadata_database_id"), table_name, ["metadata_database_id"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_org_code"), table_name, ["org_code"], unique=False)
        op.create_index(op.f("ix_datasource_endpoint_projection_tenant_id"), table_name, ["tenant_id"], unique=False)


def downgrade() -> None:
    table_name = "datasource_endpoint_projection"
    if _table_exists(table_name):
        op.drop_table(table_name)
