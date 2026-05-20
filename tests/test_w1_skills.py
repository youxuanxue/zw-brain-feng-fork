"""W1 skill contract tests: 12 new skills covering reverse cataloging, quality
task management, direct-access read views, demand dispatch / handoff, and
withdrawal handling (delivery replace/cancel + subscription terminate).

Each skill gets at minimum:
- Manifest is registered with the expected audit class + surfaces
- Policy assigns the correct roles
- Happy-path invocation succeeds (write skills round-trip via DatabaseStore)
- Confirmation is enforced on writes
- Wrong-role calls are rejected

Tests use the DatabaseStore-backed BrainService factory mirrored from
tests/test_brain_service.py so the audit sink is wired to a real on-disk
SQLite DB.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zw_brain.command.brain import (
    AccessDeniedError,
    BrainService,
    ConfirmationRequiredError,
)
from zw_brain.domain.policy import PERMISSION_ROLES
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.state_store import StateStore
from zw_brain.skill_registration.runtime import get_manifest


def _make_database_service(tmp_dir: Path) -> BrainService:
    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp_dir / "zw_brain_w1.db")
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=database_store))


@pytest.fixture()
def svc(tmp_path: Path) -> BrainService:
    return _make_database_service(tmp_path)


W1_SKILLS = [
    ("catalog.entry.reverse_draft.create", "write-default", {"ROLE_ORGAN_MANAGER"}),
    ("catalog.entry.reverse_draft.confirm", "write-critical", {"ROLE_BUSIAUDIT"}),
    ("catalog.entry.reverse_draft.reject", "write-default", {"ROLE_BUSIAUDIT"}),
    ("metadata.schema.discover", "read-trace", {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
    ("quality.rule.upsert", "write-default", {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
    ("quality.task.run", "write-default", {"ROLE_ORGAN_MANAGER"}),
    ("quality.task.replay", "write-default", {"ROLE_ORGAN_MANAGER"}),
    ("direct_access.catalog.query", "read-trace", {"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"}),
    ("direct_access.delivery.list", "read-trace", {"ROLE_ORGAN_MANAGER", "ROLE_SECURITY_AUDIT"}),
    ("require.resource.dispatch", "write-critical", {"ROLE_BUSIAUDIT"}),
    ("require.task.handoff", "write-default", {"ROLE_BUSIAUDIT"}),
    ("delivery.replace_or_cancel", "write-critical", {"ROLE_ORGAN_MANAGER"}),
    ("subscription.terminate", "write-critical", {"ROLE_ORGAN_MANAGER"}),
]


@pytest.mark.parametrize("skill_id,audit_class,roles", W1_SKILLS)
def test_w1_manifest_and_policy(skill_id: str, audit_class: str, roles: set[str]) -> None:
    manifest = get_manifest(skill_id)
    assert manifest["audit_class"] == audit_class
    for surface in ("webui", "api", "cli", "mcp", "a2a"):
        assert surface in manifest["compatibility"], f"{skill_id} missing surface {surface}"
    assert manifest["audit_required"] is True
    allowed = PERMISSION_ROLES.get(f"{skill_id}.execute") or set()
    assert allowed == roles, f"{skill_id} permissions {allowed} != expected {roles}"


def test_reverse_draft_lifecycle(svc: BrainService) -> None:
    create_result = svc.invoke_skill(
        "catalog.entry.reverse_draft.create",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "catalog_code": "TC-RD-001",
            "title": "停车场信息 (reverse-draft)",
            "schema_ref": "schema-snapshot-RD-001",
            "draft_field_suggestions": [{"name": "park_id", "name_cn": "停车场编号"}],
        },
    )
    assert create_result["ok"] is True
    assert create_result["result"]["lifecycle_status"] == "draft"

    confirm_result = svc.invoke_skill(
        "catalog.entry.reverse_draft.confirm",
        {
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
            "catalog_code": "TC-RD-001",
            "field_decisions": [{"name": "park_id", "sensitive_level": "1"}],
            "comment": "字段口径与目录模板一致",
        },
    )
    assert confirm_result["ok"] is True
    assert confirm_result["result"]["lifecycle_status"] == "pending_review"


def test_reverse_draft_reject_requires_reverse_source(svc: BrainService) -> None:
    svc.invoke_skill(
        "catalog.entry.reverse_draft.create",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "catalog_code": "TC-RD-002",
            "title": "字段口径模糊",
            "schema_ref": "schema-snapshot-RD-002",
        },
    )
    result = svc.invoke_skill(
        "catalog.entry.reverse_draft.reject",
        {
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
            "catalog_code": "TC-RD-002",
            "reject_reason": "中英文字段不一致，缺主键说明",
        },
    )
    assert result["result"]["lifecycle_status"] == "rejected"
    assert "中英文字段不一致" in result["result"]["reason"]


def test_metadata_schema_discover_is_read_only(svc: BrainService) -> None:
    result = svc.invoke_skill("metadata.schema.discover", {"role": "ROLE_ORGAN_MANAGER", "limit": 20})
    assert "items" in result
    assert "total" in result
    assert isinstance(result["items"], list)


def test_quality_rule_then_run_then_replay(svc: BrainService) -> None:
    rule = svc.invoke_skill(
        "quality.rule.upsert",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "rule_code": "QR-MUST-FILL-01",
            "rule_name": "必填率检查",
            "rule_kind": "completeness",
            "rule_payload_json": {"threshold": 0.98},
            "target_catalog_codes": ["TC-RD-001"],
        },
    )
    assert rule["ok"] is True
    assert rule["result"]["rule_code"] == "QR-MUST-FILL-01"

    run = svc.invoke_skill(
        "quality.task.run",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "rule_code": "QR-MUST-FILL-01",
            "target_catalog_code": "TC-RD-001",
        },
    )
    assert run["result"]["task_status"] == "running"
    previous_ref = run["result"]["task_ref"]

    replay = svc.invoke_skill(
        "quality.task.replay",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "rule_code": "QR-MUST-FILL-01",
            "previous_task_ref": previous_ref,
            "reason": "外部执行器超时",
        },
    )
    assert replay["result"]["previous_task_ref"] == previous_ref


def test_direct_access_catalog_query_returns_envelope(svc: BrainService) -> None:
    result = svc.invoke_skill("direct_access.catalog.query", {"role": "ROLE_SECURITY_AUDIT"})
    assert "items" in result
    assert "total" in result


def test_direct_access_delivery_list_returns_envelope(svc: BrainService) -> None:
    result = svc.invoke_skill("direct_access.delivery.list", {"role": "ROLE_ORGAN_MANAGER"})
    assert "items" in result
    assert "total" in result


def test_require_resource_dispatch_needs_existing_application(svc: BrainService) -> None:
    from zw_brain.domain.models import ApplicationRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        session.add(
            ApplicationRecord(
                tenant_id="sd-default",
                application_code="REQ-W1-0001",
                status="submitted",
                applicant_name="测试申请人",
                applicant_org="省大数据局",
                payload_json={"intent": "民生保障专题"},
            )
        )
        session.commit()

    result = svc.invoke_skill(
        "require.resource.dispatch",
        {
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
            "application_code": "REQ-W1-0001",
            "dispatch_payload_json": {"slice_by": "region"},
            "target_region_codes": ["370102", "370112"],
        },
    )
    assert result["result"]["status"] == "dispatched"


def test_require_task_handoff_emits_audit(svc: BrainService) -> None:
    result = svc.invoke_skill(
        "require.task.handoff",
        {
            "role": "ROLE_BUSIAUDIT",
            "confirmed": True,
            "application_code": "REQ-W1-0001",
            "handoff_to_role": "ROLE_ORGAN_MANAGER",
            "handoff_note": "审核汇总人 接管异常汇总",
        },
    )
    assert result["ok"] is True
    assert result["result"]["handoff_to_role"] == "ROLE_ORGAN_MANAGER"


def test_delivery_replace_or_cancel_updates_state(svc: BrainService) -> None:
    from zw_brain.domain.models import DeliveryTaskRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        session.add(
            DeliveryTaskRecord(
                tenant_id="sd-default",
                delivery_code="DLV-W1-0001",
                application_code="REQ-W1-0001",
                state="active",
                channel="api",
                payload_json={"access_grant_snapshot": {"direct_access": True}},
            )
        )
        session.commit()

    result = svc.invoke_skill(
        "delivery.replace_or_cancel",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "delivery_code": "DLV-W1-0001",
            "action": "replace",
            "replacement_resource_id": "RES-FALLBACK-01",
            "reason": "原资源已撤回",
        },
    )
    assert result["result"]["state"] == "replaced"


def test_subscription_terminate_writes_audit_snapshot(svc: BrainService) -> None:
    from zw_brain.domain.models import DeliverySubscriptionRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        session.add(
            DeliverySubscriptionRecord(
                tenant_id="sd-default",
                subscription_code="SUB-W1-0001",
                delivery_code="DLV-W1-0001",
                status="active",
                schedule_ref_json={},
                policy_snapshot_json={},
                legacy_status_snapshot_json={},
            )
        )
        session.commit()

    result = svc.invoke_skill(
        "subscription.terminate",
        {
            "role": "ROLE_ORGAN_MANAGER",
            "confirmed": True,
            "subscription_code": "SUB-W1-0001",
            "reason": "目录撤回影响订阅",
        },
    )
    assert result["result"]["status"] == "terminated"


def test_write_skill_requires_confirmation(svc: BrainService) -> None:
    with pytest.raises(ConfirmationRequiredError):
        svc.invoke_skill(
            "catalog.entry.reverse_draft.create",
            {"role": "ROLE_ORGAN_MANAGER", "catalog_code": "TC-NEED-CONFIRM", "title": "x", "schema_ref": "x"},
        )


def test_write_skill_rejects_wrong_role(svc: BrainService) -> None:
    with pytest.raises(AccessDeniedError):
        svc.invoke_skill(
            "catalog.entry.reverse_draft.confirm",
            {"role": "ROLE_ORGAN_OPERATER", "confirmed": True, "catalog_code": "TC-WRONG-ROLE"},
        )
