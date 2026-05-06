"""add capability call ledger

Revision ID: 0006_capability_call_ledger
Revises: 0005_p1_governance_topic_package
Create Date: 2026-05-05 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_capability_call_ledger"
down_revision = "0005_p1_governance_topic_package"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capability_call",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("call_ref", sa.String(length=128), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("skill_id", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_ref", sa.String(length=128), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    for column in ["call_ref", "tenant_id", "skill_id", "role_code", "status", "request_ref", "started_at"]:
        op.create_index(f"ix_capability_call_{column}", "capability_call", [column])


def downgrade() -> None:
    op.drop_table("capability_call")
