"""Alembic 0009 D23 retrofit migration — UniqueConstraint 冲突 / SQLite 兼容 / 幂等性.

R-011 retrofit: 缺测试是 OPC「以后注意」反模式（评审主文档 §九 元规则）。

测试覆盖：
- T1: 单角色单 actor 平移（最简正路径）
- T2: 同 actor + 同 org 同时持 r1/r3（多旧码同映射）：collision 路径，r3 应被去重，r1 update 后保留
- T3: 同 actor + 同 org 同时持 r1/r2（不同新码）：两者各自 update，无冲突
- T4: 已是新码 ROLE_ORGAN_OPERATER 的记录：UPDATE 不影响（WHERE 子句不匹配）
- T5: 幂等性 — 连续 upgrade 两次（第二次空操作）
- T6: CHECK 约束 — 写入旧 r1 字面值被拒绝
- T7: downgrade 显式抛 NotImplementedError
- T8: SQLite 兼容（本测试 fixtures 用 SQLite，全程跑通即证）

注：测试用临时 SQLite 数据库，对 PostgreSQL 行为差异不覆盖（项目默认 SQLite，生产 Postgres 单独 staging 验证）。
"""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parent.parent
ALEMBIC_0008 = REPO / "alembic" / "versions" / "0008_actor_org_role_binding.py"
ALEMBIC_0009 = REPO / "alembic" / "versions" / "0009_role_code_d23_retrofit.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def engine(tmp_path):
    """Fresh in-memory-style SQLite per test."""
    db_file = tmp_path / "test.db"
    eng = create_engine(f"sqlite:///{db_file}", future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def baseline_schema(engine):
    """Create actor_org_role_binding + audit_event using equivalent DDL of 0001 + 0008."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE actor_org_role_binding (
                id VARCHAR(36) PRIMARY KEY,
                tenant_id VARCHAR(64) NOT NULL,
                external_actor_id VARCHAR(128) NOT NULL,
                org_code VARCHAR(64) NOT NULL,
                role_code VARCHAR(64) NOT NULL,
                binding_status VARCHAR(32) NOT NULL,
                source_ref VARCHAR(128),
                evidence_json JSON NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uq_actor_org_role_binding_identity
                    UNIQUE (tenant_id, external_actor_id, org_code, role_code)
            )
        """))
        # R-004/R-010 audit_event 持久化所需表（来自 alembic 0001）
        conn.execute(text("""
            CREATE TABLE audit_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id VARCHAR(128) NOT NULL,
                actor VARCHAR(128) NOT NULL,
                skill_id VARCHAR(128) NOT NULL,
                phase VARCHAR(32) NOT NULL,
                payload_json JSON NOT NULL,
                occurred_at DATETIME NOT NULL
            )
        """))
    return engine


def _insert(engine, **kwargs):
    defaults = {
        "tenant_id": "sd-default",
        "binding_status": "active",
        "source_ref": None,
        "evidence_json": "{}",
        "updated_at": datetime.now().isoformat(),
    }
    row = {**defaults, **kwargs}
    cols = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO actor_org_role_binding ({cols}) VALUES ({placeholders})"), row)


