"""agent runtime agent state

Revision ID: a1b2c3d4e5f6
Revises: 77da8251e66d
Create Date: 2026-06-23 18:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "77da8251e66d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    return index_name in {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    table_name = "agent_runtime_agent_state"
    if not _table_exists(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("agent_id", sa.String(length=128), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("allowed_roles_json", sa.JSON(), nullable=False),
            sa.Column("updated_by", sa.String(length=128), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "agent_id", name="uq_agent_runtime_state_tenant_agent"),
        )
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if not _index_exists(table_name, "ix_agent_runtime_agent_state_agent_id"):
            batch_op.create_index(batch_op.f("ix_agent_runtime_agent_state_agent_id"), ["agent_id"], unique=False)
        if not _index_exists(table_name, "ix_agent_runtime_agent_state_enabled"):
            batch_op.create_index(batch_op.f("ix_agent_runtime_agent_state_enabled"), ["enabled"], unique=False)
        if not _index_exists(table_name, "ix_agent_runtime_agent_state_tenant_id"):
            batch_op.create_index(batch_op.f("ix_agent_runtime_agent_state_tenant_id"), ["tenant_id"], unique=False)


def downgrade() -> None:
    table_name = "agent_runtime_agent_state"
    if not _table_exists(table_name):
        return
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if _index_exists(table_name, "ix_agent_runtime_agent_state_tenant_id"):
            batch_op.drop_index(batch_op.f("ix_agent_runtime_agent_state_tenant_id"))
        if _index_exists(table_name, "ix_agent_runtime_agent_state_enabled"):
            batch_op.drop_index(batch_op.f("ix_agent_runtime_agent_state_enabled"))
        if _index_exists(table_name, "ix_agent_runtime_agent_state_agent_id"):
            batch_op.drop_index(batch_op.f("ix_agent_runtime_agent_state_agent_id"))
    op.drop_table(table_name)
