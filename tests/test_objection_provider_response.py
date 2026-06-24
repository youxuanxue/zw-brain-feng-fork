"""F4 提供方异议响应 — provider inbox 投影 + reply/review 闭环."""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db() -> None:
    """conftest autouse 已为每个测试提供干净、已迁移的空 PG 克隆库。本 fixture 保留为显式依赖标记。"""
    yield None


@pytest.fixture()
def brain(temp_db: None) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_provider_investigating_case() -> str:
    created = ObjectionRepository().create_case(
        {
            "objection_kind": "catalog_quality",
            "target_type": "catalog",
            "target_id": "cat-obj-inbox-001",
            "title": "提供方待响应异议",
            "complainant_org_id": "ORG-A",
            "provider_org_id": "ORG-B",
            "status": "provider_investigating",
        },
        tenant_id=TENANT,
    )
    return created.id


def test_manager_snapshot_includes_provider_objection_inbox(brain: BrainService) -> None:
    case_id = _seed_provider_investigating_case()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    rows = snap["provider"]["objection_cases"]
    assert isinstance(rows, list)
    assert any(row["id"] == case_id for row in rows)
    row = next(item for item in rows if item["id"] == case_id)
    assert row["title"] == "提供方待响应异议"
    assert row["status"] == "provider_investigating"


def test_operater_snapshot_redacts_provider_objection_inbox(brain: BrainService) -> None:
    _seed_provider_investigating_case()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER")
    assert snap["provider"]["objection_cases"] == []


def test_objection_reply_then_review_resolve_updates_provider_inbox(brain: BrainService) -> None:
    case_id = _seed_provider_investigating_case()
    common = {"objection_id": case_id, "confirmed": True}

    reply = invoke_trusted(
        brain,
        "objection.case.reply",
        {
            **common,
            "node_name": "提供方部门核查回复",
            "opinion": "已核实字段描述",
            "action_result": "submitted",
        },
        role="ROLE_ORGAN_MANAGER",
    )["result"]
    assert reply["status"] == "provider_investigating"

    mid = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    assert any(row["id"] == case_id for row in mid["provider"]["objection_cases"])

    resolved = invoke_trusted(
        brain,
        "objection.case.review",
        {**common, "decision": "resolve", "resolved_summary": "字段已修正"},
        role="ROLE_ORGAN_MANAGER",
    )["result"]
    assert resolved["status"] == "resolved"

    after = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    inbox_ids = {row["id"] for row in after["provider"]["objection_cases"]}
    assert case_id not in inbox_ids


# ──────────────────────────────────────────────────────────────────────
# D57①（R-6）：异议受理面接通——收件箱纳入 submitted 态 + objection.case.accept 点到底
# ──────────────────────────────────────────────────────────────────────


def _seed_submitted_case(target_type: str = "catalog", target_id: str = "cat-obj-accept-001") -> str:
    created = ObjectionRepository().create_case(
        {
            "objection_kind": "catalog_quality",
            "target_type": target_type,
            "target_id": target_id,
            "title": "待受理异议",
            "complainant_org_id": "ORG-A",
            "provider_org_id": "ORG-B",
            "status": "submitted",
        },
        tenant_id=TENANT,
    )
    return created.id


def test_submitted_case_enters_provider_objection_inbox(brain: BrainService) -> None:
    """D57①：submitted 态案件进入异议收件箱（此前只列 provider_investigating，待受理
    案件在唯一工作面不可见=「有待办、点不到可办理处」的病根）。"""
    case_id = _seed_submitted_case()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    rows = snap["provider"]["objection_cases"]
    row = next((item for item in rows if item["id"] == case_id), None)
    assert row is not None, "submitted 态案件应出现在异议收件箱"
    assert row["status"] == "submitted"
    assert row["target_label"] == "catalog:cat-obj-accept-001"
    assert row["target_href"] == "#/provider/catalog/cat-obj-accept-001"


def test_provider_objection_inbox_target_link_encodes_catalog_code(brain: BrainService) -> None:
    """供方异议响应必须能跳到关联目录/资源；目录码可能含 /，href 必须编码后进入 hash 路由。"""
    case_id = _seed_submitted_case(target_id="370000308004000000/000001")
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    row = next(item for item in snap["provider"]["objection_cases"] if item["id"] == case_id)
    assert row["target_label"] == "catalog:370000308004000000/000001"
    assert row["target_href"] == "#/provider/catalog/370000308004000000%2F000001"


def test_workbench_objection_todo_counts_pending_acceptance_only(brain: BrainService) -> None:
    """工作台待办是“待受理异议”，只等于 submitted；异议响应收件箱还包含核查中在办案。"""
    pending_id = _seed_submitted_case(target_id="cat-obj-wb-pending")
    investigating_id = _seed_provider_investigating_case()

    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    inbox_ids = {row["id"] for row in snap["provider"]["objection_cases"]}
    assert {pending_id, investigating_id}.issubset(inbox_ids)

    wb = invoke_trusted(brain, "workbench.view", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    todo = next(item for item in wb["todos"] if item["id"] == "backlog-objection")
    assert todo["title"] == "待受理异议 1 条"
    assert todo["href"] == "#/provider/inbox/objection"


def test_busiaudit_accept_transitions_to_platform_investigating(brain: BrainService) -> None:
    """D57①：业务运营员受理 submitted 案件——5 业务维度（catalog）按维度状态机走既有合法边
    submitted → platform_investigating（受理即进入平台核查；维度表无 accepted 态），
    受理后案件仍在收件箱（不消失成新死端）。"""
    case_id = _seed_submitted_case()
    out = invoke_trusted(
        brain,
        "objection.case.accept",
        {"objection_id": case_id, "confirmed": True},
        role="ROLE_BUSIAUDIT",
    )["result"]
    assert out["status"] == "platform_investigating"

    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_BUSIAUDIT"}, role="ROLE_BUSIAUDIT")
    rows = snap["provider"]["objection_cases"]
    row = next((item for item in rows if item["id"] == case_id), None)
    assert row is not None, "受理后案件应保留在收件箱（platform_investigating 在办态）"
    assert row["status"] == "platform_investigating"


def test_operater_denied_objection_accept(brain: BrainService) -> None:
    """双面验证负向半：部门操作员无受理权（objection.case.accept={MANAGER,BUSIAUDIT}）。"""
    from zw_brain.command.brain import AccessDeniedError

    case_id = _seed_submitted_case(target_id="cat-obj-accept-002")
    with pytest.raises(AccessDeniedError):
        invoke_trusted(
            brain,
            "objection.case.accept",
            {"objection_id": case_id, "confirmed": True},
            role="ROLE_ORGAN_OPERATER",
        )
