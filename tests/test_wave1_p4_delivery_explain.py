# Wave: 1
# Journey: J1
# Pages: P4 交付任务详情（减摩组件）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请人) | ROLE_ORGAN_MANAGER (提供方) | ROLE_BUSIAUDIT
# Trace:
#   zw_brain/command/handlers/j1/delivery_explain.py
#   docs/approved/zw-brain-architecture.md §5.4.4 (减摩组件反约束)
"""F8: P4 交付状态解释助手 — 5 真实 sd-default 交付任务 + §5.4.4 反约束守卫.

数据隔离：realistic_pg_module 克隆 zw_realistic_tmpl（含真实旧平台数据），
模板缺位时整模块 skip（承接旧 require_real_seed 数据量门槛语义），writes 落克隆库、
不污染真实模板。
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from tests._pg_realistic import realistic_pg_module  # noqa: F401  (fixture)
from tests._trusted_payload import invoke_trusted
from zw_brain.shared.db import get_database_url

REPO_ROOT = Path(__file__).resolve().parent.parent
TENANT = "sd-default"

# 门槛语义（delivery_task≥50）由 realistic_pg_module 的 skip-when-absent 承接。
pytestmark = pytest.mark.usefixtures("realistic_pg_module")


def _pg_read(sql: str, params: tuple = ()):
    """Read against the cloned realistic PG (app read-path's DB), never a file."""
    url = make_url(get_database_url())
    with psycopg.connect(
        host=url.host, port=url.port, user=url.username,
        password=url.password, dbname=url.database,
    ) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture(scope="module")
def real_tasks() -> list[dict]:
    """从真实 sd-default 取 5 条 delivery_task（覆盖 ≥2 个不同 state）."""
    rows = _pg_read(
        "SELECT delivery_code, application_code, state, channel "
        "FROM delivery_task WHERE tenant_id=%s LIMIT 5",
        (TENANT,),
    )
    out = [{"delivery_code": r[0], "application_code": r[1], "state": r[2], "channel": r[3]} for r in rows]
    assert len(out) == 5
    return out


@pytest.fixture
def brain():
    # Function-scoped: conftest._isolate_db_env clears the audit-bus sink before
    # every test, so the sink must be (re)configured per test.
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
    sample = real_tasks[0]
    out = _invoke(brain, {
        "application_code": sample["application_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    # 用同 application_code 在克隆库找全部 delivery_code，断言返回值在其中
    rows = _pg_read(
        "SELECT delivery_code FROM delivery_task WHERE tenant_id=%s AND application_code=%s "
        "ORDER BY created_at DESC",
        (TENANT, sample["application_code"]),
    )
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
# enabled=true — 仍走本地确定性解释
# ──────────────────────────────────────────────────────────────────────


def test_explain_enabled_true_uses_local_rule(brain, real_tasks):
    sample = real_tasks[0]
    out = _invoke(brain, {
        "delivery_code": sample["delivery_code"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": True,
    })
    assert out["source"] == "fallback_rule"
    assert out["enabled"] is True
    assert "degraded" not in out
    assert out["phase"] == sample["state"]
    assert out["phase_label"]
    assert out["evidence_sources"]


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
    feed = brain.snapshot()["audit_events"]
    types = [e["type"] for e in feed if e.get("target") == sample["delivery_code"]]
    assert "delivery.status.explain" in types
    # Action F lock: handler attributes the audit feed to the per-request
    # trusted-session actor (ctx.actor), never the dead _ui_state "system" constant.
    explain_actor = next(
        e["actor"] for e in feed
        if e.get("target") == sample["delivery_code"] and e["type"] == "delivery.status.explain"
    )
    assert explain_actor != "system"
    assert explain_actor == "test-actor:role_organ_operater"
