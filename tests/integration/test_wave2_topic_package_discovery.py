# Wave: 2
# Twin-F: e3.F9
# Covers: F9 P7 共享专区 / 专题包 — J1 专题发现与订阅
"""F9 discovery 集成测试 — query / subscribe / metric.query + 三维可见性 + seed 3 标杆。

真链路：起 BrainService（__init__ 触发 sync → 种 sd-default 3 标杆专题包），经
`invoke_trusted`（模拟 BFF 验证后路径）打 topic.package.* capability。守 D11：3 标杆
引用 #168 已补种的真 catalog_entry，本测试反向断言 seed 定义的 ref_id == query 返回 ref_id
（标杆数据单一源 = seed_snapshot.json topic_packages，不另存 fixture 副本）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F9_topic_discovery_shadow.db"
SEED = REPO_ROOT / "zw_brain" / "domain" / "seed_snapshot.json"
BENCHMARKS = ("tp-yiliao-jiuzhu", "tp-yibao-code", "tp-yidi-jiuyi")


def _remove_shadow_db_files() -> None:
    for suffix in ("", "-wal", "-shm"):
        (SHADOW_DB.parent / f"{SHADOW_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="session", autouse=True)
def _shadow_db() -> None:
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


def _query(brain, payload, role="ROLE_ORGAN_OPERATER"):
    return invoke_trusted(brain, "topic.package.query", payload, role=role)


def test_seed_injects_three_benchmarks_published() -> None:
    """M1 seed 注入：3 山东标杆专题包以 published 终态进库，query 可发现。"""
    brain = _new_brain()
    result = _query(brain, {})
    by_code = {it["package_code"]: it for it in result["items"]}
    for code in BENCHMARKS:
        assert code in by_code, f"{code} 未出现在 topic.package.query 结果"
        assert by_code[code]["status"] == "published", f"{code} 非 published"


def test_query_status_filter() -> None:
    """status 过滤维度生效：只返回 published。"""
    brain = _new_brain()
    result = _query(brain, {"status": "published"})
    assert result["items"]
    assert all(it["status"] == "published" for it in result["items"])


def test_detail_items_are_real_catalog_refs() -> None:
    """守 D11：异地就医专题包详情引用 3 个真 catalog_entry，ref_id 与 seed 定义一致。"""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    z3 = next(p for p in seed["topic_packages"] if p["package_code"] == "tp-yidi-jiuyi")
    expected_refs = {it["ref_id"] for it in z3["items"]}

    brain = _new_brain()
    detail = _query(brain, {"package_code": "tp-yidi-jiuyi"})["items"][0]
    got_refs = {it["ref_id"] for it in detail["items"]}
    assert got_refs == expected_refs
    assert all(ref.startswith("basic-elem:") for ref in got_refs)


def test_three_dimensional_visibility_approved() -> None:
    """三维可见性（org + role + surface/region）以 approved 落库。"""
    brain = _new_brain()
    detail = _query(brain, {"package_code": "tp-yiliao-jiuzhu"})["items"][0]
    approved = [v for v in detail["visibility"] if v["policy_status"] == "approved"]
    assert approved, "缺 approved visibility"
    v = approved[0]
    assert v["org_code"] and v["role_code"] and v["surface"]


def test_subscribe_writes_subscription_visibility() -> None:
    """订阅真写：OPERATER 订阅 → 新增 subscription surface 的 visibility。"""
    brain = _new_brain()
    before = _query(brain, {"package_code": "tp-yibao-code"})["items"][0]
    assert "subscription" not in {v["surface"] for v in before["visibility"]}
    assert before["isSubscribed"] is False  # V1 诚实回显：订阅前未订阅

    res = invoke_trusted(
        brain,
        "topic.package.subscribe",
        {
            "confirmed": True,
            "package_code": "tp-yibao-code",
            "org_code": "ORG-A",
            "role_code": "ROLE_ORGAN_OPERATER",
            "surface": "subscription",
            "intent": "use",
        },
        role="ROLE_ORGAN_OPERATER",
    )
    assert res["ok"] is True

    after = _query(brain, {"package_code": "tp-yibao-code"})["items"][0]
    assert "subscription" in {v["surface"] for v in after["visibility"]}
    assert after["isSubscribed"] is True  # V1 诚实回显：订阅后已订阅


def test_metric_query_returns_summary() -> None:
    """metric.query（MANAGER 岗）返回 items + summary 投影。"""
    brain = _new_brain()
    res = invoke_trusted(
        brain,
        "topic.package.metric.query",
        {"package_code": "tp-yiliao-jiuzhu"},
        role="ROLE_ORGAN_MANAGER",
    )
    assert "items" in res and "summary" in res
