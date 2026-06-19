# Wave: 0
# Journey: J1
# Pages: P3
# Consumer-faces: API (brain.invoke_skill — 运行时受理/审核两级)
# Roles: ROLE_BUSIAUDIT (省大数据局，受理第一级) | ROLE_ORGAN_MANAGER (提供方部门，审核第二级) | ROLE_ORGAN_OPERATER (申请人)
# Trace:
#   .testing/waves/wave-0-golden-path/features/j1-approval-conditional.feature
#   zw_brain/domain/services/conditional_approval.py
#   zw_brain/command/handlers/j1/approval.py (handler_application_{dept,platform}_approve)
"""j1-approval-conditional 运行时层 pytest — D55/P21 受理/审核两级真写库 + 状态机断言.

D55/P21（受理/审核两级，改 D49 关联）：有条件共享走「受理（业务运营员，第一级）→ 部门审核
（部门管理员，第二级终审）」，与旧序对调。capability key 不改名（D33 先例）：
  - application.platform_approve = 第一级受理（submitted → dept_approved/rejected），业务运营员，
    平台级动作不做 self/方向校验。
  - application.dept_approve     = 第二级部门审核终审（dept_approved → granted/rejected），部门管理员，
    保留 self_approval + R11 方向 guard；resubmit 复用本 key 走申请人路径。

中间态字符串 ``dept_approved`` 不改名（API surface / 国家转报路径键此态），含义=「已受理待部门审」。

数据隔离：临时 DB + ensure_runtime_schema()，合成有条件共享申请单（shared_type=2 + owner_org_code）
驱动状态机，写不触真实 seed 库。
"""
from __future__ import annotations

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
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"

# 提供方部门 = 部门B_市场监管；申请人部门 = 部门A_公安；平台 = 省大数据局；部门C = 自然资源
ORG_PROVIDER_B = "ORG-B-MARKET-REG"
ORG_APPLICANT_A = "ORG-A-POLICE"
ORG_PLATFORM = "11370000MB284651XL"
ORG_DEPT_C = "ORG-C-NATURAL-RES"


@pytest.fixture()
def brain():
    """Brain bound to the per-test empty PG clone (provided by the conftest
    autouse fixture); ensure_runtime_schema() makes the schema present."""
    ensure_runtime_schema()

    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


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


def _accept(brain, code: str, *, decision: str = "approve", note: str = "") -> dict[str, Any]:
    """第一级受理（业务运营员 application.platform_approve）。"""
    return _invoke(
        brain,
        "application.platform_approve",
        {"request_id": code, "decision": decision, "confirmed": True, "note": note},
        role="ROLE_BUSIAUDIT",
        org_code=ORG_PLATFORM,
    )["result"]


def _dept_review(
    brain, code: str, *, decision: str = "approve", note: str = "", org_code: str = ORG_PROVIDER_B
) -> dict[str, Any]:
    """第二级部门审核（部门管理员 application.dept_approve）。"""
    return _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": decision, "confirmed": True, "note": note},
        role="ROLE_ORGAN_MANAGER",
        org_code=org_code,
    )["result"]


# ============================================================================
# Scenario 1: 正向 — 第一级业务运营员受理通过（submitted → dept_approved 受理通过待审）
# ============================================================================


def test_accept_advances_submitted_to_dept_approved(brain):
    code = "A301-COND-1"
    _seed_conditional_application(code)
    out = _accept(brain, code, note="材料齐全，予以受理")
    assert out["status"] == STATUS_DEPT_APPROVED
    assert out["legacy_status"] == 4, "受理通过映射 legacy status 4（待部门审核中间态）"
    assert _status(code) == STATUS_DEPT_APPROVED
    # 受理 step 落库（decision_mode='single'，decision='approved'）
    accept_steps = [s for s in _steps(code) if s.decision_mode == "single"]
    assert len(accept_steps) == 1
    assert accept_steps[0].status == "completed"
    decs = _decisions(code)
    assert any(d.decision == "approved" for d in decs)
    # 审计反馈记录 capability_call=application.platform_approve（受理动作复用此 key）
    feed = brain.snapshot().get("auditFeed") or brain._snapshot.get("audit_events") or []
    assert any("application.platform_approve" in str(e) for e in feed), f"审计反馈应含 application.platform_approve；feed={feed!r}"


