# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: API (brain.invoke_skill — 运行时两步条件审批)
# Roles: ROLE_ORGAN_MANAGER (提供方部门) | ROLE_BUSIAUDIT (省大数据局) | ROLE_ORGAN_OPERATER (申请人)
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature
#   zw_brain/domain/services/conditional_approval.py
#   zw_brain/command/handlers/j1/approval.py (handler_application_{dept,platform}_approve)
"""j1-approval-conditional 运行时层 pytest — 两步条件审批真写库 + 状态机断言.

与 tests/test_wave0_j1_approval_conditional.py（数据底座层，断 ExchangeMapper 灌入的
真实 department step）互补：本文件**驱动真实 handler**经 invoke_skill / 服务层真写库后
断言 application_record.status + approval_step/decision 行 + 审计反馈，覆盖 .feature 的
两步 flow（数据底座层无法断言运行时迁移）。

数据隔离：临时 DB + ensure_runtime_schema()（同 tests/test_credential_honesty_legacy_granted.py），
合成有条件共享申请单（shared_type=2 + owner_org_code）驱动状态机，写不触真实 seed 库。
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.domain.errors import AccessDeniedError, InvalidStateError
from zw_brain.domain.policy import (
    ApprovalDirectionError,
    SelfApprovalNotAllowedError,
)
from zw_brain.domain.services.conditional_approval import (
    STATUS_DEPT_APPROVED,
    STATUS_GRANTED,
    STATUS_REJECTED,
    STATUS_SUBMITTED,
)
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"

# 提供方部门 = 部门B_市场监管；申请人部门 = 部门A_公安；平台 = 省大数据局；部门C = 自然资源
ORG_PROVIDER_B = "ORG-B-MARKET-REG"
ORG_APPLICANT_A = "ORG-A-POLICE"
ORG_PLATFORM = "11370000MB284651XL"
ORG_DEPT_C = "ORG-C-NATURAL-RES"


@pytest.fixture()
def brain(monkeypatch: pytest.MonkeyPatch):
    """Fresh temp DB + brain bound to it (ensure_runtime_schema rebuilds schema)."""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "approval_conditional_runtime.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()

        import zw_brain.shared.audit as audit_bus
        from zw_brain.command.brain import BrainService
        from zw_brain.shared.database_store import DatabaseStore
        from zw_brain.shared.state_store import StateStore

        ds = DatabaseStore()
        audit_bus.configure_sink(ds.append_audit_event)
        ss = StateStore(database_store=ds)
        yield BrainService(state_store=ss)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_conditional_application(
    code: str,
    *,
    status: str = STATUS_SUBMITTED,
    owner_org_code: str = ORG_PROVIDER_B,
    applicant_org_code: str = ORG_APPLICANT_A,
) -> None:
    """合成一条有条件共享(shared_type=2)申请单，落 application_record（真写库）。"""
    from zw_brain.domain.repositories.application import ApplicationRepository

    ApplicationRepository().upsert_from_request(
        {
            "id": code,
            "status": status,
            "applicant": "测试操作员",
            "applicantDept": applicant_org_code,
            "resourceId": "C102_TEST",
            "shared_type": 2,
            "owner_org_code": owner_org_code,
            "owner_org_name": "部门B_市场监管",
            "applicant_org_code": applicant_org_code,
        },
        tenant_id=TENANT,
    )


def _status(code: str) -> str:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None, f"application_record {code} 应存在"
    return rec.status


def _payload(code: str) -> dict[str, Any]:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None
    return rec.payload_json or {}


def _steps(code: str) -> list[Any]:
    from zw_brain.domain.repositories.approval import ApprovalRepository

    return ApprovalRepository().list_steps(code)


def _decisions(code: str) -> list[Any]:
    from zw_brain.domain.repositories.approval import ApprovalRepository

    return ApprovalRepository().list_decisions(code)


def _invoke(brain, skill_id: str, payload: dict[str, Any], *, role: str, org_code: str) -> dict[str, Any]:
    snap = actor_snapshot(role, org_code=org_code, tenant_id=TENANT)
    return invoke_trusted(brain, skill_id, payload, role=role, snapshot=snap)


# ============================================================================
# Scenario 1: 正向 — 第一步部门管理员审核通过（submitted → dept_approved）
# ============================================================================


def test_dept_approve_advances_submitted_to_dept_approved(brain):
    code = "A301-COND-1"
    _seed_conditional_application(code)
    out = _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "approve", "confirmed": True, "note": "用途合理，限期 90 天"},
        role="ROLE_ORGAN_MANAGER",
        org_code=ORG_PROVIDER_B,
    )["result"]
    assert out["status"] == STATUS_DEPT_APPROVED
    assert out["legacy_status"] == 4, "部门同意映射 legacy status 4"
    assert _status(code) == STATUS_DEPT_APPROVED
    # 申请单记录 dept_approver_id
    assert _payload(code).get("dept_approver_id"), "应记录 dept_approver_id"
    # 部门审 step 落库（decision_mode='department'，decision='approved'）
    dept_steps = [s for s in _steps(code) if s.decision_mode == "department"]
    assert len(dept_steps) == 1
    assert dept_steps[0].status == "completed"
    decs = _decisions(code)
    assert any(d.decision == "approved" for d in decs)
    # 审计反馈记录 capability_call=application.dept_approve
    feed = brain.snapshot().get("auditFeed") or brain._snapshot.get("audit_events") or []
    assert any("application.dept_approve" in str(e) for e in feed), f"审计反馈应含 application.dept_approve；feed={feed!r}"


# ============================================================================
# Scenario 2: 正向 — 第二步平台运营员复核通过（dept_approved → granted）
# ============================================================================


def test_platform_approve_advances_dept_approved_to_granted(brain):
    code = "A301-COND-2"
    _seed_conditional_application(code)
    _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        org_code=ORG_PROVIDER_B,
    )
    assert _status(code) == STATUS_DEPT_APPROVED
    out = _invoke(
        brain,
        "application.platform_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
        org_code=ORG_PLATFORM,
    )["result"]
    assert out["status"] == STATUS_GRANTED
    assert out["legacy_status"] == 6, "已授权映射 legacy status 6"
    assert _status(code) == STATUS_GRANTED
    # 两步共存：department step + single(平台复核) step
    modes = sorted(s.decision_mode for s in _steps(code))
    assert modes == ["department", "single"], f"应 department+single 两步共存；got {modes}"
    # 审计事件链三条：dept_approve + platform_approve（submit 由提交路径产生，本合成单跳过）
    feed = brain._snapshot.get("audit_events") or brain.snapshot().get("auditFeed") or []
    assert any("application.dept_approve" in str(e) for e in feed)
    assert any("application.platform_approve" in str(e) for e in feed)


# ============================================================================
# Scenario 3: 正向 — 第一步驳回 + 申请人补件重提（rejected → submitted, round+1）
# ============================================================================


def test_dept_reject_then_applicant_resubmit_increments_round(brain):
    code = "A301-COND-3"
    _seed_conditional_application(code)
    out = _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "reject", "confirmed": True, "note": "缺少业务场景说明"},
        role="ROLE_ORGAN_MANAGER",
        org_code=ORG_PROVIDER_B,
    )["result"]
    assert out["status"] == STATUS_REJECTED
    assert out["legacy_status"] == 3, "驳回映射 legacy status 3"
    assert _status(code) == STATUS_REJECTED
    # 申请人补件重提（OPERATER 本人）
    out2 = _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "resubmit", "confirmed": True},
        role="ROLE_ORGAN_OPERATER",
        org_code=ORG_APPLICANT_A,
    )["result"]
    assert out2["status"] == STATUS_SUBMITTED
    assert out2["round"] == 2, "重提 round 计数 +1（首轮 1 → 2）"
    assert _status(code) == STATUS_SUBMITTED
    assert _payload(code).get("round") == 2


# ============================================================================
# Scenario 4: 负向 — 部门审通过后平台驳回（4 → 3，部门审记录保留）
# ============================================================================


def test_platform_reject_after_dept_approve_preserves_dept_step(brain):
    code = "A301-COND-4"
    _seed_conditional_application(code)
    _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        org_code=ORG_PROVIDER_B,
    )
    dept_step_ids_before = sorted(s.id for s in _steps(code) if s.decision_mode == "department")
    out = _invoke(
        brain,
        "application.platform_approve",
        {"request_id": code, "decision": "reject", "confirmed": True, "note": "近 6 个月调用合规风险高，本次拒绝"},
        role="ROLE_BUSIAUDIT",
        org_code=ORG_PLATFORM,
    )["result"]
    assert out["status"] == STATUS_REJECTED
    assert _status(code) == STATUS_REJECTED
    # 部门审通过的 step 仍保留（append-only，不回退/软删）
    dept_steps_after = [s for s in _steps(code) if s.decision_mode == "department"]
    assert sorted(s.id for s in dept_steps_after) == dept_step_ids_before, "部门审 step 应保留"
    assert all(s.status == "completed" for s in dept_steps_after)
    dept_dec = [d for d in _decisions(code) if d.decision == "approved"]
    assert dept_dec, "部门审 approved 决策应保留"
    plat_dec = [d for d in _decisions(code) if d.decision == "rejected"]
    assert plat_dec, "平台驳回决策应落库"


# ============================================================================
# Scenario 5: 负向 — 提供方部门外的 ORGAN_MANAGER 不能审批此申请（R11 方向）
# ============================================================================


def test_cross_org_manager_cannot_dept_approve_r11_direction(brain):
    code = "A301-COND-5"
    _seed_conditional_application(code, owner_org_code=ORG_PROVIDER_B)
    # U_DEPT_C_MGR (部门C 自然资源) 不是 owner_org_code(部门B) → 拒绝
    with pytest.raises(ApprovalDirectionError):
        _invoke(
            brain,
            "application.dept_approve",
            {"request_id": code, "decision": "approve", "confirmed": True},
            role="ROLE_ORGAN_MANAGER",
            org_code=ORG_DEPT_C,
        )
    # 状态未变（仍 submitted），未越权写
    assert _status(code) == STATUS_SUBMITTED
    assert not any(s.decision_mode == "department" for s in _steps(code)), "越权调用不得落部门审 step"


# ============================================================================
# Scenario 6: 负向 — 申请人本人不能审批自己的申请（self_approval reject + audit）
# ============================================================================


def test_self_approval_rejected(brain):
    code = "A301-COND-6"
    # owner_org_code == applicant_org_code（同一部门既申请又自审 = legacy anomaly）
    _seed_conditional_application(code, owner_org_code=ORG_APPLICANT_A, applicant_org_code=ORG_APPLICANT_A)
    with pytest.raises(SelfApprovalNotAllowedError) as exc:
        _invoke(
            brain,
            "application.dept_approve",
            {"request_id": code, "decision": "approve", "confirmed": True},
            role="ROLE_ORGAN_MANAGER",
            org_code=ORG_APPLICANT_A,
        )
    assert "self_approval_not_allowed" in str(exc.value)
    assert _status(code) == STATUS_SUBMITTED, "自审被拒，状态不变"


# ============================================================================
# Scenario 8: 负向 — OPERATER 用 decision='approve' 不能走部门审路径（R-001 角色门控）
# ============================================================================


def test_operater_cannot_dept_approve_via_decision_approve_r001(brain):
    """R-001: application.dept_approve.execute 的 PERMISSION_ROLES 含 OPERATER 仅为
    resubmit 复用同 capability。OPERATER（org==owner_org 使 R11 方向通过、非申请人本人使
    self-approval 通过）用 decision='approve' 本可走到 dept_approve 审批路径，越过
    「部门审仅 ROLE_ORGAN_MANAGER」的 SPEC 角色边界。handler 按 ctx.role 二次门控 → 拒绝。
    """
    code = "A301-COND-8"
    # owner=部门B；申请人=部门A。OPERATER 在部门B（owner）发起：方向 guard 通过、
    # self-approval guard 通过（org != applicant），唯一拦截点是 R-001 的 ctx.role 门控。
    _seed_conditional_application(code, owner_org_code=ORG_PROVIDER_B, applicant_org_code=ORG_APPLICANT_A)
    with pytest.raises(AccessDeniedError) as exc:
        _invoke(
            brain,
            "application.dept_approve",
            {"request_id": code, "decision": "approve", "confirmed": True},
            role="ROLE_ORGAN_OPERATER",
            org_code=ORG_PROVIDER_B,
        )
    assert "ROLE_ORGAN_MANAGER" in str(exc.value)
    # 越权调用：状态不变（仍 submitted），不落部门审 step
    assert _status(code) == STATUS_SUBMITTED, "越权调用，状态不变"
    assert not any(s.decision_mode == "department" for s in _steps(code)), "越权调用不得落部门审 step"


# ============================================================================
# Scenario 7: 回归 — 状态机迁移合法性（基线 §3.3）
# ============================================================================


def test_illegal_transition_rejected_platform_on_submitted(brain):
    """非法迁移：submitted 直接平台复核（跳过部门审）应被状态机拒绝。"""
    code = "A301-COND-7A"
    _seed_conditional_application(code)
    with pytest.raises(InvalidStateError):
        _invoke(
            brain,
            "application.platform_approve",
            {"request_id": code, "decision": "approve", "confirmed": True},
            role="ROLE_BUSIAUDIT",
            org_code=ORG_PLATFORM,
        )
    assert _status(code) == STATUS_SUBMITTED


def test_illegal_transition_double_platform_approve(brain):
    """granted 是终态：再次平台复核应被拒（granted 无合法后继）。"""
    code = "A301-COND-7B"
    _seed_conditional_application(code)
    _invoke(brain, "application.dept_approve", {"request_id": code, "decision": "approve", "confirmed": True}, role="ROLE_ORGAN_MANAGER", org_code=ORG_PROVIDER_B)
    _invoke(brain, "application.platform_approve", {"request_id": code, "decision": "approve", "confirmed": True}, role="ROLE_BUSIAUDIT", org_code=ORG_PLATFORM)
    assert _status(code) == STATUS_GRANTED
    with pytest.raises(InvalidStateError):
        _invoke(brain, "application.platform_approve", {"request_id": code, "decision": "approve", "confirmed": True}, role="ROLE_BUSIAUDIT", org_code=ORG_PLATFORM)
    assert _status(code) == STATUS_GRANTED


def test_state_machine_legal_transition_table_matches_baseline():
    """状态机合法迁移表与 .feature 末尾回归场景表一致（纯函数断言，无 DB）。"""
    from zw_brain.domain.services.conditional_approval import (
        CONDITIONAL_TRANSITIONS,
        assert_legal_transition,
    )

    # 合法迁移（.feature 状态机表）
    assert_legal_transition(STATUS_SUBMITTED, STATUS_DEPT_APPROVED)  # dept.approve
    assert_legal_transition(STATUS_SUBMITTED, STATUS_REJECTED)       # dept.reject
    assert_legal_transition(STATUS_SUBMITTED, STATUS_GRANTED)        # platform.approve(unconditional)
    assert_legal_transition(STATUS_DEPT_APPROVED, STATUS_GRANTED)    # platform.approve
    assert_legal_transition(STATUS_DEPT_APPROVED, STATUS_REJECTED)   # platform.reject
    assert_legal_transition(STATUS_REJECTED, STATUS_SUBMITTED)       # applicant.resubmit
    # granted 终态无后继
    assert CONDITIONAL_TRANSITIONS[STATUS_GRANTED] == set()
    # 非法迁移示例
    for frm, to in [
        (STATUS_DEPT_APPROVED, STATUS_SUBMITTED),
        (STATUS_GRANTED, STATUS_REJECTED),
        (STATUS_REJECTED, STATUS_GRANTED),
    ]:
        with pytest.raises(InvalidStateError):
            assert_legal_transition(frm, to)
