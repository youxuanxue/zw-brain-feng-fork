# Wave: 1
# Journey: J1/J2
# Pages: P7 共享专区 / 专题包
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/services/topic_package_service.py
"""topic_package 投影读路径 N+1 消除守卫.

锁定 catalog_projection_items 把 resource_api_repo.list_assets 提到 per-item
循环外：N 个 catalog_entry 目录项原本触发 N 次 list_assets 全表扫 → 1 次。
防回潮「列表跑详情级投影、逐目录项 list_assets 全表」（P7 性能债）。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_topic_projection_perf_shadow.db"
TENANT = "sd-default"

require_real_seed({"catalog_entry": 100, "topic_package": 1})


@pytest.fixture(scope="module", autouse=True)
def _shadow_db() -> None:
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield


@pytest.fixture(scope="module")
def brain():
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore
    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _catalog_entry_items(brain):
    """取一个含 ≥2 个 catalog_entry 目录项的专题包的 item dicts；无则 skip。"""
    from zw_brain.command.serializers import topic_package as ser
    store = brain._state_store.database_store
    repo = store.topic_package_repo
    for pkg in repo.list_packages(tenant_id=TENANT):
        items = [
            ser.topic_item_to_dict(rec)
            for rec in repo.list_items(pkg.package_code, tenant_id=TENANT)
            if rec.ref_type == "catalog_entry"
        ]
        if len(items) >= 2:
            return items
    pytest.skip("无含 ≥2 catalog_entry 目录项的专题包，无法证明 N+1 消除")
    return []


def test_catalog_projection_items_calls_list_assets_once(brain, monkeypatch):
    """N 个目录项只触发 1 次 list_assets（旧实现是 N 次全表扫）。"""
    items = _catalog_entry_items(brain)
    store = brain._state_store.database_store
    calls = {"n": 0}
    real = store.resource_api_repo.list_assets

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(store.resource_api_repo, "list_assets", counting)
    out = brain._get_handler_deps().services.topic_package.catalog_projection_items(items)
    assert calls["n"] == 1, f"list_assets 应每次投影调 1 次（提到循环外），实际 {calls['n']}"
    assert len(out) == len(items)
    for row in out:
        assert "field_count" in row and "resource_count" in row and "visible" in row


def test_catalog_projection_items_resource_count_matches_assets(brain):
    """resource_count 仍正确反映按 catalog_code 命中的 asset 数（分组等价于过滤）。"""
    items = _catalog_entry_items(brain)
    store = brain._state_store.database_store
    all_assets = store.resource_api_repo.list_assets(tenant_id=TENANT)
    out = brain._get_handler_deps().services.topic_package.catalog_projection_items(items)
    for row in out:
        catalog_code = row["catalog_code"]
        expected = sum(1 for a in all_assets if a.catalog_code == catalog_code)
        assert row["resource_count"] == expected
