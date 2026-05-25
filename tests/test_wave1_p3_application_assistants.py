# Wave: 1
# Journey: J1
# Pages: P3 申请草拟 + 审批（减摩组件）
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER (申请人) | ROLE_ORGAN_MANAGER (审批人) | ROLE_BUSIAUDIT
# Trace:
#   .twin/e1-j1-journey/plan.yaml F7
#   zw_brain/command/handlers/j1/application_assistants.py
#   docs/approved/zw-brain-architecture.md §5.4.4 (减摩组件反约束)
"""F7: P3 申请双助手 — 草拟 + 审批依据 + 推理降级 + 不替人提交/决策守卫."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from tests._seed_guard import require_real_seed
from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_wave1_p3_assistants_shadow.db"
TENANT = "sd-default"

require_real_seed({"application_record": 100})


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
def real_apply_samples() -> list[dict]:
    """从真实 sd-default 取 5 条 kind=apply, status=approved 的申请."""
    with sqlite3.connect(f"file:{SHADOW_DB}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT application_code, status, payload_json "
            "FROM application_record WHERE tenant_id=? "
            "  AND json_extract(payload_json,'$.kind')='apply' "
            "  AND status='approved' LIMIT 5",
            (TENANT,),
        ).fetchall()
    out = []
    for code, status, pj in rows:
        payload = json.loads(pj) if isinstance(pj, str) else pj
        out.append({
            "application_code": code,
            "status": status,
            "resource_name": payload.get("resource_name") or "",
            "applicant_org": payload.get("applicant_org_name") or "",
            "use_reason": payload.get("use_reason") or "",
            "purpose": payload.get("purpose") or payload.get("use_reason") or "",
        })
    assert len(out) == 5, "sd-default expected ≥5 approved apply records"
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


def _invoke(brain, skill_id: str, payload: dict) -> dict:
    role = payload.pop("role", "ROLE_ORGAN_MANAGER")
    out = invoke_trusted(brain, skill_id, payload, role=role)
    if isinstance(out, dict) and "result" in out and "audit_id" in out:
        return out["result"]
    return out


# ──────────────────────────────────────────────────────────────────────
# application.draft.suggest — 5 个真实样例
# ──────────────────────────────────────────────────────────────────────


def test_draft_suggest_5_real_samples_fallback(brain, real_apply_samples):
    """5 个真实 sd-default 申请，关闭推理走 fallback 草拟."""
    for sample in real_apply_samples:
        out = _invoke(brain, "application.draft.suggest", {
            "resource_name": sample["resource_name"],
            "applicant_org": sample["applicant_org"],
            "use_case": "",
            "role": "ROLE_ORGAN_OPERATER",
            "enabled": False,
        })
        assert out["source"] == "fallback_rule"
        assert out["suggested_fields"]["use_reason"] in ("行政依据", "审批办理", "信用核查", "其他")
        assert out["risk_band"] in ("low", "medium", "high")
        assert isinstance(out["risk_factors"], list) and out["risk_factors"]
        assert isinstance(out["missing_fields"], list) and out["missing_fields"]
        assert out["reasoning"]


def test_draft_suggest_high_risk_keyword_lifts_score(brain):
    out = _invoke(brain, "application.draft.suggest", {
        "resource_name": "户籍敏感个人信息库",
        "applicant_org": "公安局信息处",
        "use_case": "公安系统行政依据",
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    assert out["risk_band"] == "high"
    assert out["risk_score"] >= 70
    assert any("敏感" in f or "公安" in f for f in out["risk_factors"])


def test_draft_suggest_inference_path_returns_structured(brain, monkeypatch):
    from zw_brain.command.handlers.j1 import application_assistants as aa
    from zw_brain.shared.inference.client import ChatResult

    mocked = (
        '{"suggested_fields":{"purpose":"信用核查","use_reason":"信用核查","use_item":"信用查询",'
        '"service_times":500,"service_times_unit":"次/日","use_region":"济南"},'
        '"risk_score":55,"risk_band":"medium","risk_factors":["涉及个人信用数据"],'
        '"missing_fields":["数据脱敏方案"],"recommended_use_reasons":["信用核查","行政依据"],'
        '"reasoning":"基于历史相似申请，建议中等风险评估。"}'
    )
    monkeypatch.setattr(aa, "_inference_chat",
                        lambda *a, **kw: ChatResult(text=mocked, model="demo"))
    out = _invoke(brain, "application.draft.suggest", {
        "resource_name": "信用信息库",
        "applicant_org": "市场监管局",
        "use_case": "信用核查",
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": True,
    })
    assert out["source"] == "inference"
    assert out["risk_band"] == "medium"
    assert out["suggested_fields"]["use_reason"] == "信用核查"


def test_draft_suggest_inference_error_degrades(brain, monkeypatch):
    from zw_brain.command.handlers.j1 import application_assistants as aa
    from zw_brain.shared.inference.client import InferenceError

    def _raise(*a, **kw):
        raise InferenceError("base_url required")
    monkeypatch.setattr(aa, "_inference_chat", _raise)
    out = _invoke(brain, "application.draft.suggest", {
        "resource_name": "测试资源",
        "applicant_org": "测试部门",
        "role": "ROLE_ORGAN_OPERATER",
    })
    assert out["source"] == "fallback_rule"
    assert out["degraded"] is True


def test_draft_suggest_never_calls_application_create(brain, monkeypatch):
    """硬约束守卫：draft 助手绝不能直接 invoke_skill('application.resource.submit')."""
    original_invoke = brain.invoke_skill
    forbidden_calls: list[str] = []

    def _spy_invoke(skill_id, *args, **kwargs):
        if skill_id in ("application.resource.submit", "application.create"):
            forbidden_calls.append(skill_id)
            raise AssertionError(f"draft 助手禁止调用写 cap: {skill_id}")
        return original_invoke(skill_id, *args, **kwargs)

    monkeypatch.setattr(brain, "invoke_skill", _spy_invoke)
    out = _invoke(brain, "application.draft.suggest", {
        "resource_name": "测试", "applicant_org": "测试", "role": "ROLE_ORGAN_OPERATER", "enabled": False,
    })
    assert out["source"] == "fallback_rule"
    assert forbidden_calls == []


# ──────────────────────────────────────────────────────────────────────
# approval.evidence.summarize — 5 个真实历史申请
# ──────────────────────────────────────────────────────────────────────


def test_evidence_summarize_5_real_applications_fallback(brain, real_apply_samples):
    for sample in real_apply_samples:
        out = _invoke(brain, "approval.evidence.summarize", {
            "application_id": sample["application_code"],
            "role": "ROLE_ORGAN_MANAGER",
            "enabled": False,
        })
        assert out["source"] == "fallback_rule"
        assert out["application_id"] == sample["application_code"]
        assert out["application_status"] == sample["status"]
        assert out["recommendation"] in ("approve", "return_for_fix", "reject")
        assert isinstance(out["bases"], list) and out["bases"]
        assert isinstance(out["counter_factuals"], list) and out["counter_factuals"]
        assert out["recommended_decision_reason"]
        assert out["historical_summary"]


def test_evidence_summarize_not_found_returns_hint(brain):
    out = _invoke(brain, "approval.evidence.summarize", {
        "application_id": "NOT-EXISTS-APP-ID",
        "role": "ROLE_ORGAN_MANAGER",
    })
    assert out["status"] == "not_found"
    assert "不存在" in out["hint"]


def test_evidence_summarize_inference_path(brain, monkeypatch, real_apply_samples):
    from zw_brain.command.handlers.j1 import application_assistants as aa
    from zw_brain.shared.inference.client import ChatResult

    mocked = (
        '{"bases":["use_reason=行政依据 合规","历史相似申请 70% 已 approved"],'
        '"counter_factuals":["未声明字段子集，建议补 fields 列表"],'
        '"recommendation":"approve",'
        '"recommended_decision_reason":"基于历史模式与依据完整度，建议批准。",'
        '"historical_summary":"历史 4 条同源，3 条 approved，1 条 rejected。"}'
    )
    monkeypatch.setattr(aa, "_inference_chat",
                        lambda *a, **kw: ChatResult(text=mocked, model="demo"))
    sample = real_apply_samples[0]
    out = _invoke(brain, "approval.evidence.summarize", {
        "application_id": sample["application_code"],
        "role": "ROLE_ORGAN_MANAGER",
        "enabled": True,
    })
    assert out["source"] == "inference"
    assert out["recommendation"] == "approve"
    assert out["historical_summary"]


def test_evidence_summarize_inference_invalid_recommendation_normalized(brain, monkeypatch, real_apply_samples):
    """推理返回非法 recommendation 字符串 → 兜底到 return_for_fix."""
    from zw_brain.command.handlers.j1 import application_assistants as aa
    from zw_brain.shared.inference.client import ChatResult

    mocked = '{"bases":["x"],"counter_factuals":["y"],"recommendation":"维持原判","recommended_decision_reason":"r","historical_summary":"h"}'
    monkeypatch.setattr(aa, "_inference_chat",
                        lambda *a, **kw: ChatResult(text=mocked, model="demo"))
    sample = real_apply_samples[1]
    out = _invoke(brain, "approval.evidence.summarize", {
        "application_id": sample["application_code"],
        "role": "ROLE_ORGAN_MANAGER",
    })
    assert out["recommendation"] == "return_for_fix"


def test_evidence_summarize_never_calls_decision_cap(brain, monkeypatch, real_apply_samples):
    """硬约束守卫：审批助手绝不能 invoke 任何 approval.decide / request.approve|reject."""
    original_invoke = brain.invoke_skill
    forbidden_calls: list[str] = []
    forbidden = (
        "approval.case.decide", "approval.review_decide",
        "request.approve", "request.reject", "application.resource.review",
    )

    def _spy(skill_id, *args, **kwargs):
        if skill_id in forbidden:
            forbidden_calls.append(skill_id)
            raise AssertionError(f"审批助手禁止调用写 cap: {skill_id}")
        return original_invoke(skill_id, *args, **kwargs)

    monkeypatch.setattr(brain, "invoke_skill", _spy)
    sample = real_apply_samples[2]
    _invoke(brain, "approval.evidence.summarize", {
        "application_id": sample["application_code"],
        "role": "ROLE_ORGAN_MANAGER",
        "enabled": False,
    })
    assert forbidden_calls == []


# ──────────────────────────────────────────────────────────────────────
# Audit chain
# ──────────────────────────────────────────────────────────────────────


def test_audit_chain_records_both_caps(brain, real_apply_samples):
    sample = real_apply_samples[3]
    _invoke(brain, "application.draft.suggest", {
        "resource_name": sample["resource_name"],
        "applicant_org": sample["applicant_org"],
        "role": "ROLE_ORGAN_OPERATER",
        "enabled": False,
    })
    _invoke(brain, "approval.evidence.summarize", {
        "application_id": sample["application_code"],
        "role": "ROLE_ORGAN_MANAGER",
        "enabled": False,
    })
    types = [e["type"] for e in brain.snapshot()["audit_events"]]
    assert "application.draft.suggest" in types
    assert "approval.evidence.summarize" in types


# ──────────────────────────────────────────────────────────────────────
# §5.4.4 反约束守卫
# ──────────────────────────────────────────────────────────────────────


def test_draft_output_does_not_contain_submit_marker(brain):
    """draft 输出不应含 'submitted' / 'created' / 'application_code' 等"已提交"语义字段."""
    out = _invoke(brain, "application.draft.suggest", {
        "resource_name": "测试", "applicant_org": "测试", "role": "ROLE_ORGAN_OPERATER", "enabled": False,
    })
    for forbidden in ("application_code", "submitted_at", "request_id_created"):
        assert forbidden not in out, f"draft 不应返回 {forbidden}（§5.4.4 反约束）"


def test_evidence_output_does_not_contain_decision_marker(brain, real_apply_samples):
    """evidence 输出不应含 'decided' / 'approved_at' / 'decision_id' 等"已决策"语义字段."""
    sample = real_apply_samples[4]
    out = _invoke(brain, "approval.evidence.summarize", {
        "application_id": sample["application_code"],
        "role": "ROLE_ORGAN_MANAGER",
        "enabled": False,
    })
    for forbidden in ("decided_at", "decision_id", "approved_by"):
        assert forbidden not in out, f"evidence 不应返回 {forbidden}（§5.4.4 反约束）"
