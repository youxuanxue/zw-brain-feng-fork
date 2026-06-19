# Wave: 1
# Journey: J1
# Pages: P3 application / P3 review
# Consumer-faces: API (brain.invoke_skill write path)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/command/card_session.py
#   zw_brain/command/pipeline.py
"""Action D 写路径单源化 — CardSession 脏检/落库等价 + 性能守卫.

历史（HIGH-2）：sync_aggregate_tables 曾在每次写的 H3 写锁热路径上「遍历整个
snapshot 全量 re-upsert」申请/审批/交付三聚合，后以指纹增量收敛为 O(touched)。
Action D 把三聚合的快照镜像整体退役——运行时写经 CardSession（per-dispatch
identity map + load 指纹脏检）直落 DB，写成本由构造即 O(本次写触达的卡)。

本测试锁定（承接 HIGH-2 的等价/性能语义，换轴到 CardSession）：
1. 只读触达（get_* 后未变更）→ flush 零 upsert（写锁临界区不为读买单）；
2. 变更 1 张申请卡 → 只该 application（+配对 approval case）落库，且 DB 状态
   与变更内容字节级一致；
3. 新建卡（add_*）必落库；flush 后会话清空，二次 flush 零写；
4. 配对语义：申请卡落库时 approval_case.current_status 随申请状态刷新
   （与退役前镜像循环的 request+approval 配对一致）。
"""
from __future__ import annotations

TENANT = "sd-default"

# PG 迁移后：每个测试自己的空 PG 克隆（已 alembic upgrade head 建表）由根 conftest 的
# function-scoped autouse fixture 供给，跨测试天然隔离。测试体经 CardSession / repo 直写。
# 无需影子库 / 旧库路径环境变量 / reset_and_upgrade —— schema 已就绪。


def _new_store():
    from zw_brain.shared.database_store import DatabaseStore

    return DatabaseStore()


def _new_session(store):
    from zw_brain.command.card_session import CardSession

    return CardSession(lambda: store)


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


def _seed(store, n=6):
    for i in range(n):
        store.application_repo.upsert_from_request(_mk_request(f"app{i:03d}"), tenant_id=TENANT)
        store.delivery_repo.upsert_from_delivery(_mk_delivery(f"DLV-app{i:03d}", f"app{i:03d}"), tenant_id=TENANT)


class _UpsertCounter:
    """Count aggregate upserts on a DatabaseStore's repos (monkeypatch-style)."""

    def __init__(self, store):
        self.store = store
        self.app = self.approval = self.delivery = 0

    def __enter__(self):
        self._orig = (
            self.store.application_repo.upsert_from_request,
            self.store.approval_repo.upsert_from_request_and_approval,
            self.store.delivery_repo.upsert_from_delivery,
        )
        counter = self

        def app_upsert(request, **kw):
            counter.app += 1
            return counter._orig[0](request, **kw)

        def approval_upsert(request, approval, **kw):
            counter.approval += 1
            return counter._orig[1](request, approval, **kw)

        def delivery_upsert(delivery, **kw):
            counter.delivery += 1
            return counter._orig[2](delivery, **kw)

        self.store.application_repo.upsert_from_request = app_upsert
        self.store.approval_repo.upsert_from_request_and_approval = approval_upsert
        self.store.delivery_repo.upsert_from_delivery = delivery_upsert
        return self

    def __exit__(self, *exc):
        self.store.application_repo.upsert_from_request = self._orig[0]
        self.store.approval_repo.upsert_from_request_and_approval = self._orig[1]
        self.store.delivery_repo.upsert_from_delivery = self._orig[2]


# ── 1. 只读触达 → flush 零 upsert ──

def test_read_only_touch_flushes_nothing():
    store = _new_store()
    _seed(store)
    session = _new_session(store)
    assert session.get_request("app000") is not None
    assert session.get_delivery("DLV-app003") is not None
    with _UpsertCounter(store) as c:
        session.flush()
    assert (c.app, c.approval, c.delivery) == (0, 0, 0), "未变更的卡不得产生任何 upsert"


# ── 2. 变更 1 张卡 → 只该卡（+配对 approval）落库 ──

def test_single_change_write_is_o_touched():
    store = _new_store()
    _seed(store)
    session = _new_session(store)
    card = session.get_request("app002")
    _untouched = session.get_request("app004")  # 同会话只读触达，不得连带落库
    card["status"] = "need-fix"
    with _UpsertCounter(store) as c:
        session.flush()
    assert c.app == 1, "只变更的申请卡落库"
    assert c.approval == 1, "配对 approval case 随申请状态刷新"
    assert c.delivery == 0
    rec = store.application_repo.get_record("app002", tenant_id=TENANT)
    assert rec.status == "need-fix"
    assert rec.payload_json.get("status") == "need-fix"
    assert store.application_repo.get_record("app004", tenant_id=TENANT).status == "pending"


# ── 3. 新建卡必落库；flush 后会话清空 ──

def test_added_cards_flush_then_session_drains():
    store = _new_store()
    session = _new_session(store)
    session.add_request(_mk_request("app900", status="draft"))
    session.add_delivery(_mk_delivery("DLV-app900", "app900"))
    with _UpsertCounter(store) as c:
        session.flush()
    assert c.app == 1 and c.delivery == 1
    assert store.application_repo.get_record("app900", tenant_id=TENANT).status == "draft"
    with _UpsertCounter(store) as c2:
        session.flush()
    assert (c2.app, c2.approval, c2.delivery) == (0, 0, 0), "flush 后会话应清空，二次 flush 零写"


# ── 4. 配对语义：approval_case.current_status 随申请状态走 ──

def test_paired_approval_case_follows_request_status():
    store = _new_store()
    _seed(store, n=1)
    session = _new_session(store)
    card = session.get_request("app000")
    card["status"] = "granted"
    session.flush()
    case = store.approval_repo.get_case("app000", tenant_id=TENANT)
    assert case is not None
    assert case.current_status == "granted"