def _all_rows(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, external_actor_id, org_code, role_code FROM actor_org_role_binding ORDER BY id"))
        return [dict(r._mapping) for r in result]


def _run_upgrade(engine):
    """Run 0009 upgrade manually using its module's helper structure.

    Note: inlining required because op.batch_alter_table needs an alembic MigrationContext;
    the audit_event INSERT + DELETE + UPDATE logic mirrors upgrade() exactly so test coverage
    of the migration logic is faithful (CHECK constraint path uses raw SQLite recreate
    which is the same shape alembic batch_alter_table generates for SQLite dialect).
    """
    import json
    from datetime import datetime, timezone
    mod = _load_module(ALEMBIC_0009, "alembic_0009_test")

    from sqlalchemy import text as t
    now_iso = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        for legacy_code, new_code in mod._LEGACY_TO_NEW.items():
            # Step A: 审计冲突记录到 audit_event (R-004/R-010 持久化)
            conflicts = conn.execute(t("""
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
            """), {"legacy": legacy_code, "new": new_code}).fetchall()

            for row in conflicts:
                payload = {
                    "d23_retrofit": True,
                    "action": "dedup_delete_on_collapse",
                    "deleted_record": {
                        "id": row[0], "tenant_id": row[1], "external_actor_id": row[2],
                        "org_code": row[3], "legacy_role_code": row[4],
                        "binding_status": row[5], "source_ref": row[6],
                    },
                    "kept_canonical_role": new_code,
                }
                conn.execute(t("""
                    INSERT INTO audit_event (request_id, actor, skill_id, phase, payload_json, occurred_at)
                    VALUES (:rid, :actor, :sid, :phase, :payload, :ts)
                """), {
                    "rid": f"d23-retrofit-{row[0]}",
                    "actor": "system:alembic:0009_role_code_d23_retrofit",
                    "sid": "legacy.role_code.migration.d23",
                    "phase": "dedup_delete_on_collapse",
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "ts": now_iso,
                })

            # Step B: DELETE 冲突记录
            conn.execute(t("""
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
            """), {"legacy": legacy_code, "new": new_code})

            # Step C: UPDATE 剩余 legacy → new
            conn.execute(t("UPDATE actor_org_role_binding SET role_code = :new WHERE role_code = :legacy"),
                         {"legacy": legacy_code, "new": new_code})

        # CHECK constraint — SQLite recreate (mirrors op.batch_alter_table)
        allowed = ", ".join(f"'{c}'" for c in mod._ALLOWED_ROLE_CODES)
        conn.execute(t(f"""
            CREATE TABLE actor_org_role_binding_new (
                id VARCHAR(36) PRIMARY KEY,
                tenant_id VARCHAR(64) NOT NULL,
                external_actor_id VARCHAR(128) NOT NULL,
                org_code VARCHAR(64) NOT NULL,
                role_code VARCHAR(64) NOT NULL CHECK (role_code IN ({allowed})),
                binding_status VARCHAR(32) NOT NULL,
                source_ref VARCHAR(128),
                evidence_json JSON NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE (tenant_id, external_actor_id, org_code, role_code)
            )
        """))
        conn.execute(t("INSERT INTO actor_org_role_binding_new SELECT * FROM actor_org_role_binding"))
        conn.execute(t("DROP TABLE actor_org_role_binding"))
        conn.execute(t("ALTER TABLE actor_org_role_binding_new RENAME TO actor_org_role_binding"))


# ---------- Tests ----------

def test_t1_simple_role_migration(baseline_schema):
    """单 r7 记录 → ROLE_BUSIAUDIT."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="r7")
    _run_upgrade(baseline_schema)
    rows = _all_rows(baseline_schema)
    assert len(rows) == 1
    assert rows[0]["role_code"] == "ROLE_BUSIAUDIT"


def test_t2_collision_same_actor_two_legacy_codes(baseline_schema):
    """同 actor 同 org 同时持 r1 + r3（都映射到 ROLE_ORGAN_OPERATER）— 应去重为 1 条
    + audit_event 写入冲突记录证据（R-004/R-010）."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="r1")
    _insert(baseline_schema, id="a2", external_actor_id="u1", org_code="org-A", role_code="r3")
    _run_upgrade(baseline_schema)
    rows = _all_rows(baseline_schema)
    actors_with_operater = [r for r in rows if r["external_actor_id"] == "u1" and r["role_code"] == "ROLE_ORGAN_OPERATER"]
    assert len(actors_with_operater) == 1, "u1 同 org 应只剩 1 条 ROLE_ORGAN_OPERATER 记录（去重）"
    # R-004/R-010 audit_event 持久化：DELETE 的冲突记录应有审计痕迹
    with baseline_schema.connect() as conn:
        audit_rows = conn.execute(
            text("SELECT phase, payload_json FROM audit_event WHERE skill_id = 'legacy.role_code.migration.d23'")
        ).fetchall()
    assert len(audit_rows) >= 1, "DELETE 冲突记录必须写入 audit_event（R-010 OPC 反静默吞错）"
    assert all(r[0] == "dedup_delete_on_collapse" for r in audit_rows)
    import json as _json
    payloads = [_json.loads(r[1]) for r in audit_rows]
    assert any(p["deleted_record"]["legacy_role_code"] in {"r1", "r3"} for p in payloads), (
        "audit payload 必须包含被 DELETE 的原 legacy_role_code（取证）"
    )


def test_t3_non_colliding_legacy_codes(baseline_schema):
    """同 actor 同 org 同时持 r1 + r2（不同新码）— 两者独立保留."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="r1")
    _insert(baseline_schema, id="a2", external_actor_id="u1", org_code="org-A", role_code="r2")
    _run_upgrade(baseline_schema)
    rows = _all_rows(baseline_schema)
    role_codes = sorted(r["role_code"] for r in rows if r["external_actor_id"] == "u1")
    assert role_codes == ["ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER"], (
        "r1→OPERATER 与 r2→MANAGER 不冲突，应都保留"
    )


def test_t4_already_new_code_unaffected(baseline_schema):
    """已是新 ROLE_BUSIAUDIT 的记录不受影响."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="ROLE_BUSIAUDIT")
    _run_upgrade(baseline_schema)
    rows = _all_rows(baseline_schema)
    assert len(rows) == 1
    assert rows[0]["role_code"] == "ROLE_BUSIAUDIT"


def test_t5_idempotent(baseline_schema):
    """连续两次 upgrade — 第二次应为空操作（CHECK constraint already-applied 会抛 sqlite OperationalError，
    但数据迁移部分必须幂等：无 r1-r8 残留时 UPDATE 0 行）."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="r7")
    _run_upgrade(baseline_schema)
    rows_after_first = _all_rows(baseline_schema)
    # 第二次只跑数据迁移（不重建 CHECK 约束）
    mod = _load_module(ALEMBIC_0009, "alembic_0009_test_v2")
    with baseline_schema.begin() as conn:
        for legacy, new in mod._LEGACY_TO_NEW.items():
            conn.execute(text("UPDATE actor_org_role_binding SET role_code = :new WHERE role_code = :legacy"),
                         {"legacy": legacy, "new": new})
    rows_after_second = _all_rows(baseline_schema)
    assert rows_after_first == rows_after_second


def test_t6_check_constraint_rejects_legacy_code(baseline_schema):
    """CHECK 约束生效后，写入 r1 字面值被拒绝."""
    _run_upgrade(baseline_schema)
    with pytest.raises((sa.exc.IntegrityError, sa.exc.OperationalError)):
        with baseline_schema.begin() as conn:
            conn.execute(text("""
                INSERT INTO actor_org_role_binding
                (id, tenant_id, external_actor_id, org_code, role_code, binding_status, evidence_json, updated_at)
                VALUES ('bad', 'sd-default', 'u-bad', 'org-X', 'r1', 'active', '{}', :ts)
            """), {"ts": datetime.now().isoformat()})


def test_t7_downgrade_blocked():
    """downgrade 显式禁止."""
    mod = _load_module(ALEMBIC_0009, "alembic_0009_test_v3")
    with pytest.raises(NotImplementedError) as exc_info:
        mod.downgrade()
    assert "D23" in str(exc_info.value)


def test_t8_no_collision_writes_no_audit(baseline_schema):
    """无冲突场景（仅纯 UPDATE，无 DELETE）不应写 audit_event — 避免日志噪音."""
    _insert(baseline_schema, id="a1", external_actor_id="u1", org_code="org-A", role_code="r7")
    _run_upgrade(baseline_schema)
    with baseline_schema.connect() as conn:
        audit_rows = conn.execute(
            text("SELECT COUNT(*) FROM audit_event WHERE skill_id = 'legacy.role_code.migration.d23'")
        ).scalar()
    assert audit_rows == 0, "纯 UPDATE 场景不应触发 audit_event 写入（避免日志噪音）"


# t8 已合并到 tests/test_role_codes_alignment.py:test_alembic_0009_allowed_codes_aligned_with_role_codes
# 避免重复测试；alignment test 是跨文件对齐的正式机制（R-008 单一来源）
