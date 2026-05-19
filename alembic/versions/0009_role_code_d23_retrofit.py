"""D23 retrofit: migrate r1-r8 role codes to ROLE_* + add CHECK constraint

Revision ID: 0009_role_code_d23_retrofit
Revises: 0008_actor_org_role_binding
Create Date: 2026-05-19 09:00:00

业务背景：2026-05-19 GATE-1.1 retrofit（D23）退役 R1-R8 八角色矩阵，对齐旧平台
ROLE_* 7 角色码（详见 docs/approved/zw-brain-roles-v2.md）。

本迁移做两件事：
1. 数据迁移：actor_org_role_binding.role_code 中存量 r1-r8 字面值映射到新 6 角色码
2. DDL 加固：role_code 加 CHECK 约束，禁止任何 r1-r8 字面值写入

迁移映射规则（与 zw_brain/domain/policy.py 一致）：
  r1, r3, r4 → ROLE_ORGAN_OPERATER
  r2, r5     → ROLE_ORGAN_MANAGER
  r6         → ROLE_ORGAN_MANAGER
  r7         → ROLE_BUSIAUDIT
  r8         → ROLE_SECURITY_AUDIT

不留兼容：downgrade 被显式禁用，避免误回滚把已映射的语义反推回错误的 r1-r8。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_role_code_d23_retrofit"
down_revision = "0008_actor_org_role_binding"
branch_labels = None
depends_on = None

# R-008: 从单一来源 role_codes 派生（_ALLOWED_ROLE_CODES）
# 注意：alembic 模块不能 import zw_brain.domain.role_codes（迁移可能在 app 不可导入时运行），
# 此处显式硬编码 + 测试 t8 验证与 ACTOR_NAMES 同步（CI 兜底）
_LEGACY_TO_NEW = {
    "r1": "ROLE_ORGAN_OPERATER",
    "r2": "ROLE_ORGAN_MANAGER",
    "r3": "ROLE_ORGAN_OPERATER",
    "r4": "ROLE_ORGAN_OPERATER",
    "r5": "ROLE_ORGAN_MANAGER",
    "r6": "ROLE_ORGAN_MANAGER",
    "r7": "ROLE_BUSIAUDIT",
    "r8": "ROLE_SECURITY_AUDIT",
}

# 新角色码白名单（CHECK 约束依据）；test_t8 验证与 role_codes.ALL_ROLE_CODES 一致
_ALLOWED_ROLE_CODES = (
    "ROLE_ORGAN_OPERATER",
    "ROLE_ORGAN_MANAGER",
    "ROLE_BUSIAUDIT",
    "ROLE_SECURITY_ADMIN",
    "ROLE_SECURITY_AUDIT",
    "ROLE_SYSTEM",
    "admin",
    "system",
)


def upgrade() -> None:
    bind = op.get_bind()

    # R-004 / R-010 fix: 双层审计 — DELETE 前先 INSERT 到 audit_event 持久化（生产可查），
    # 再用 rowcount + logging 兜底（迁移日志可见）。
    # 基线 D22 元规则禁止 OPC 静默吞错；本迁移既写 DB 审计、也写 logger。
    import json
    import logging
    from datetime import datetime, timezone
    log = logging.getLogger("alembic.0009_role_code_d23_retrofit")
    now_iso = datetime.now(timezone.utc).isoformat()

    for legacy_code, new_code in _LEGACY_TO_NEW.items():
        # Step A: 先把会被 DELETE 的冲突记录摘要写入 audit_event（持久化迁移证据）
        # audit_event 表 schema (alembic 0001): id auto / request_id / actor / skill_id /
        #   phase / payload_json / occurred_at
        conflicts = bind.execute(
            sa.text(
                """
                SELECT a.id, a.tenant_id, a.external_actor_id, a.org_code, a.role_code,
                       a.binding_status, a.source_ref
                FROM actor_org_role_binding a
                WHERE a.role_code = :legacy
                  AND EXISTS (
                      SELECT 1 FROM actor_org_role_binding b
                      WHERE b.tenant_id = a.tenant_id
                        AND b.external_actor_id = a.external_actor_id
                        AND b.org_code = a.org_code
                        AND b.role_code = :new
                        AND b.id != a.id
                  )
                """
            ),
            {"legacy": legacy_code, "new": new_code},
        ).fetchall()

        for row in conflicts:
            payload = {
                "d23_retrofit": True,
                "action": "dedup_delete_on_collapse",
                "deleted_record": {
                    "id": row[0],
                    "tenant_id": row[1],
                    "external_actor_id": row[2],
                    "org_code": row[3],
                    "legacy_role_code": row[4],
                    "binding_status": row[5],
                    "source_ref": row[6],
                },
                "kept_canonical_role": new_code,
                "reason": (
                    f"actor 同 org 同时持有 {legacy_code} 与映射后等价的 {new_code} 兄弟绑定；"
                    "本迁移按 UniqueConstraint 去重保留 canonical 新码记录。"
                ),
            }
            bind.execute(
                sa.text(
                    """
                    INSERT INTO audit_event (request_id, actor, skill_id, phase, payload_json, occurred_at)
                    VALUES (:rid, :actor, :sid, :phase, :payload, :ts)
                    """
                ),
                {
                    "rid": f"d23-retrofit-{row[0]}",
                    "actor": "system:alembic:0009_role_code_d23_retrofit",
                    "sid": "legacy.role_code.migration.d23",
                    "phase": "dedup_delete_on_collapse",
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "ts": now_iso,
                },
            )

        # Step B: DELETE 冲突记录
        delete_result = bind.execute(
            sa.text(
                """
                DELETE FROM actor_org_role_binding
                WHERE id IN (
                    SELECT a.id FROM actor_org_role_binding a
                    WHERE a.role_code = :legacy
                      AND EXISTS (
                          SELECT 1 FROM actor_org_role_binding b
                          WHERE b.tenant_id = a.tenant_id
                            AND b.external_actor_id = a.external_actor_id
                            AND b.org_code = a.org_code
                            AND b.role_code = :new
                            AND b.id != a.id
                      )
                )
                """
            ),
            {"legacy": legacy_code, "new": new_code},
        )
        if delete_result.rowcount > 0:
            log.warning(
                "[D23] dedup-collapse: deleted %d %s bindings already represented as %s "
                "(per-record evidence in audit_event with phase=dedup_delete_on_collapse).",
                delete_result.rowcount,
                legacy_code,
                new_code,
            )

        # Step C: UPDATE 剩余 legacy → new
        update_result = bind.execute(
            sa.text("UPDATE actor_org_role_binding SET role_code = :new WHERE role_code = :legacy"),
            {"legacy": legacy_code, "new": new_code},
        )
        log.info(
            "[D23] role-code migrated: %s -> %s, %d records updated.",
            legacy_code,
            new_code,
            update_result.rowcount,
        )

    # R-003 fix: SQLite 不支持 ALTER TABLE ADD CONSTRAINT CHECK；用 batch_alter_table
    # 在非 SQLite 上等价于 ALTER ADD CONSTRAINT，在 SQLite 上自动 recreate table 注入 CHECK。
    allowed_literals = ", ".join(f"'{code}'" for code in _ALLOWED_ROLE_CODES)
    with op.batch_alter_table("actor_org_role_binding") as batch_op:
        batch_op.create_check_constraint(
            "ck_actor_org_role_binding_role_code_d23",
            f"role_code IN ({allowed_literals})",
        )


def downgrade() -> None:
    # D23 retrofit 是单向决策：R1-R8 已退役，不允许回滚。
    # 若需删除 CHECK 约束（调试用），手工执行：
    #   ALTER TABLE actor_org_role_binding DROP CONSTRAINT ck_actor_org_role_binding_role_code_d23;
    raise NotImplementedError(
        "D23: R1-R8 角色码已退役，本迁移不可回滚。"
        "如需调试性删除 CHECK 约束，请参考本函数注释手工执行 DDL。"
    )
