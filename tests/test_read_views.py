"""ReadViews contract tests — Action C (PR #137).

The CQRS read facade has two distinct method families that look similar but
behave differently. These tests pin down the contract so future refactors
can't silently flip semantics:

A. **Bulk / deepcopy reads** (``list_all``, ``get``, ``list_*``, ``get_*``):
   return copies — handler-side mutation must NOT propagate to the live
   snapshot（或 DB，Action D 后申请/审批/交付列表态从库现算）。The two
   per-entity ``get_*_by_id`` lookups (``DisputesView.get_dispute_by_id`` and
   ``ResourcesView.get_api_resource``) also live here — the ``get_`` prefix
   signals deepcopy semantics even though the surface is a single entity.

B. **Per-entity live lookups** (``find_by_id`` on RequestsView /
   PackagesView / DeliveryView; ``find_by_request_id`` on DeliveryView):
   return a per-dispatch live card — handler-side mutation IS persisted by
   the write bracket（Action D：CardSession identity map + flush 落库；
   PackagesView 仍是快照活引用）。

C. **NotFoundError contract**: the three live lookup helpers
   (requests / packages / delivery#find_by_id) raise NotFoundError on miss;
   ``find_by_request_id`` / ``get_dispute_by_id`` / ``get_api_resource``
   return ``None``.
"""
from __future__ import annotations

import pytest

from zw_brain.command.brain import BrainService, NotFoundError
from zw_brain.command.views import ReadViews

TENANT = "sd-default"


@pytest.fixture(scope="module")
def brain() -> BrainService:
    """Single in-memory BrainService for the whole module; no DB needed."""
    return BrainService()


@pytest.fixture(scope="module")
def views(brain: BrainService) -> ReadViews:
    return ReadViews.from_brain(brain)


@pytest.fixture()
def db_brain():
    """Fresh DB-backed brain（Action D：申请/交付 find_by_id 走 CardSession + DB）。

    The autouse conftest fixture supplies a fresh, migrated per-test PostgreSQL clone."""
    from zw_brain.shared import db as db_module
    from zw_brain.shared.migrate import ensure_runtime_schema

    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    ensure_runtime_schema()

    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    store = DatabaseStore()
    store.application_repo.upsert_from_request(
        {"id": "appRV001", "status": "pending", "applicant": "张三", "applicantDept": "测试单位", "resourceName": "读视图测试资源"},
        tenant_id=TENANT,
    )
    store.delivery_repo.upsert_from_delivery(
        {"id": "DLV-appRV001", "requestId": "appRV001", "status": "pending", "channel": "api_gateway"},
        tenant_id=TENANT,
    )
    yield BrainService(state_store=StateStore(database_store=store))
    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()


# ── §A bulk reads: deepcopy isolation ──────────────────────────────────────


def test_requests_list_all_returns_deepcopy(db_brain: BrainService) -> None:
    """Action D：list_all 从 DB 现算只读副本——变更副本不得落库、不得进会话。"""
    db_views = ReadViews.from_brain(db_brain)
    listed = db_views.requests.list_all()
    assert listed, "db_brain fixture seeds one request"
    listed[0]["__view_sentinel"] = "view_test_should_not_propagate"
    listed[0]["status"] = "granted"
    db_brain._card_session.flush()
    store = db_brain._state_store.database_store
    rec = store.application_repo.get_record("appRV001", tenant_id=TENANT)
    assert rec.status == "pending", "list_all 副本变更不得经会话落库"
    assert "__view_sentinel" not in (rec.payload_json or {})


def test_packages_list_all_returns_deepcopy(brain: BrainService, views: ReadViews) -> None:
    listed = views.packages.list_all()
    if not listed:
        pytest.skip("seed snapshot has no capability_packages")
    listed[0]["__view_sentinel"] = "x"
    assert all("__view_sentinel" not in r for r in brain._snapshot["capability_packages"]), (
        "PackagesView.list_all leaked a mutable reference into brain._snapshot"
    )


def test_provider_get_returns_deepcopy(brain: BrainService, views: ReadViews) -> None:
    provider = views.provider.get()
    provider["__view_sentinel"] = "x"
    assert "__view_sentinel" not in brain._snapshot.get("provider", {}), (
        "ProviderView.get leaked a mutable reference into brain._snapshot['provider']"
    )


