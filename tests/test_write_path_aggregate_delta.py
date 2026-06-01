# Wave: 1
# Journey: J1
# Pages: P3 application / P3 review
# Consumer-faces: API (brain.invoke_skill write path)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/shared/database_store.py
#   zw_brain/command/sync.py
#   zw_brain/command/pipeline.py
"""HIGH-2 写锁内 O(快照) 全量对账 → O(本次写触达) 增量同步 等价 + 性能守卫.

根因（架构性）：sync_aggregate_tables 被设计成「每次写遍历整个 snapshot 全量
re-upsert」——在每次写的 H3 全局写锁热路径上，临界区成本是 O(快照大小) 而非
O(本次写触达的行)。snapshot 随运行时累积（request.submit 追加 requests），临界区
持锁时长随之膨胀。

修法（保住 H3 正确性）：DatabaseStore 维护 per-entity 内容指纹缓存；
sync_aggregate_tables(full=False)（per-write 默认）只对指纹变化的实体 upsert。
一次「内容不变的 re-upsert」是 no-op，跳过它对 DB 状态观察等价 → 临界区降为
O(本次写改了的实体)。full=True（启动权威同步）忽略缓存全量 re-assert。

本测试锁定：
1. 增量同步（delta）后的 DB 投影 == 全量同步（full）后的 DB 投影（字节级等价）；
2. 无变更的第二次写：per-write 同步对 aggregate 实体发起 0 次 upsert（持锁时长塌缩）；
3. 改 1 个 request：只该 request+approval 重新 upsert（O(touched)）；
4. H3 写锁仍包裹整条链（由 test_h3_snapshot_write_concurrency.py 守，本测试不削弱）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHADOW_DB = REPO_ROOT / ".data" / "test_write_path_aggregate_delta_shadow.db"
TENANT = "sd-default"


def _remove_shadow_db_files() -> None:
    for suffix in ("", "-wal", "-shm"):
        (SHADOW_DB.parent / f"{SHADOW_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="function", autouse=True)
def _shadow_db():
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    from zw_brain.shared import db as _db

    _db.reset_engine_cache()
    _remove_shadow_db_files()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade

    reset_and_upgrade()
    yield
    _db.reset_engine_cache()
    _remove_shadow_db_files()
    os.environ.pop("ZW_BRAIN_DB_PATH", None)


def _new_store():
    from zw_brain.shared.database_store import DatabaseStore

    return DatabaseStore()


class _SessionCounter:
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


def _snapshot_with(requests, deliveries):
    return {
        "requests": requests,
        "approvals": [{"id": r["id"], "suggestion": "建议通过"} for r in requests],
        "delivery_tasks": deliveries,
        "api_resources": [],
        "disputes": [],
        "capability_packages": [],
        "topic_packages": [],
        "zones": [],
    }


def _mk_request(rid, status="pending"):
    return {
        "id": rid,
        "status": status,
        "applicant": "张三",
        "applicantDept": "测试单位",
        "resourceName": f"资源-{rid}",
    }


def _mk_delivery(did, appcode, status="pending"):
    return {
        "id": did,
        "deliveryCode": did,
        "requestId": appcode,
        "applicationCode": appcode,
        "status": status,
        "channel": "api_gateway",
    }


def _db_projection(store) -> str:
    """Serialize the aggregate projection (application + delivery rows) as a
    stable string for byte-level equivalence comparison."""
    apps = [
        {
            "code": r.application_code,
            "status": r.status,
            "applicant": r.applicant_name,
            "org": r.applicant_org,
            "payload": r.payload_json,
        }
        for r in store.application_repo.list_records(tenant_id=TENANT)
    ]
    deliveries = [
        {"code": d.delivery_code, "app": d.application_code, "state": d.state}
        for d in store.delivery_repo.list_tasks(tenant_id=TENANT)
    ]
    apps.sort(key=lambda x: x["code"])
    deliveries.sort(key=lambda x: x["code"])
    return json.dumps({"apps": apps, "deliveries": deliveries}, sort_keys=True, default=str, ensure_ascii=False)


# ── 1. delta == full equivalence ──

def test_delta_sync_db_projection_equals_full_sync():
    requests = [_mk_request(f"REQ-{i:03d}") for i in range(12)]
    deliveries = [_mk_delivery(f"DLV-{i:03d}", f"REQ-{i:03d}") for i in range(12)]
    snapshot = _snapshot_with(requests, deliveries)

    # Path A: delta store — full prime, then mutate two requests + one delivery,
    # then a per-write delta sync.
    store_delta = _new_store()
    store_delta.sync_aggregate_tables(snapshot, full=True)
    snapshot["requests"][0]["status"] = "approved"
    snapshot["requests"][3]["status"] = "rejected"
    snapshot["delivery_tasks"][5]["status"] = "granted"
    store_delta.sync_aggregate_tables(snapshot)  # full=False (per-write)
    delta_projection = _db_projection(store_delta)

    # Path B: a *fresh* store that full-syncs the SAME (mutated) snapshot in one
    # authoritative pass.
    _remove_shadow_db_files()
    from zw_brain.shared import db as _db

    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade

    reset_and_upgrade()
    store_full = _new_store()
    store_full.sync_aggregate_tables(snapshot, full=True)
    full_projection = _db_projection(store_full)

    assert delta_projection == full_projection, "delta sync DB projection diverged from full sync"


# ── 2. no-change write issues zero aggregate upserts (lock-hold collapses) ──

def test_no_change_write_skips_all_aggregate_upserts():
    requests = [_mk_request(f"REQ-{i:03d}") for i in range(20)]
    deliveries = [_mk_delivery(f"DLV-{i:03d}", f"REQ-{i:03d}") for i in range(20)]
    snapshot = _snapshot_with(requests, deliveries)

    store = _new_store()
    store.sync_aggregate_tables(snapshot, full=True)  # prime

    # A subsequent identical sync must not re-upsert any request/delivery.
    import zw_brain.domain.repositories.application as app_mod
    import zw_brain.domain.repositories.delivery as dlv_mod

    upserts = {"req": 0, "dlv": 0}
    orig_req = app_mod.ApplicationRepository.upsert_from_request
    orig_dlv = dlv_mod.DeliveryRepository.upsert_from_delivery

    def wrap_req(self, *a, **k):
        upserts["req"] += 1
        return orig_req(self, *a, **k)

    def wrap_dlv(self, *a, **k):
        upserts["dlv"] += 1
        return orig_dlv(self, *a, **k)

    app_mod.ApplicationRepository.upsert_from_request = wrap_req  # type: ignore[method-assign]
    dlv_mod.DeliveryRepository.upsert_from_delivery = wrap_dlv  # type: ignore[method-assign]
    try:
        store.sync_aggregate_tables(snapshot)  # per-write, no change
    finally:
        app_mod.ApplicationRepository.upsert_from_request = orig_req  # type: ignore[method-assign]
        dlv_mod.DeliveryRepository.upsert_from_delivery = orig_dlv  # type: ignore[method-assign]

    assert upserts == {"req": 0, "dlv": 0}, (
        f"no-change write still re-upserted {upserts} aggregates — delta gate broken"
    )


# ── 3. one changed request → only that entity re-upserts (O(touched)) ──

def test_single_change_write_is_o_touched():
    requests = [_mk_request(f"REQ-{i:03d}") for i in range(20)]
    deliveries = [_mk_delivery(f"DLV-{i:03d}", f"REQ-{i:03d}") for i in range(20)]
    snapshot = _snapshot_with(requests, deliveries)

    store = _new_store()
    store.sync_aggregate_tables(snapshot, full=True)

    snapshot["requests"][7]["status"] = "need-fix"

    import zw_brain.domain.repositories.application as app_mod
    import zw_brain.domain.repositories.delivery as dlv_mod

    touched = {"req": [], "dlv": []}
    orig_req = app_mod.ApplicationRepository.upsert_from_request
    orig_dlv = dlv_mod.DeliveryRepository.upsert_from_delivery

    def wrap_req(self, request, **k):
        touched["req"].append(request["id"])
        return orig_req(self, request, **k)

    def wrap_dlv(self, delivery, **k):
        touched["dlv"].append(delivery.get("id"))
        return orig_dlv(self, delivery, **k)

    app_mod.ApplicationRepository.upsert_from_request = wrap_req  # type: ignore[method-assign]
    dlv_mod.DeliveryRepository.upsert_from_delivery = wrap_dlv  # type: ignore[method-assign]
    try:
        store.sync_aggregate_tables(snapshot)
    finally:
        app_mod.ApplicationRepository.upsert_from_request = orig_req  # type: ignore[method-assign]
        dlv_mod.DeliveryRepository.upsert_from_delivery = orig_dlv  # type: ignore[method-assign]

    assert touched["req"] == ["REQ-007"], f"expected only REQ-007 re-upserted, got {touched['req']}"
    assert touched["dlv"] == [], f"no delivery changed; got {touched['dlv']}"


# ── 4. per-write session count is sub-linear vs snapshot size ──

def test_per_write_sessions_sublinear_in_snapshot_size():
    requests = [_mk_request(f"REQ-{i:03d}") for i in range(50)]
    deliveries = [_mk_delivery(f"DLV-{i:03d}", f"REQ-{i:03d}") for i in range(50)]
    snapshot = _snapshot_with(requests, deliveries)

    store = _new_store()
    with _SessionCounter() as c:
        store.sync_aggregate_tables(snapshot, full=True)
    full_sessions = c.count

    snapshot["requests"][0]["status"] = "approved"
    with _SessionCounter() as c2:
        store.sync_aggregate_tables(snapshot)  # per-write
    delta_sessions = c2.count

    n = len(requests)
    # Full sync touches O(N); per-write delta after a single change must be a
    # small constant (the reference-table guards + the 1 changed request's 2
    # upserts), far below N.
    assert delta_sessions < n, (
        f"per-write delta issued {delta_sessions} sessions for a 1-entity change "
        f"on a {n}-request snapshot (full={full_sessions}) — O(snapshot) regressed"
    )
    assert delta_sessions <= 12, (
        f"per-write delta should be a fixed handful of sessions, got {delta_sessions}"
    )
