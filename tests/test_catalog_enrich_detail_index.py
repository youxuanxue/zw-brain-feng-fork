# Wave: 1
# Journey: J1
# Pages: P3 目录详情
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/services/catalog_service.py
"""catalog `enrich_detail` no-context 分支改索引取数等价守卫 (缺陷3b).

M3 把 enrich_detail(context=None) 分支里
`[item for item in list_assets(tenant) if item.catalog_code == catalog_code]`
换成 `list_assets_by_catalog(catalog_code)` 索引下推。本测试在多目录多资源
shadow DB 上锁定: 改后 detail["resourceAssets"] 与旧整租户筛逐字节一致
(同 tenant + catalog_code 等值 + order_by resource_code)。

自建小规模真库 (repository 真灌库), 不依赖客户 dump seed。

PG 迁移后：DB 由根 conftest 的 function-scoped 空克隆（已 alembic upgrade head 建表）
供给，本模块只负责把小规模 fixture 数据灌进每个测试自己的空克隆。无需 SEED_DB /
SHADOW_DB / reset_and_upgrade —— schema 已就绪、跨测试天然隔离。
"""
from __future__ import annotations

import pytest

TENANT = "sd-default"

CATALOGS = [f"basic-elem:cat-{i}" for i in range(3)]


@pytest.fixture(autouse=True)
def _seed_db():
    _seed()
    yield


def _seed() -> None:
    """Each catalog gets a varying number of resources; resource_codes are
    deliberately interleaved across catalogs so a tenant-wide order_by(
    resource_code) does NOT coincide with per-catalog insertion order — this
    catches an index getter that drops or reorders rows."""
    from zw_brain.domain.repositories import CatalogRepository, ResourceApiRepository

    cat_repo = CatalogRepository()
    asset_repo = ResourceApiRepository()

    for ci, catalog in enumerate(CATALOGS):
        cat_repo.upsert_from_resource(
            {
                "id": catalog,
                "name": f"测试目录 {ci}",
                "status": "active",
                "provider": f"org-{ci}",
                "source_ref": f"t:catalog:{ci}",
                "legacy_object_ref": catalog,
            },
            tenant_id=TENANT,
        )
        cat_repo.upsert_item(
            {
                "item_code": f"{catalog}:field-0",
                "catalog_code": catalog,
                "title": "字段0",
                "item_kind": "field",
                "display_order": 0,
                "summary_json": {},
            },
            tenant_id=TENANT,
        )

    # interleave resource codes: rc-00 cat0, rc-01 cat1, rc-02 cat2, rc-03 cat0 ...
    for n in range(15):
        catalog = CATALOGS[n % len(CATALOGS)]
        asset_repo.upsert_asset(
            {
                "resource_code": f"rc-{n:02d}",
                "title": f"资源 {n}",
                "resource_kind": "api",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{n % 3}",
                "catalog_code": catalog,
                "source_ref": f"t:res:{n}",
                "legacy_object_ref": f"rc-{n:02d}",
            },
            tenant_id=TENANT,
        )


def _store():
    from zw_brain.shared.database_store import DatabaseStore

    return DatabaseStore()


def _catalog_service(store):
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    ss = StateStore(database_store=store)
    brain = BrainService(state_store=ss)
    return brain._get_handler_deps().services.catalog


def _old_asset_records(store, catalog_code):
    """The pre-M3 whole-tenant-load-then-Python-filter behavior."""
    return [
        item
        for item in store.resource_api_repo.list_assets(tenant_id=TENANT)
        if item.catalog_code == catalog_code
    ]


def test_enrich_detail_no_context_resource_assets_byte_identical():
    store = _store()
    svc = _catalog_service(store)
    for catalog in CATALOGS:
        record = store.catalog_repo.get_entry(catalog, tenant_id=TENANT)
        assert record is not None
        detail: dict = {}
        svc.enrich_detail(detail, record, store, context=None)
        new_codes = [r["resource_code"] for r in detail["resourceAssets"]]
        old_codes = [r.resource_code for r in _old_asset_records(store, catalog)]
        assert new_codes == old_codes, (
            f"catalog {catalog}: resourceAssets {new_codes} != old whole-tenant filter {old_codes}"
        )
        # non-empty for at least the catalogs we seeded resources into
        assert new_codes, f"catalog {catalog} expected ≥1 resource asset"


def test_enrich_detail_no_context_index_getter_le_tenant_total():
    """The index getter must return ≤ the whole-tenant asset count (pushdown)."""
    store = _store()
    tenant_total = len(store.resource_api_repo.list_assets(tenant_id=TENANT))
    for catalog in CATALOGS:
        scoped = store.resource_api_repo.list_assets_by_catalog(catalog, tenant_id=TENANT)
        assert len(scoped) <= tenant_total
        assert len(scoped) < tenant_total, "per-catalog subset must be strictly smaller than tenant total"


def test_enrich_detail_no_context_snapshots_pushdown(monkeypatch):
    """PERF-1: no-context 分支取 schema snapshots 必须下推 resource_codes（SQL IN），
    不再全表扫整租户 snapshot 后 Python 过滤。守 catalog_service.py 调用点不回潮。"""
    from zw_brain.domain.repositories import MetadataEvidenceRepository

    calls: list[dict] = []
    orig = MetadataEvidenceRepository.list_schema_snapshots

    def _spy(self, *args, **kwargs):
        calls.append(kwargs)
        return orig(self, *args, **kwargs)

    monkeypatch.setattr(MetadataEvidenceRepository, "list_schema_snapshots", _spy)

    store = _store()
    svc = _catalog_service(store)
    record = store.catalog_repo.get_entry(CATALOGS[0], tenant_id=TENANT)
    assert record is not None
    svc.enrich_detail({}, record, store, context=None)

    snap_calls = [c for c in calls if "resource_codes" in c]
    assert snap_calls, f"list_schema_snapshots 未被下推调用（疑全表扫回潮）：{calls}"
    for c in calls:
        # 裸全表扫 fallback 会省略 resource_codes kwarg → None；下推必非 None。
        assert c.get("resource_codes") is not None, f"全表扫 fallback 残留：{c}"