def test_discovery_get_resources_returns_deepcopy(brain: BrainService, views: ReadViews) -> None:
    resources = views.discovery.get_resources()
    if not resources:
        pytest.skip("seed snapshot has no discovery.resources")
    resources[0]["__view_sentinel"] = "x"
    live = brain._snapshot.get("discovery", {}).get("resources", [])
    assert all("__view_sentinel" not in r for r in live), (
        "DiscoveryView.get_resources leaked a mutable reference"
    )


def test_discovery_get_recall_dictionary_returns_deepcopy(brain: BrainService, views: ReadViews) -> None:
    """R-007 sweep target — data_search.py now reads recall dict via this view."""
    recall = views.discovery.get_recall_dictionary()
    recall["__view_sentinel"] = "x"
    live = brain._snapshot.get("discovery", {}).get("recallDictionary", {})
    assert "__view_sentinel" not in live, (
        "DiscoveryView.get_recall_dictionary leaked a mutable reference"
    )


def test_resources_list_api_resources_returns_deepcopy(brain: BrainService, views: ReadViews) -> None:
    """R-007 sweep target — data_search.py now reads API resource list via this view."""
    items = views.resources.list_api_resources()
    if not items:
        pytest.skip("seed snapshot has no api_resources")
    items[0]["__view_sentinel"] = "x"
    live = brain._snapshot.get("api_resources", [])
    assert all("__view_sentinel" not in r for r in live), (
        "ResourcesView.list_api_resources leaked a mutable reference"
    )


# ── §B per-entity lookups: live reference ──────────────────────────────────


def test_requests_find_by_id_returns_live_reference(db_brain: BrainService) -> None:
    """Action D：find_by_id 返回 per-dispatch 会话卡——同会话同一实例，变更经 flush 落库。"""
    db_views = ReadViews.from_brain(db_brain)
    card = db_views.requests.find_by_id("appRV001")
    again = db_views.requests.find_by_id("appRV001")
    assert card is again, (
        "RequestsView.find_by_id must return the same per-dispatch card (mutation closures depend on this)"
    )
    card["status"] = "need-fix"
    db_brain._card_session.flush()
    store = db_brain._state_store.database_store
    assert store.application_repo.get_record("appRV001", tenant_id=TENANT).status == "need-fix", (
        "会话卡变更必须经 flush 持久化（写括号语义）"
    )


def test_packages_find_by_id_returns_live_reference(brain: BrainService, views: ReadViews) -> None:
    packages = brain._snapshot["capability_packages"]
    if not packages:
        pytest.skip("seed snapshot has no capability_packages")
    pid = packages[0]["id"]
    record = views.packages.find_by_id(pid)
    assert record is packages[0], (
        "PackagesView.find_by_id must return a live reference"
    )


def test_delivery_find_by_id_returns_live_reference(db_brain: BrainService) -> None:
    """Action D：交付卡同会话同一实例，变更经 flush 落库（state 列权威同步）。"""
    db_views = ReadViews.from_brain(db_brain)
    card = db_views.delivery.find_by_id("DLV-appRV001")
    again = db_views.delivery.find_by_id("DLV-appRV001")
    assert card is again, "DeliveryView.find_by_id must return the same per-dispatch card"
    card["status"] = "granted"
    db_brain._card_session.flush()
    store = db_brain._state_store.database_store
    assert store.delivery_repo.get_task("DLV-appRV001", tenant_id=TENANT).state == "granted"


def test_delivery_find_by_request_id_returns_live_or_none(db_brain: BrainService) -> None:
    """find_by_request_id returns the per-dispatch card on hit, None on miss."""
    db_views = ReadViews.from_brain(db_brain)
    record = db_views.delivery.find_by_request_id("appRV001")
    assert record is not None and record["id"] == "DLV-appRV001"
    assert record is db_views.delivery.find_by_id("DLV-appRV001"), "两种索引须命中同一会话卡"

    # miss returns None
    miss = db_views.delivery.find_by_request_id("REQ-DOES-NOT-EXIST")
    assert miss is None, "miss must return None (not raise)"


# ── §C NotFoundError contract ──────────────────────────────────────────────


def test_requests_find_by_id_raises_on_miss(brain: BrainService, views: ReadViews) -> None:
    """RequestsView.find_by_id (Action E: deps.services.request.by_id) raises NotFoundError."""
    with pytest.raises(NotFoundError):
        views.requests.find_by_id("REQ-DOES-NOT-EXIST")


def test_packages_find_by_id_raises_on_miss(brain: BrainService, views: ReadViews) -> None:
    """PackagesView.find_by_id (Action E: inline snapshot scan) raises NotFoundError."""
    with pytest.raises(NotFoundError):
        views.packages.find_by_id("PKG-DOES-NOT-EXIST")


