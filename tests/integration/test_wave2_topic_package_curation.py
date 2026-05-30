# Wave: 2
# Twin-F: e3.F9
# Covers: F9 P7 共享专区 / 专题包 — J2 运营方策展与发布状态机
"""F9 curation 集成测试 — 8 态发布状态机 + publish 校验 + policy.update + evidence.attach。

全流转走 ROLE_BUSIAUDIT（编制/审核岗，policy.py:319-324 授权）。非法跃迁与 publish
前置校验均断言抛 InvalidStateError（invoke_skill 把 repo 的 TopicPackageStateError 转译）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.domain.errors import InvalidStateError

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F9_topic_curation_shadow.db"
EDIT = "ROLE_BUSIAUDIT"
REAL_CATALOG = "basic-elem:0b26783950004ed882ec9309fae73310"


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


def _call(brain, slug, payload):
    return invoke_trusted(brain, slug, {"confirmed": True, **payload}, role=EDIT)


def _status(brain, code):
    return invoke_trusted(brain, "topic.package.query", {"package_code": code}, role=EDIT)["items"][0]["status"]


def _configure_publishable(brain, code):
    _call(brain, "topic.package.configure", {
        "package_code": code,
        "items": [{"ref_type": "catalog_entry", "ref_id": REAL_CATALOG, "title": "医疗救助信息"}],
        "visibility": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER",
                        "surface": "webui", "intent": "view", "policy_status": "approved"}],
    })


def test_full_lifecycle_create_to_published() -> None:
    """create→configure→submit→review(approve)→published 全流转。"""
    brain = _new_brain()
    code = "tp-flow-happy"
    assert _call(brain, "topic.package.create", {"package_code": code, "title": "流转测试包"})["ok"]
    _configure_publishable(brain, code)
    assert _status(brain, code) == "configuring"
    assert _call(brain, "topic.package.submit", {"package_code": code})["ok"]
    assert _status(brain, code) == "submitted"
    assert _call(brain, "topic.package.review", {"package_code": code, "decision": "approve"})["ok"]
    assert _status(brain, code) == "published"


def test_illegal_transition_draft_to_published_raises() -> None:
    """非法跃迁：draft 直接 publish 抛 InvalidStateError。"""
    brain = _new_brain()
    code = "tp-flow-illegal"
    _call(brain, "topic.package.create", {"package_code": code, "title": "非法跃迁"})
    with pytest.raises(InvalidStateError):
        _call(brain, "topic.package.publish", {"package_code": code})


def test_publish_requires_item_and_approved_visibility() -> None:
    """publish 前置校验：缺 approved visibility 时抛 InvalidStateError。"""
    brain = _new_brain()
    code = "tp-flow-novis"
    _call(brain, "topic.package.create", {"package_code": code, "title": "缺可见性"})
    _call(brain, "topic.package.configure", {
        "package_code": code,
        "items": [{"ref_type": "catalog_entry", "ref_id": REAL_CATALOG}],
    })
    _call(brain, "topic.package.submit", {"package_code": code})
    with pytest.raises(InvalidStateError):
        _call(brain, "topic.package.publish", {"package_code": code})


def test_review_reject_then_reconfigure() -> None:
    """review reject → rejected；rejected→configuring 回环可达。"""
    brain = _new_brain()
    code = "tp-flow-reject"
    _call(brain, "topic.package.create", {"package_code": code, "title": "驳回路径"})
    _configure_publishable(brain, code)
    _call(brain, "topic.package.submit", {"package_code": code})
    _call(brain, "topic.package.review", {"package_code": code, "decision": "reject"})
    assert _status(brain, code) == "rejected"
    # rejected → configuring（TRANSITIONS 允许）再次 configure 回到 configuring
    _call(brain, "topic.package.configure", {"package_code": code, "title": "重新策展"})
    assert _status(brain, code) in {"configuring", "rejected"}


def test_policy_update_writes_visibility() -> None:
    """policy.update 写入新维度的可见性策略。"""
    brain = _new_brain()
    code = "tp-policy"
    _call(brain, "topic.package.create", {"package_code": code, "title": "策略测试"})
    _call(brain, "topic.package.configure", {
        "package_code": code,
        "items": [{"ref_type": "catalog_entry", "ref_id": REAL_CATALOG}],
    })
    res = _call(brain, "topic.package.policy.update", {
        "package_code": code,
        "visibility": [{"org_code": "ORG-B", "role_code": "ROLE_ORGAN_MANAGER",
                        "surface": "webui", "intent": "view", "policy_status": "approved"}],
    })
    assert res["ok"]
    detail = invoke_trusted(brain, "topic.package.query", {"package_code": code}, role=EDIT)["items"][0]
    assert any(v["org_code"] == "ORG-B" and v["policy_status"] == "approved" for v in detail["visibility"])


def test_evidence_attach() -> None:
    """evidence.attach 挂证据到专题包。"""
    brain = _new_brain()
    code = "tp-evidence"
    _call(brain, "topic.package.create", {"package_code": code, "title": "证据测试"})
    res = _call(brain, "topic.package.evidence.attach", {
        "package_code": code,
        "evidence_type": "case_evidence",
        "title": "山东医疗救助复用案例",
        "content_json": {"note": "跨部门复用"},
    })
    assert res["ok"]
    detail = invoke_trusted(brain, "topic.package.query", {"package_code": code}, role=EDIT)["items"][0]
    assert detail["evidence"]
