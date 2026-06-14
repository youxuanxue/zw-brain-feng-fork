"""test_alembic_migration_d58 — D58 alembic 回归 + 冷启动不再 DROP.

反转 D23（drop_all+create_all），用 alembic forward-migration 取代「漂移即 DROP」。
核心不变量（隔离临时库逐条钉死）：
  (a) 空库 ensure_runtime_schema() → 全部 75 表 + alembic_version 建好；
  (b) 灌数据的存量库（无 alembic_version、schema 与模型一致）→ stamp baseline 后
      数据**仍在**、绝不 DROP；
  (c) prod 模式 reset_and_upgrade() 无 ALLOW env → raise（M5 fail-closed）；
  (d) upgrade head / ensure_runtime_schema 幂等（重复调用不报错、表数不变）。
另补：真漂移（无版本表 + 有数据 + schema 不一致）→ raise SchemaDriftError（绝不 DROP）。

库隔离：每个测试用 tmp_path 下独立 sqlite + monkeypatch ZW_BRAIN_DATABASE_URL，
配合 root conftest 的 per-test env snapshot + engine-cache reset。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

import zw_brain.domain.models  # noqa: F401 — 注册全部 ORM 表到 Base.metadata
from zw_brain.shared.db import Base, reset_engine_cache
from zw_brain.shared.migrate import (
    REQUIRED_TABLES,
    SchemaDriftError,
    SchemaResetForbiddenError,
    ensure_runtime_schema,
    reset_and_upgrade,
    run_migrations,
)


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """指向 tmp_path 下独立 sqlite 文件的 DB URL（每测独立、引擎缓存清掉）。"""
    db_path = tmp_path / "d58.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ZW_BRAIN_DATABASE_URL", url)
    reset_engine_cache()
    yield url
    reset_engine_cache()


def _table_names(url: str) -> set[str]:
    engine = create_engine(url, future=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _seed_business_rows(url: str) -> None:
    """往一张真实业务表灌一行，模拟存量已部署库（用于 stamp / 防 DROP 断言）。"""
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tenant_projection "
                    "(id, tenant_id, tenant_name, status, profile_json, updated_at) "
                    "VALUES (:id, :tid, :name, :status, :profile, :ts)"
                ),
                {
                    "id": "t-legacy-1",
                    "tid": "sd-default",
                    "name": "山东省",
                    "status": "active",
                    "profile": "{}",
                    "ts": "2026-06-14T00:00:00",
                },
            )
    finally:
        engine.dispose()


def _count_tenant_rows(url: str) -> int:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM tenant_projection")).scalar_one()
    finally:
        engine.dispose()


# ──────────────────────────────────────────────────────────────────────────
# (a) 空库 → 全表建好 + alembic_version
# ──────────────────────────────────────────────────────────────────────────
def test_empty_db_ensure_builds_all_tables(isolated_db: str) -> None:
    assert _table_names(isolated_db) == set(), "前置：库应为空"
    ensure_runtime_schema()
    tables = _table_names(isolated_db)
    assert "alembic_version" in tables, "alembic 应纳管（写入版本表）"
    metadata_tables = set(Base.metadata.tables.keys())
    assert metadata_tables.issubset(tables), (
        f"缺表：{sorted(metadata_tables - tables)}"
    )
    assert REQUIRED_TABLES.issubset(tables), "运行时自检清单全部建好"
    assert len(metadata_tables) == 75, "Base.metadata 应为 75 表（与 baseline 对账）"


# ──────────────────────────────────────────────────────────────────────────
# (b) 灌数据的存量库（无 alembic_version）→ stamp baseline 后数据仍在、不 DROP
# ──────────────────────────────────────────────────────────────────────────
def test_legacy_db_stamped_not_dropped(isolated_db: str) -> None:
    # 1) 先建全 schema（== 存量库的当前形态），但**不**纳管 alembic（手动建表模拟旧 drop&create 库）。
    engine = create_engine(isolated_db, future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    assert "alembic_version" not in _table_names(isolated_db), "前置：存量库无版本表"

    # 2) 灌一行真实业务数据。
    _seed_business_rows(isolated_db)
    assert _count_tenant_rows(isolated_db) == 1

    # 3) ensure_runtime_schema → 走「存量库」分支：stamp baseline + upgrade head（零 DDL）。
    ensure_runtime_schema()

    # 4) 数据**仍在**（绝不 DROP），且 alembic 已纳管。
    assert _count_tenant_rows(isolated_db) == 1, "存量数据被 DROP/清空 = D58 违约"
    assert "alembic_version" in _table_names(isolated_db), "stamp 后应有版本表"

    # 5) 版本号 = baseline revision。
    engine = create_engine(isolated_db, future=True)
    try:
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    from zw_brain.shared.migrate import BASELINE_REVISION

    assert rev == BASELINE_REVISION


# ──────────────────────────────────────────────────────────────────────────
# (c) prod 模式 reset_and_upgrade() 无 ALLOW env → raise（M5 fail-closed）
# ──────────────────────────────────────────────────────────────────────────
def test_reset_forbidden_without_allow_env(isolated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "production")
    monkeypatch.delenv("ZW_BRAIN_ALLOW_SCHEMA_RESET", raising=False)
    with pytest.raises(SchemaResetForbiddenError):
        reset_and_upgrade()


def test_reset_allowed_with_explicit_env(isolated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # 建一张表 + 灌数据，确认显式 reset 真的 drop&rebuild（且不 raise）。
    engine = create_engine(isolated_db, future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    _seed_business_rows(isolated_db)
    assert _count_tenant_rows(isolated_db) == 1

    monkeypatch.setenv("ZW_BRAIN_ALLOW_SCHEMA_RESET", "1")
    reset_and_upgrade()
    # reset = drop 全表后重建 → 数据清空（这是显式承认的破坏性路径），且 alembic 纳管。
    assert _count_tenant_rows(isolated_db) == 0
    assert "alembic_version" in _table_names(isolated_db)


# ──────────────────────────────────────────────────────────────────────────
# (d) 幂等：upgrade head / ensure_runtime_schema 重复调用不报错、表数稳定
# ──────────────────────────────────────────────────────────────────────────
def test_upgrade_head_idempotent(isolated_db: str) -> None:
    run_migrations()
    first = _table_names(isolated_db)
    run_migrations()  # 再次 upgrade head — 应 no-op、不报错
    second = _table_names(isolated_db)
    assert first == second, "重复 upgrade head 不应改变表集合"


def test_ensure_runtime_schema_idempotent(isolated_db: str) -> None:
    ensure_runtime_schema()
    first = _table_names(isolated_db)
    _seed_business_rows(isolated_db)  # 灌数据，确认二次调用不动它
    ensure_runtime_schema()  # 已纳管 → 走 upgrade head 续迁分支，幂等
    second = _table_names(isolated_db)
    assert first == second
    assert _count_tenant_rows(isolated_db) == 1, "二次 ensure 不应 DROP 已有数据"


# ──────────────────────────────────────────────────────────────────────────
# 补：真漂移（无版本表 + 有数据 + schema 不一致）→ raise SchemaDriftError（绝不 DROP）
# ──────────────────────────────────────────────────────────────────────────
def test_real_drift_refuses_not_dropped(isolated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # 造一个「有数据但缺表」的漂移库：只建 tenant_projection 一张表 + 灌数据。
    engine = create_engine(isolated_db, future=True)
    Base.metadata.tables["tenant_projection"].create(bind=engine)
    engine.dispose()
    _seed_business_rows(isolated_db)
    assert _count_tenant_rows(isolated_db) == 1
    assert "alembic_version" not in _table_names(isolated_db)

    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "production")
    with pytest.raises(SchemaDriftError):
        ensure_runtime_schema()
    # 拒启 = 数据原封不动（绝不 DROP）。
    assert _count_tenant_rows(isolated_db) == 1