def test_delivery_find_by_id_raises_on_miss(brain: BrainService, views: ReadViews) -> None:
    """DeliveryView.find_by_id (Action E: deps.services.delivery.by_id) raises NotFoundError."""
    with pytest.raises(NotFoundError):
        views.delivery.find_by_id("DLV-DOES-NOT-EXIST")


def test_get_api_resource_returns_none_on_miss(brain: BrainService, views: ReadViews) -> None:
    """ResourcesView.get_api_resource returns None on miss (does not raise)."""
    result = views.resources.get_api_resource("API-DOES-NOT-EXIST")
    assert result is None


def test_get_dispute_by_id_returns_none_on_miss(brain: BrainService, views: ReadViews) -> None:
    """DisputesView.get_dispute_by_id returns None on miss (does not raise)."""
    result = views.disputes.get_dispute_by_id("DSP-DOES-NOT-EXIST")
    assert result is None


# ── §D get_*_by_id deepcopy semantics (R-010 rename guard) ────────────────


def test_disputes_get_dispute_by_id_returns_deepcopy_not_live(
    brain: BrainService, views: ReadViews
) -> None:
    """DisputesView.get_dispute_by_id must return deepcopy (mutation does NOT propagate).

    Pins the §A contract for the ``get_*_by_id`` family — R-010 renamed
    ``DisputesView.find_by_id`` → ``get_dispute_by_id`` to make the deepcopy
    semantics explicit by name. This test guards the contract.
    """
    disputes = brain._snapshot.get("disputes", [])
    if not disputes:
        pytest.skip("seed snapshot has no disputes")
    did = disputes[0].get("id")
    if did is None:
        pytest.skip("seed dispute entry has no id")
    record = views.disputes.get_dispute_by_id(did)
    assert record is not None
    assert record is not disputes[0], (
        "DisputesView.get_dispute_by_id must return deepcopy — name signals §A contract"
    )
    sentinel = "__get_dispute_deepcopy_sentinel"
    record[sentinel] = "isolated"
    assert sentinel not in disputes[0], (
        "DisputesView.get_dispute_by_id leaked a mutable reference into brain._snapshot['disputes']"
    )


def test_resources_get_api_resource_returns_deepcopy_not_live(
    brain: BrainService, views: ReadViews
) -> None:
    """ResourcesView.get_api_resource must return deepcopy / fresh dict (no in-place propagation).

    R-010 renamed ``ResourcesView.find_api_resource`` → ``get_api_resource``
    because the underlying ``provider.find_api_resource`` (Action E:
    lifted from brain._find_api_resource) deepcopies the in-memory fallback
    and returns a freshly-serialized dict for DB-backed lookups. This test
    pins both behaviors so a future Action D/E rewrite can't silently flip
    semantics.
    """
    items = brain._snapshot.get("api_resources", [])
    if not items:
        pytest.skip("seed snapshot has no api_resources")
    code = items[0].get("resource_code") or items[0].get("id")
    if code is None:
        pytest.skip("seed api resource entry has no resource_code/id")
    record = views.resources.get_api_resource(code)
    assert record is not None
    assert record is not items[0], (
        "ResourcesView.get_api_resource must return deepcopy / fresh dict — name signals §A contract"
    )
    sentinel = "__get_api_resource_deepcopy_sentinel"
    record[sentinel] = "isolated"
    assert sentinel not in items[0], (
        "ResourcesView.get_api_resource leaked a mutable reference into brain._snapshot['api_resources']"
    )


# ── §D ReadViews frozen + facet coverage ───────────────────────────────────


def test_read_views_is_frozen() -> None:
    """ReadViews itself is @dataclass(frozen=True) — facet handles must not mutate."""
    assert ReadViews.__dataclass_params__.frozen, (
        "ReadViews must be @dataclass(frozen=True); see HandlerDeps frozen invariant."
    )


def test_read_views_exposes_all_facets(views: ReadViews) -> None:
    """ReadViews facet 集合钉死（Action D：approvals 视图因零消费者删除——
    审批卡读取走 services.request.approval_by_id + enrich_approvals_snapshot）。"""
    expected = {
        "workbench", "discovery", "requests", "delivery",
        "resources", "provider", "disputes", "audit_events", "zones",
        "packages", "tickets", "knowledge", "alerts", "audit_ai",
    }
    actual = {f.name for f in ReadViews.__dataclass_fields__.values()}
    assert actual == expected, (
        f"ReadViews facet drift — expected {expected}, got {actual}"
    )
