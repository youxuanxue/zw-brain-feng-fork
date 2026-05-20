"""Relax actor_org_role_binding.role_code CHECK constraint to allow IAM realm roles

Revision ID: 0010_role_code_check_relax
Revises: 0009_role_code_d23_retrofit
Create Date: 2026-05-19 11:00:00

业务背景：
    actor_org_role_binding 表存储 actor 的角色绑定，**同时承载两类角色**：
    1. zw-brain 业务角色（policy.ACTOR_NAMES，ROLE_* + admin/system）
    2. IAM realm 角色（从 IAF claims 同步而来，如 ACCOUNT_ADMIN / DEV_IAM_BYPASS）

    PR #60 alembic 0009 D23 retrofit 的 CHECK 约束只允许第 1 类，**误拒第 2 类**，
    导致 actor.projection.sync 在写入 IAM realm 角色时 IntegrityError。

修正：
    DROP CHECK 约束（用 batch_alter_table 兼容 SQLite）。
    业务角色集合（policy.ACTOR_NAMES）的硬约束改由 3 层兜底：
      1. policy.assert_no_legacy_role_codes() 模块加载启动检查
      2. preflight 段 19 check_no_legacy_role_codes.py 仓库级 grep
      3. test_role_codes_alignment.py 跨文件机械验证

    DB 层 CHECK 约束被证明过严（误伤 IAM 角色）；3 层应用层保护已足够确保
    业务角色集合冻结的安全性。历史 R1-R8 角色码字面值在写入路径上仍被
    policy.py 启动检查 _LEGACY_ROLE_CODES 集合拦截（assert_no_legacy_role_codes）。

零回滚（沿用 D23 单向决策原则）：downgrade 显式 NotImplementedError。
"""
from __future__ import annotations

from alembic import op

revision = "0010_role_code_check_relax"
down_revision = "0009_role_code_d23_retrofit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 用 batch_alter_table 兼容 SQLite（SQLite 不支持 ALTER TABLE DROP CONSTRAINT）
    with op.batch_alter_table("actor_org_role_binding") as batch_op:
        batch_op.drop_constraint("ck_actor_org_role_binding_role_code_d23", type_="check")


def downgrade() -> None:
    raise NotImplementedError(
        "D23 / D30 retrofit：actor_org_role_binding.role_code CHECK 约束已永久 DROP（误伤 IAM 角色）。"
        "如需重新约束，应改为允许两类角色的 enum 或不约束（应用层兜底）。"
    )
