from __future__ import annotations

from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.domain.policy import SelfApprovalNotAllowedError
from zw_brain.domain.services.conditional_approval import (
    STATUS_DEPT_APPROVED,
    STATUS_GRANTED,
    STATUS_SUBMITTED,
)
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_APPLICANT_A = "ORG-A-POLICE"
ORG_PLATFORM = "11370000MB284651XL"


@pytest.fixture()
def brain():
    ensure_runtime_schema()

    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    audit_bus.configure_sink(ds.append_audit_event)
    ss = StateStore(database_store=ds)
    return BrainService(state_store=ss)


def _seed_application(
    code: str,
    *,
    applicant_actor: str = "test-actor:role_organ_operater",
    org_code: str = ORG_APPLICANT_A,
) -> None:
    from zw_brain.domain.repositories.application import ApplicationRepository

    ApplicationRepository().upsert_from_request(
        {
            "id": code,
            "status": STATUS_SUBMITTED,
            "applicant": applicant_actor,
            "applicantDept": org_code,
            "resourceId": "C102_SELF_ACTOR_TEST",
            "shared_type": 2,
            "owner_org_code": org_code,
            "owner_org_name": "部门A_公安",
            "applicant_org_code": org_code,
        },
        tenant_id=TENANT,
    )


def _invoke(brain, skill_id: str, payload: dict[str, Any], *, role: str, org_code: str) -> dict[str, Any]:
    snap = actor_snapshot(role, org_code=org_code, tenant_id=TENANT)
    return invoke_trusted(brain, skill_id, payload, role=role, snapshot=snap)["result"]


def _accept(brain, code: str) -> None:
    out = _invoke(
        brain,
        "application.platform_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
        org_code=ORG_PLATFORM,
    )
    assert out["status"] == STATUS_DEPT_APPROVED


def _dept_approve(brain, code: str) -> dict[str, Any]:
    return _invoke(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        org_code=ORG_APPLICANT_A,
    )


def test_same_org_manager_can_approve_operator_request(brain):
    """Self-approval is actor-based; same org alone must not block department review."""
    code = "SELF-ACTOR-SAME-ORG-ALLOWED"
    _seed_application(code, applicant_actor="test-actor:role_organ_operater")
    _accept(brain, code)

    out = _dept_approve(brain, code)

    assert out["status"] == STATUS_GRANTED


def test_same_actor_cannot_approve_own_request(brain):
    code = "SELF-ACTOR-REJECTED"
    _seed_application(code, applicant_actor="test-actor:role_organ_manager")
    _accept(brain, code)

    with pytest.raises(SelfApprovalNotAllowedError):
        _dept_approve(brain, code)


def test_untrusted_actor_snapshot_cannot_bypass_self_approval_guard(brain):
    from zw_brain.shared.auth_context import AuthContext, reset_auth_context, set_auth_context

    token = set_auth_context(
        AuthContext(
            subject="mgr-subject",
            username="manager",
            tenant_id=TENANT,
            org_code=ORG_APPLICANT_A,
            role_codes=("ROLE_ORGAN_MANAGER",),
            claims={},
        )
    )
    try:
        actor = brain._actor_for_context(
            "ROLE_ORGAN_MANAGER",
            {
                "role": "ROLE_ORGAN_MANAGER",
                "org_code": ORG_APPLICANT_A,
                "actor_snapshot": {
                    "actor": "someone-else",
                    "current_org_code": ORG_APPLICANT_A,
                    "current_role": "ROLE_ORGAN_MANAGER",
                },
            },
        )
    finally:
        reset_auth_context(token)
    assert actor == "mgr-subject"


def test_dev_iam_bypass_actor_is_role_distinct_not_shared_subject(brain):
    """Bypass 模式下各岗位 actor 须可区分，否则 self_approval 把受理→部门审 e2e 全链打死。"""
    from zw_brain.shared.auth_context import AuthContext, reset_auth_context, set_auth_context

    token = set_auth_context(
        AuthContext(
            subject="dev-iam-bypass",
            username="dev_iam_bypass",
            tenant_id=TENANT,
            org_code=ORG_PLATFORM,
            role_codes=("ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"),
            claims={},
            development_iam_bypass=True,
        )
    )
    try:
        operater = brain._actor_for_context("ROLE_ORGAN_OPERATER", {"role": "ROLE_ORGAN_OPERATER"})
        manager = brain._actor_for_context("ROLE_ORGAN_MANAGER", {"role": "ROLE_ORGAN_MANAGER"})
        assert operater != manager
        assert operater.endswith("[bypass]")
        assert manager.endswith("[bypass]")
    finally:
        reset_auth_context(token)