# ============================================================================
# Scenario 2: 正向 — 第二级部门管理员审核通过（dept_approved → granted）
# ============================================================================


def test_dept_review_advances_dept_approved_to_granted(brain):
    code = "A301-COND-2"
    _seed_conditional_application(code)
    _accept(brain, code)
    assert _status(code) == STATUS_DEPT_APPROVED
    out = _dept_review(brain, code)
    assert out["status"] == STATUS_GRANTED
    assert out["legacy_status"] == 6, "已授权映射 legacy status 6"
    assert _status(code) == STATUS_GRANTED
    # 两级共存：single(受理) step + department(部门审核) step
    modes = sorted(s.decision_mode for s in _steps(code))
    assert modes == ["department", "single"], f"应 department+single 两级共存；got {modes}"
    # 审计事件链：platform_approve(受理) + dept_approve(部门审核)
    feed = brain._snapshot.get("audit_events") or brain.snapshot().get("auditFeed") or []
    assert any("application.platform_approve" in str(e) for e in feed)
    assert any("application.dept_approve" in str(e) for e in feed)


# ============================================================================
# Scenario 3: 正向 — 第一级受理驳回 + 申请人补件重提（rejected → submitted, round+1）
# ============================================================================


def test_accept_reject_then_applicant_resubmit_increments_round(brain):
    code = "A301-COND-3"
    _seed_conditional_application(code)
    out = _accept(brain, code, decision="reject", note="缺少业务场景说明")
    assert out["status"] == STATUS_REJECTED
    assert out["legacy_status"] == 3, "驳回映射 legacy status 3"
    assert _status(code) == STATUS_REJECTED
    # 申请人补件重提（OPERATER 本人，复用 dept_approve key 的 resubmit 路径）
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
# Scenario 4: 负向 — 受理通过后部门审核驳回（4 → 3，受理记录保留）
# ============================================================================


def test_dept_review_reject_after_accept_preserves_accept_step(brain):
    code = "A301-COND-4"
    _seed_conditional_application(code)
    _accept(brain, code)
    accept_step_ids_before = sorted(s.id for s in _steps(code) if s.decision_mode == "single")
    out = _dept_review(brain, code, decision="reject", note="近 6 个月调用合规风险高，本次拒绝")
    assert out["status"] == STATUS_REJECTED
    assert _status(code) == STATUS_REJECTED
    # 受理 step 仍保留（append-only，不回退/软删）
    accept_steps_after = [s for s in _steps(code) if s.decision_mode == "single"]
    assert sorted(s.id for s in accept_steps_after) == accept_step_ids_before, "受理 step 应保留"
    assert all(s.status == "completed" for s in accept_steps_after)
    accept_dec = [d for d in _decisions(code) if d.decision == "approved"]
    assert accept_dec, "受理 approved 决策应保留"
    review_dec = [d for d in _decisions(code) if d.decision == "rejected"]
    assert review_dec, "部门审核驳回决策应落库"


# ============================================================================
# Scenario 5: 负向 — 提供方部门外的 ORGAN_MANAGER 不能审核此申请（R11 方向，第二级）
# ============================================================================


def test_cross_org_manager_cannot_dept_review_r11_direction(brain):
    code = "A301-COND-5"
    _seed_conditional_application(code, owner_org_code=ORG_PROVIDER_B)
    _accept(brain, code)  # 先受理进入第二级
    # U_DEPT_C_MGR (部门C 自然资源) 不是 owner_org_code(部门B) → 拒绝
    with pytest.raises(ApprovalDirectionError):
        _dept_review(brain, code, org_code=ORG_DEPT_C)
    # 状态未变（仍 dept_approved），未越权写终审
    assert _status(code) == STATUS_DEPT_APPROVED
    assert not any(s.decision_mode == "department" for s in _steps(code)), "越权调用不得落部门审核 step"


# ============================================================================
# Scenario 6: 负向 — 申请人本人不能审核自己的申请（self_approval reject + audit，第二级）
# ============================================================================


