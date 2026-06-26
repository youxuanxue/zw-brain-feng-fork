from __future__ import annotations

from typing import Any

import pytest

from tests._trusted_payload import actor_snapshot, invoke_trusted
from zw_brain.domain.services.conditional_approval import (
    STATUS_DEPT_APPROVED,
    STATUS_GRANTED,
    STATUS_SUBMITTED,
)
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_PROVIDER_B = "ORG-B-MARKET-REG"
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


def _seed_conditional_application(code: str) -> None:
    from zw_brain.domain.repositories.application import ApplicationRepository

    ApplicationRepository().upsert_from_request(
        {
            "id": code,
            "status": STATUS_SUBMITTED,
            "applicant": "测试操作员",
            "applicantDept": ORG_APPLICANT_A,
            "resourceId": "C102_TEST",
            "shared_type": 2,
            "owner_org_code": ORG_PROVIDER_B,
            "owner_org_name": "部门B_市场监管",
            "applicant_org_code": ORG_APPLICANT_A,
        },
        tenant_id=TENANT,
    )


def _payload(code: str) -> dict[str, Any]:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None
    return rec.payload_json or {}


def _status(code: str) -> str:
    from zw_brain.domain.repositories.application import ApplicationRepository

    rec = ApplicationRepository().get_record(code, tenant_id=TENANT)
    assert rec is not None
    return rec.status


def _steps(code: str) -> list[Any]:
    from zw_brain.domain.repositories.approval import ApprovalRepository

    return ApprovalRepository().list_steps(code)


def _accept(brain, code: str) -> None:
    out = invoke_trusted(
        brain,
        "application.platform_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_BUSIAUDIT",
        snapshot=actor_snapshot("ROLE_BUSIAUDIT", org_code=ORG_PLATFORM, tenant_id=TENANT),
    )["result"]
    assert out["status"] == STATUS_DEPT_APPROVED


def test_multi_context_manager_can_dept_review_for_held_provider_org(brain):
    code = "A301-COND-MULTI-CTX"
    _seed_conditional_application(code)
    _accept(brain, code)
    snapshot = actor_snapshot(
        "ROLE_ORGAN_MANAGER",
        org_code=ORG_APPLICANT_A,
        tenant_id=TENANT,
        available_contexts=[
            {"org_code": ORG_APPLICANT_A, "role_code": "ROLE_ORGAN_MANAGER", "actor_tags": {}},
            {"org_code": ORG_PROVIDER_B, "role_code": "ROLE_ORGAN_MANAGER", "actor_tags": {}},
        ],
    )
    out = invoke_trusted(
        brain,
        "application.dept_approve",
        {"request_id": code, "decision": "approve", "confirmed": True},
        role="ROLE_ORGAN_MANAGER",
        snapshot=snapshot,
    )["result"]
    assert out["status"] == STATUS_GRANTED
    assert _payload(code)["dept_approver_org_code"] == ORG_PROVIDER_B
    assert _status(code) == STATUS_GRANTED
    assert any(s.decision_mode == "department" for s in _steps(code))
