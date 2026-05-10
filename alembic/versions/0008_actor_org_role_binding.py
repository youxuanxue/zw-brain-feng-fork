"""add actor org role binding projection

Revision ID: 0008_actor_org_role_binding
Revises: 0007_compliance_projection
Create Date: 2026-05-10 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_actor_org_role_binding"
down_revision = "0007_compliance_projection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actor_org_role_binding",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("external_actor_id", sa.String(length=128), nullable=False),
        sa.Column("org_code", sa.String(length=64), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("binding_status", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_actor_id", "org_code", "role_code", name="uq_actor_org_role_binding_identity"),
    )
    for column in ["tenant_id", "external_actor_id", "org_code", "role_code", "binding_status"]:
        op.create_index(f"ix_actor_org_role_binding_{column}", "actor_org_role_binding", [column])


def downgrade() -> None:
    for column in ["binding_status", "role_code", "org_code", "external_actor_id", "tenant_id"]:
        op.drop_index(f"ix_actor_org_role_binding_{column}", table_name="actor_org_role_binding")
    op.drop_table("actor_org_role_binding")