def test_self_approval_rejected_at_dept_review(brain):
    code = "A301-COND-6"
    # owner_org_code == applicant_org_code（同一部门既申请又自审 = legacy anomaly）
    _seed_conditional_application(code, owner_org_code=ORG_APPLICANT_A, applicant_org_code=ORG_APPLICANT_A)
    _accept(brain, code)  # 受理进入第二级
    with pytest.raises(SelfApprovalNotAllowedError) as exc:
        _dept_review(brain, code, org_code=ORG_APPLICANT_A)
    assert "self_approval_not_allowed" in str(exc.value)
    assert _status(code) == STATUS_DEPT_APPROVED, "自审被拒，状态不变（仍待部门审）"


# ============================================================================
# Scenario 8: 负向 — OPERATER 用 decision='approve' 不能走部门审核路径（R-001 角色门控）
# ============================================================================


def test_operater_cannot_dept_review_via_decision_approve_r001(brain):
    """R-001: application.dept_approve.execute 的 PERMISSION_ROLES 含 OPERATER 仅为
    resubmit 复用同 capability。OPERATER（org==owner_org 使 R11 方向通过、非申请人本人使
    self-approval 通过）用 decision='approve' 本可走到部门审核路径，越过「部门审核仅
    ROLE_ORGAN_MANAGER」的 SPEC 角色边界。handler 按 ctx.role 二次门控 → 拒绝。
    """
    code = "A301-COND-8"
    _seed_conditional_application(code, owner_org_code=ORG_PROVIDER_B, applicant_org_code=ORG_APPLICANT_A)
    _accept(brain, code)  # 受理进入第二级（dept_approved），使 OPERATER 走到部门审核路径
    with pytest.raises(AccessDeniedError) as exc:
        _invoke(
            brain,
            "application.dept_approve",
            {"request_id": code, "decision": "approve", "confirmed": True},
            role="ROLE_ORGAN_OPERATER",
            org_code=ORG_PROVIDER_B,
        )
    assert "ROLE_ORGAN_MANAGER" in str(exc.value)
    # 越权调用：状态不变（仍 dept_approved），不落部门审核 step
    assert _status(code) == STATUS_DEPT_APPROVED, "越权调用，状态不变"
    assert not any(s.decision_mode == "department" for s in _steps(code)), "越权调用不得落部门审核 step"


# ============================================================================
# Scenario 7: 回归 — 状态机迁移合法性（基线 §3.3）
# ============================================================================


def test_illegal_transition_dept_review_on_submitted(brain):
    """非法迁移：submitted 直接部门审核（跳过受理）应被状态机拒绝。"""
    code = "A301-COND-7A"
    _seed_conditional_application(code)
    with pytest.raises(InvalidStateError):
        _dept_review(brain, code)
    assert _status(code) == STATUS_SUBMITTED


def test_illegal_transition_double_dept_review(brain):
    """granted 是终态：再次部门审核应被拒（granted 无合法后继）。"""
    code = "A301-COND-7B"
    _seed_conditional_application(code)
    _accept(brain, code)
    _dept_review(brain, code)
    assert _status(code) == STATUS_GRANTED
    with pytest.raises(InvalidStateError):
        _dept_review(brain, code)
    assert _status(code) == STATUS_GRANTED


def test_state_machine_legal_transition_table_matches_baseline():
    """状态机合法迁移表与 .feature 末尾回归场景表一致（纯函数断言，无 DB）。

    D55/P21：迁移对（状态字符串）不变；actor 含义对调（submitted→dept_approved 由受理产生、
    dept_approved→granted 由部门审核产生）。
    """
    from zw_brain.domain.services.conditional_approval import (
        CONDITIONAL_TRANSITIONS,
        assert_legal_transition,
    )

    # 合法迁移（.feature 状态机表）
    assert_legal_transition(STATUS_SUBMITTED, STATUS_DEPT_APPROVED)  # accept(受理)
    assert_legal_transition(STATUS_SUBMITTED, STATUS_REJECTED)       # accept.reject
    assert_legal_transition(STATUS_SUBMITTED, STATUS_GRANTED)        # 无条件受理即终
    assert_legal_transition(STATUS_DEPT_APPROVED, STATUS_GRANTED)    # dept_review(部门审核)
    assert_legal_transition(STATUS_DEPT_APPROVED, STATUS_REJECTED)   # dept_review.reject
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
