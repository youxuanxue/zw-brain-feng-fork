# Wave: 1
# Journey: J1
# Pages: P4 交付任务详情（减摩组件）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请人) | ROLE_ORGAN_MANAGER (提供方) | ROLE_BUSIAUDIT
# Trace:
#   .twin/e1-j1-journey/plan.yaml F8
#   zw_brain/command/handlers/j1/delivery_explain.py
#   docs/approved/zw-brain-architecture.md §5.4.4 (减摩组件反约束)
"""F8: P4 交付状态解释助手 — 5 真实 sd-default 交付任务 + 推理降级 + §5.4.4 反约束守卫."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_p4_explain_shadow.db"
TENANT = "sd-default"


def _seed_ready() -> bool:
    if not SEED_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM delivery_task WHERE tenant_id=?",
                (TENANT,),
            ).fetchone()
            return bool(row and row[0] >= 50)
    except sqlite3.OperationalError:
        return False


if not _seed_ready():
    pytest.skip("M0 真灌库 delivery_task 缺位", allow_module_level=True)


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
def real_tasks() -> list[dict]:
    """从真实 sd-default 取 5 条 delivery_task（覆盖 ≥2 个不同 state）."""
    with sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT delivery_code, application_code, state, channel "
            "FROM delivery_task WHERE tenant_id=? LIMIT 5",
            (TENANT,),
        ).fetchall()
    out = [{"delivery_code": r[0], "application_code": r[1], "state": r[2], "channel": r[3]} for r in rows]
    assert len(out) == 5
    return out


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


def _invoke(brain, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_ORGAN_MANAGER")
    out = invoke_trusted(brain, "delivery.status.explain", payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# 5 真实 sd-default 交付任务 fallback 解释
# ──────────────────────────────────────────────────────────────────────


def test_explain_5_real_tasks_fallback(brain, real_tasks):
    for task in real_tasks:
        out = _invoke(brain, {
            "delivery_code": task["delivery_code"],
            "role": "ROLE_ORGAN_OPERATER",
            "enabled": False,
        })
        assert out["source"] == "fallback_rule"
        assert out["delivery_code"] == task["delivery_code"]
        assert out["phase"] == task["state"]
        assert out["phase_label"]
        assert out["phase_description"]
        assert isinstance(out["exception_reasons"], list) and out["exception_reasons"]
        assert isinstance(out["impact_scope"], list) and out["impact_scope"]
        assert out["responsible_role"]
        assert isinstance(out["evidence_sources"], list) and out["evidence_sources"]


def test_explain_by_application_code_also_works(brain, real_tasks):
    """支持用 application_code 反查；当 app_code 对应多条 delivery 时，handler 按
    created_at desc 取最新一条（R-002 fix —— 稳定 UX）。本测试验证返回的
    delivery_code 隶属同 application_code，且当存在多条时确实是 created_at 最新者。"""
    import sqlite3

    sample = real_tasks[0]
    out = _invoke(brain, {
        "application_code": sample["application_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    # 用同 application_code 在原 seed DB 找全部 delivery_code，断言返回值在其中
    with sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT delivery_code FROM delivery_task WHERE tenant_id=? AND application_code=? "
            "ORDER BY created_at DESC",
            (TENANT, sample["application_code"]),
        ).fetchall()
    candidates = [r[0] for r in rows]
    assert candidates, "fixture 期望至少一条 delivery"
    assert out["delivery_code"] in candidates
    # 多 delivery 场景 R-002 守卫：必须返回 created_at 最新者
    assert out["delivery_code"] == candidates[0], (
        f"R-002 fix 失效：app_code={sample['application_code']} 有 {len(candidates)} 条 delivery，"
        f"应返回最新 {candidates[0]}，实际 {out['delivery_code']}"
    )


def test_explain_not_found_returns_hint(brain):
    out = _invoke(brain, {
        "delivery_code": "NOT-EXISTS-DELIVERY",
        "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["status"] == "not_found"
    assert "不存在" in out["hint"]


def test_explain_requires_at_least_one_id(brain):
    with pytest.raises(ValueError, match="required"):
        invoke_trusted(brain, "delivery.status.explain", {}, role="ROLE_ORGAN_OPERATER")


# ──────────────────────────────────────────────────────────────────────
# inference path + 降级
# ──────────────────────────────────────────────────────────────────────


def test_explain_inference_path_returns_structured(brain, monkeypatch, real_tasks):
    from zw_brain.command.handlers.j1 import delivery_explain as de
    from zw_brain.shared.inference.client import ChatResult

    mocked = (
        '{"phase":"pending","phase_label":"待处理",'
        '"phase_description":"提供方部门正在准备数据。",'
        '"exception_reasons":["该任务已 pending 超 3 天"],'
        '"impact_scope":["申请方业务延期"],'
        '"responsible_role":"提供方部门数据负责人",'
        '"evidence_sources":["delivery_task.state=pending","payload.kind=apply_pending_delivery"]}'
    )
    monkeypatch.setattr(de, "_inference_chat",
                        lambda *a, **kw: ChatResult(text=mocked, model="demo"))
    sample = real_tasks[0]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": True,
    })
    assert out["source"] == "inference"
    assert out["phase_label"] == "待处理"
    assert "数据负责人" in out["responsible_role"]
    assert out["evidence_sources"]


def test_explain_inference_error_degrades(brain, monkeypatch, real_tasks):
    from zw_brain.command.handlers.j1 import delivery_explain as de
    from zw_brain.shared.inference.client import InferenceError

    def _raise(*a, **kw):
        raise InferenceError("base_url required")

    monkeypatch.setattr(de, "_inference_chat", _raise)
    sample = real_tasks[1]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["source"] == "fallback_rule"
    assert out["degraded"] is True


def test_explain_inference_invalid_json_degrades(brain, monkeypatch, real_tasks):
    from zw_brain.command.handlers.j1 import delivery_explain as de
    from zw_brain.shared.inference.client import ChatResult

    monkeypatch.setattr(de, "_inference_chat",
                        lambda *a, **kw: ChatResult(text="不是 JSON 的话", model="demo"))
    sample = real_tasks[2]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["source"] == "fallback_rule"
    assert out["degraded"] is True


# ──────────────────────────────────────────────────────────────────────
# §5.4.4 反约束守卫
# ──────────────────────────────────────────────────────────────────────


def test_explain_does_not_return_timeline_events(brain, real_tasks):
    """状态解释 cap 绝不能返回 events / timeline / history 列表（P4 时间线组件职责）."""
    sample = real_tasks[3]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    for forbidden in ("events", "timeline", "history", "audit_events", "receipts"):
        assert forbidden not in out, f"状态解释 cap 不应返回 {forbidden}（§5.4.4 反约束）"


def test_explain_does_not_evaluate_progress(brain, real_tasks):
    """不评价进度 — 输出不应含 progress_score / sla_breach / efficiency 等评价字段."""
    sample = real_tasks[0]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    for forbidden in ("progress_score", "sla_breach", "efficiency_rating", "score"):
        assert forbidden not in out


def test_explain_never_calls_write_cap(brain, monkeypatch, real_tasks):
    """守卫：解释助手绝不能调任何 delivery.exchange.* / delivery.access.grant / .stop / .start 等写 cap."""
    original_invoke = brain.invoke_skill
    forbidden_calls: list[str] = []
    forbidden = (
        "delivery.access.grant", "delivery.exchange.publish", "delivery.exchange.start",
        "delivery.exchange.stop", "delivery.replace_or_cancel", "delivery.trigger_recovery",
        "credential.issue", "approval.case.decide",
    )

    def _spy(skill_id, *args, **kwargs):
        if skill_id in forbidden:
            forbidden_calls.append(skill_id)
            raise AssertionError(f"解释助手禁止调写 cap: {skill_id}")
        return original_invoke(skill_id, *args, **kwargs)

    monkeypatch.setattr(brain, "invoke_skill", _spy)
    sample = real_tasks[4]
    _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    assert forbidden_calls == []


# ──────────────────────────────────────────────────────────────────────
# 证据来源 + audit chain
# ──────────────────────────────────────────────────────────────────────


def test_evidence_sources_reference_delivery_task_fields(brain, real_tasks):
    """evidence_sources 必须基于 delivery_task 字段（不能凭空捏造）."""
    sample = real_tasks[0]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    blob = "\n".join(out["evidence_sources"])
    assert "delivery_task" in blob, "evidence 应引用 delivery_task 字段"
    assert sample["state"] in blob


def test_audit_chain_records_explain(brain, real_tasks):
    sample = real_tasks[1]
    _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    types = [
        e["type"] for e in brain.snapshot()["audit_events"]
        if e.get("target") == sample["delivery_code"]
    ]
    assert "delivery.status.explain" in types
