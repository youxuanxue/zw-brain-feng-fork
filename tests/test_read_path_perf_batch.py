# Wave: 1
# Journey: J1/J2
# Pages: P2 发现 / P7 共享专区
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/services/topic_package_service.py
#   zw_brain/domain/services/catalog_service.py
#   zw_brain/command/handlers/j2/topic_package.py
#   zw_brain/command/handlers/j1/data_search.py
"""读路径 N+1 消除 + 投影形状不变守卫.

锁定 topic.package.query / data.search 列表投影改为「一次性 batch 预取 + O(1) 查找」后：
1. session 数随包/命中数 *亚线性* 增长（防回潮 per-package / per-hit N+1）；
2. catalog→package 反查走 ref_type/ref_id 索引（list_packages_referencing）等价于旧全表遍历；
3. 列表投影字段集与详情投影字段集与改前一致（契约形状不破，5 消费面共享）。

自建小规模真库（reset_and_upgrade + 经 repository 真灌库），不依赖客户 dump seed；
业务正确性回归仍由 tests/integration/test_wave2_topic_package_* 在 3 标杆真数据上守。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHADOW_DB = REPO_ROOT / ".data" / "test_read_path_perf_batch_shadow.db"
TENANT = "sd-default"

# Expected list-projection contract field set (the keys topic.package.query list
# items carry today). Locking this prevents a future "lightweight projection"
# from silently dropping a field a consumer face reads.
LIST_PROJECTION_KEYS = {
    "package_code",
    "title",
    "scenario",
    "status",
    "projectionKind",
    "projectionStatus",
    "projectionFailureReasons",
    "visibleOrgCount",
    "visibleOrgs",
    "applicationBoundary",
    "authorizationStatus",
    "activeCatalogCount",
    "hiddenCatalogCount",
    "sourceFact",
    "isSubscribed",
}


def _remove_shadow_db_files() -> None:
    for suffix in ("", "-wal", "-shm"):
        (SHADOW_DB.parent / f"{SHADOW_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="module", autouse=True)
def _shadow_db():
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    from zw_brain.shared import db as _db

    # Save prior env so teardown RESTORES it (not blindly pops) — keeps this
    # module from polluting later tests that rely on the default seed DB or on
    # an outer fixture's ZW_BRAIN_DB_PATH (test-db-path-isolation debt).
    prior_db_path = os.environ.get("ZW_BRAIN_DB_PATH")
    prior_db_url = os.environ.get("ZW_BRAIN_DATABASE_URL")

    _db.reset_engine_cache()
    _remove_shadow_db_files()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade

    reset_and_upgrade()
    _seed(packages=24, catalogs=40)
    yield
    _remove_shadow_db_files()
    # Restore env to its prior state, THEN reset the cache last so the next
    # consumer rebuilds the engine against the restored path.
    if prior_db_path is None:
        os.environ.pop("ZW_BRAIN_DB_PATH", None)
    else:
        os.environ["ZW_BRAIN_DB_PATH"] = prior_db_path
    if prior_db_url is not None:
        os.environ["ZW_BRAIN_DATABASE_URL"] = prior_db_url
    _db.reset_engine_cache()


def _seed(*, packages: int, catalogs: int) -> None:
    from zw_brain.domain.repositories import (
        CatalogRepository,
        ResourceApiRepository,
        TopicPackageRepository,
    )

    cat_repo = CatalogRepository()
    asset_repo = ResourceApiRepository()
    tp_repo = TopicPackageRepository()

    for ci in range(catalogs):
        code = f"basic-elem:t-{ci:04d}"
        cat_repo.upsert_from_resource(
            {
                "id": code,
                "name": f"法人 测试目录 {ci}",
                "status": "active",
                "provider": f"org-{ci % 8}",
                "source_ref": f"t:catalog:{ci}",
                "legacy_object_ref": code,
            },
            tenant_id=TENANT,
        )
        asset_repo.upsert_asset(
            {
                "resource_code": f"res-t-{ci:04d}",
                "title": f"测试资源 {ci}",
                "resource_kind": "dataset",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{ci % 8}",
                "catalog_code": code,
                "source_ref": f"t:resource:{ci}",
                "legacy_object_ref": f"res-t-{ci:04d}",
            },
            tenant_id=TENANT,
        )
        cat_repo.upsert_item(
            {
                "item_code": f"{code}:field-0",
                "catalog_code": code,
                "title": "字段0",
                "item_kind": "field",
                "display_order": 0,
                "summary_json": {},
            },
            tenant_id=TENANT,
        )

    for pi in range(packages):
        code = f"tp-t-{pi:04d}"
        c0 = f"basic-elem:t-{(pi * 2) % catalogs:04d}"
        c1 = f"basic-elem:t-{(pi * 2 + 1) % catalogs:04d}"
        tp_repo.create_package(
            {
                "package_code": code,
                "title": f"测试专题包 {pi}",
                "scenario": "测试场景",
                "status": "draft",
                "display_snapshot_json": {"projection_kind": "topic_package"},
                "source_ref": f"t:tp:{pi}",
            },
            tenant_id=TENANT,
        )
        tp_repo.configure_package(
            code,
            {
                "items": [
                    {"ref_type": "catalog_entry", "ref_id": c0, "title": "目录1", "display_order": 0},
                    {"ref_type": "catalog_entry", "ref_id": c1, "title": "目录2", "display_order": 1},
                ],
                "visibility": [
                    {"org_code": f"org-{pi % 8}", "role_code": "ROLE_ORGAN_OPERATER", "surface": "webui", "intent": "view", "policy_status": "approved"},
                ],
            },
            tenant_id=TENANT,
        )
        tp_repo.transition_package(code, "submitted", {"action_type": "submit"}, tenant_id=TENANT)
        tp_repo.transition_package(code, "published", {"action_type": "publish"}, tenant_id=TENANT)


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss)


class _SessionCounter:
    """Count create_session_factory() checkouts across all modules."""

    def __enter__(self):
        import sys

        import zw_brain.shared.db as dbmod

        self._orig = dbmod.create_session_factory
        self.count = 0
        counter = self

        def wrapped():
            factory = counter._orig()

            def make():
                counter.count += 1
                return factory()

            return make

        self._patched = []
        for name, mod in list(sys.modules.items()):
            if name.startswith("zw_brain") and getattr(mod, "create_session_factory", None) is not None:
                mod.__dict__["create_session_factory"] = wrapped
                self._patched.append(mod)
        return self

    def __exit__(self, *exc):
        for mod in self._patched:
            mod.__dict__["create_session_factory"] = self._orig


def _query_list(brain, status="published"):
    from zw_brain.command.deps import SkillContext
    from zw_brain.command.handlers.j2 import topic_package as tp

    deps = brain._get_handler_deps()
    ctx = SkillContext(skill_id="topic.package.query", role="ROLE_ORGAN_OPERATER", actor="t", confirmed=False, manifest={})
    return tp._query_topic_packages(brain, deps, ctx, package_code=None, status=status)


# ── 1. topic.package.query list path: session count sub-linear in package count ──

def test_topic_query_list_sessions_sublinear():
    brain = _new_brain()
    out = _query_list(brain)
    n = len(out["items"])
    assert n >= 20, f"seed should publish ~24 packages, got {n}"
    with _SessionCounter() as c:
        _query_list(brain)
    # Old impl: ~14 sessions/package (list_items + list_visibility + per-catalog-item
    # get_entry/list_items/schema_mappings/schema_snapshots + full asset + full delivery
    # re-scan, ×N). New impl: a fixed batch prefetch (≈ a dozen queries) regardless of N.
    assert c.count < n, f"list path issued {c.count} sessions for {n} packages — N+1 regressed"
    # M4 lightweight list contract: the page is a fixed handful of batch queries.
    # Measured 9 on the seed; lock a tight ceiling so a regression that re-introduces
    # any per-package query (e.g. list_projection drifting back to a per-call path)
    # trips this.
    assert c.count <= 12, f"list path should be a fixed handful of queries, got {c.count}"


def test_list_projection_decoupled_from_projection_summary():
    """M4 structural guard (topic-package-query debt close): the list path must
    assemble its contract from the lightweight sub-helpers, NOT route through the
    detail-level ``projection_summary``. We assert the byte-identical equivalence
    holds (list contract == package_to_dict | projection_summary for the same
    inputs) AND that ``list_projection`` does not literally delegate to
    ``projection_summary`` (which would re-couple list to the detail path and
    revive the debt grep)."""
    import inspect

    from zw_brain.domain.services.topic_package_service import TopicPackageService

    # Strip the docstring (which legitimately *mentions* projection_summary in
    # prose) and assert there is no actual `self.projection_summary(` call.
    fn = TopicPackageService.list_projection
    body = inspect.getsource(fn)
    doc = fn.__doc__ or ""
    body_no_doc = body.replace(doc, "")
    assert "self.projection_summary(" not in body_no_doc, (
        "list_projection must not call projection_summary (lightweight list contract)"
    )

    # Equivalence: the list contract dict must equal the package dict unioned with
    # the (shared) projection summary for the same inputs — byte-identical output.
    from zw_brain.domain.serializers import topic_package as tp_ser

    brain = _new_brain()
    svc = brain._get_handler_deps().services.topic_package
    repo = brain._state_store.database_store.topic_package_repo
    record = repo.get_package("tp-t-0000", tenant_id=TENANT)
    items, visibility = svc._list_inputs(record, context=None)
    list_dict = svc.list_projection(record, context=None)
    expected = tp_ser.topic_package_to_dict(record) | svc.projection_summary(record, items, visibility)
    assert list_dict == expected, "list_projection output drifted from package_to_dict | projection_summary"


# ── 2. catalog→package reverse index correctness ──

def test_reverse_index_matches_brute_force():
    brain = _new_brain()
    repo = brain._state_store.database_store.topic_package_repo
    # brute-force: scan every package's items for the catalog ref
    target = "basic-elem:t-0002"
    brute = {
        pkg.package_code
        for pkg in repo.list_packages(tenant_id=TENANT)
        for item in repo.list_items(pkg.package_code, tenant_id=TENANT)
        if item.ref_type == "catalog_entry" and item.ref_id == target
    }
    indexed = set(repo.list_packages_referencing("catalog_entry", target, tenant_id=TENANT))
    assert indexed == brute and brute, f"reverse index {indexed} != brute force {brute}"


def test_reverse_index_absent_code_empty():
    brain = _new_brain()
    repo = brain._state_store.database_store.topic_package_repo
    assert repo.list_packages_referencing("catalog_entry", "basic-elem:does-not-exist", tenant_id=TENANT) == []


# ── 3. data.search topic projection — batch == per-hit (no double compute, no drift) ──

def test_data_search_batch_projection_matches_single():
    brain = _new_brain()
    store = brain._state_store.database_store
    svc = brain._get_handler_deps().services.catalog
    codes = [f"basic-elem:t-{ci:04d}" for ci in range(8)]
    batch = svc.topic_projection_cards_by_catalog(codes, store)
    for code in codes:
        single = svc.topic_projection_cards(code, store)
        # compare as code→status sets (order-independent)
        b = sorted((c["package_code"], c["projectionStatus"]) for c in batch[code])
        s = sorted((c["package_code"], c["projectionStatus"]) for c in single)
        assert b == s, f"batch vs single projection differ for {code}: {b} != {s}"


def test_data_search_sessions_sublinear_in_hits():
    brain = _new_brain()
    from zw_brain.command.handlers.j1 import data_search

    out = data_search.search_resources(brain, "法人", 1)
    hits = out["total"]
    assert hits >= 20, f"expected many catalog hits for 法人, got {hits}"
    with _SessionCounter() as c:
        data_search.search_resources(brain, "法人", 1)
    # Old impl: per-hit topic_projection_cards (×116 packages) computed TWICE → thousands.
    assert c.count <= 30, f"data.search issued {c.count} sessions for {hits} hits — N+1 regressed"


# ── 4. contract shape invariance: list projection field set unchanged ──

def test_list_projection_field_set_stable():
    brain = _new_brain()
    out = _query_list(brain)
    assert out["items"]
    for item in out["items"]:
        missing = LIST_PROJECTION_KEYS - set(item.keys())
        assert not missing, f"list projection dropped contract fields: {missing}"


def test_detail_projection_superset_of_list():
    """Detail view must still carry list fields PLUS the heavy detail fields."""
    from zw_brain.command.deps import SkillContext
    from zw_brain.command.handlers.j2 import topic_package as tp

    brain = _new_brain()
    deps = brain._get_handler_deps()
    ctx = SkillContext(skill_id="topic.package.query", role="ROLE_ORGAN_OPERATER", actor="t", confirmed=False, manifest={})
    detail = tp._query_topic_packages(brain, deps, ctx, package_code="tp-t-0000", status=None)["items"][0]
    for key in LIST_PROJECTION_KEYS:
        assert key in detail, f"detail view lost list field {key}"
    for key in ("items", "visibility", "catalogProjectionItems", "reviews", "evidence", "metrics"):
        assert key in detail, f"detail view missing heavy field {key}"


def test_list_vs_detail_shared_fields_agree():
    """activeCatalogCount / projectionStatus must match between list and detail for the same package."""
    from zw_brain.command.deps import SkillContext
    from zw_brain.command.handlers.j2 import topic_package as tp

    brain = _new_brain()
    list_item = next(it for it in _query_list(brain)["items"] if it["package_code"] == "tp-t-0000")
    deps = brain._get_handler_deps()
    ctx = SkillContext(skill_id="topic.package.query", role="ROLE_ORGAN_OPERATER", actor="t", confirmed=False, manifest={})
    detail = tp._query_topic_packages(brain, deps, ctx, package_code="tp-t-0000", status=None)["items"][0]
    for key in ("activeCatalogCount", "projectionStatus", "visibleOrgCount", "hiddenCatalogCount"):
        assert list_item[key] == detail[key], f"{key} differs list({list_item[key]}) vs detail({detail[key]})"
