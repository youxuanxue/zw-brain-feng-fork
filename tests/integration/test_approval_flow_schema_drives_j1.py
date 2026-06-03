# Wave: 2
# Engine: 审批流可视化（E3 三引擎 F2 续 — 自定义 schema 驱动 J1）
# Covers: 自定义 live schema 选择 + 走查器串行 + golden baseline 回归 + fail-closed 回落
# Not covered: 条件表达式求值（本期 deliberately fail-closed，零业务需求）
"""F2 续 — committed 的自定义 live schema 真正驱动 J1（串行版）。

补 R14 执行层缝：此前 committed schema 存得下却驱动不了 J1（request.py 只问 baseline）。
本测试钉死四件事：
(1) 自定义 schema 被选中并走查成有序 steps（非 baseline）；
(2) expression 边 fail-closed 回落串行（不实现求值器）；
(3) golden 回归：无自定义 schema 时 baseline 步骤输出与改前一致；
(4) 无效/环 schema fail-closed 回落 baseline。

数据隔离：独立 shadow DB，不污染 sd-default 主库。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F2_schema_drives_j1_shadow.db"

TENANT = "sd-default"


@pytest.fixture(scope="session", autouse=True)
def _shadow_db() -> None:
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)

    from zw_brain.shared import db as _db
    _db.reset_engine_cache()

    from zw_brain.shared.migrate import reset_and_upgrade
    reset_and_upgrade()

    # baseline 两条 live schema 入库（与生产启动同构）
    from zw_brain.domain.approval_flow_baseline import seed_runtime_data
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        seed_runtime_data(s, tenant_id=TENANT)
    yield


@pytest.fixture()
def session():
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        yield s


def _serial_schema_payload(*, shared_type: int, project_code: str) -> dict:
    """3 级串行 + on_decision，scope 绑 {shared_type, project_code}。"""
    return {
        "scope": {"shared_type": shared_type, "project_code": project_code},
        "nodes": [
            {"node_code": "start", "node_type": "start", "node_name": "开始"},
            {"node_code": "n1", "node_type": "approval", "node_name": "二级部门审", "selection_rule_code": "r_mgr"},
            {"node_code": "n2", "node_type": "approval", "node_name": "一级部门审", "selection_rule_code": "r_mgr"},
            {"node_code": "n3", "node_type": "approval", "node_name": "部门负责人终审", "selection_rule_code": "r_leader"},
            {"node_code": "end", "node_type": "end", "node_name": "结束"},
        ],
        "selection_rules": [
            {"rule_code": "r_mgr", "rule_kind": "role", "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"}},
            {"rule_code": "r_leader", "rule_kind": "org_unit_leader", "rule_payload_json": {"scope": "applicant_org"}},
        ],
        "branches": [
            {"from_node_code": "start", "to_node_code": "n1", "condition_kind": "always"},
            {"from_node_code": "n1", "to_node_code": "n2", "condition_kind": "on_decision"},
            {"from_node_code": "n2", "to_node_code": "n3", "condition_kind": "on_decision"},
            {"from_node_code": "n3", "to_node_code": "end", "condition_kind": "on_decision"},
        ],
    }


def _commit_live_schema(session, payload: dict, schema_code: str):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    rec = repo.create_draft(
        tenant_id=TENANT,
        schema_code=schema_code,
        title=schema_code,
        payload=payload,
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(rec.id)
    return repo.commit_to_live(rec.id)


# ── 走查器纯函数 ────────────────────────────────────────────────────────────

def test_walker_serial_schema_yields_ordered_steps():
    from zw_brain.domain.approval_flow_walker import instantiate_steps_from_schema

    out = instantiate_steps_from_schema(_serial_schema_payload(shared_type=1, project_code="anshan"))
    steps = out["steps"]
    assert [s["step_name"] for s in steps] == ["二级部门审", "一级部门审", "部门负责人终审"]
    assert [s["step_no"] for s in steps] == [1, 2, 3]
    assert steps[0]["approver_scope_json"]["selection_rule"]["rule_kind"] == "role"
    assert out["warnings"] == []


def test_walker_expression_edge_fail_closed_serial():
    """expression 边本期 fail-closed → 当 always 走默认边 + 收 warning，不实现求值器。"""
    from zw_brain.domain.approval_flow_walker import instantiate_steps_from_schema

    payload = _serial_schema_payload(shared_type=1, project_code="anshan")
    # 把 n1→n2 改成 expression（模拟有人配了条件路由）
    for b in payload["branches"]:
        if b["from_node_code"] == "n1":
            b["condition_kind"] = "expression"
            b["condition_payload_json"] = {"field": "amount", "op": "gt", "value": 100}
    out = instantiate_steps_from_schema(payload)
    # 仍串行三级（fail-closed 走默认边），且记一条 warning
    assert [s["step_name"] for s in out["steps"]] == ["二级部门审", "一级部门审", "部门负责人终审"]
    assert any("expression-edge-fail-closed" in w for w in out["warnings"])


def test_walker_cycle_raises():
    from zw_brain.domain.approval_flow_walker import (
        ApprovalFlowWalkError,
        instantiate_steps_from_schema,
    )

    payload = _serial_schema_payload(shared_type=1, project_code="anshan")
    payload["branches"].append({"from_node_code": "n2", "to_node_code": "n1", "condition_kind": "always"})
    with pytest.raises(ApprovalFlowWalkError):
        instantiate_steps_from_schema(payload)


# ── schema 选择 ────────────────────────────────────────────────────────────

def test_find_live_for_scope_skips_baseline(session):
    """baseline 无 scope 键 → 不被当项目级覆盖；无自定义时返 None。"""
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    assert repo.find_live_for_scope(TENANT, 1, "anshan") is None


def test_find_live_for_scope_exact_project_wins(session):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    _commit_live_schema(session, _serial_schema_payload(shared_type=1, project_code="anshan"), "anshan_v1")
    repo = ApprovalFlowSchemaRepo(session)
    hit = repo.find_live_for_scope(TENANT, 1, "anshan")
    assert hit is not None and hit.schema_code == "anshan_v1"
    # 别的项目/别的 shared_type 不命中 → 回落 baseline
    assert repo.find_live_for_scope(TENANT, 1, "other_project") is None
    assert repo.find_live_for_scope(TENANT, 2, "anshan") is None


# ── schema 驱动写运行态 ────────────────────────────────────────────────────

def test_schema_drives_workflow_writes_case_and_steps(session):
    from sqlalchemy import select

    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
    from zw_brain.domain.approval_flow_walker import start_approval_workflow_from_schema
    from zw_brain.domain.models import ApprovalStepRecord

    schema = _commit_live_schema(
        session, _serial_schema_payload(shared_type=1, project_code="sichuan"), "sichuan_v1"
    )
    case = start_approval_workflow_from_schema(
        session,
        application_code="APP-SCHEMA-001",
        tenant_id=TENANT,
        schema=ApprovalFlowSchemaRepo(session).get(schema.id),
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:test",
        context={"shared_type": 1, "project_code": "sichuan"},
    )
    assert case is not None
    assert case.flow_schema_code == "sichuan_v1"
    assert case.decision_payload_json["source"] == "custom_schema"
    steps = list(
        session.execute(
            select(ApprovalStepRecord)
            .where(ApprovalStepRecord.approval_case_id == case.id)
            .order_by(ApprovalStepRecord.step_no)
        ).scalars()
    )
    assert [s.step_name for s in steps] == ["二级部门审", "一级部门审", "部门负责人终审"]
    assert steps[0].started_at is not None  # 第一步已启动


def test_maybe_start_prefers_custom_schema_else_baseline(session):
    """request.py 接线：绑了自定义 schema 走 schema；没绑走 baseline（golden）。"""
    from sqlalchemy import select

    from zw_brain.command.handlers.j1.request import _maybe_start_approval_workflow
    from zw_brain.domain.models import ApprovalCaseRecord, ApprovalStepRecord

    # (a) 绑了 jingzhou 项目 schema → schema 驱动
    _commit_live_schema(session, _serial_schema_payload(shared_type=1, project_code="jingzhou"), "jingzhou_v1")
    case_id = _maybe_start_approval_workflow(
        application_code="APP-WIRE-CUSTOM",
        tenant_id=TENANT,
        shared_type=1,
        project_code="jingzhou",
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:test",
    )
    assert case_id is not None
    case = session.get(ApprovalCaseRecord, case_id)
    assert case.flow_schema_code == "jingzhou_v1"

    # (b) 没绑项目 → 回落 baseline（shared_type=1 → 4 级 baseline）
    case_id2 = _maybe_start_approval_workflow(
        application_code="APP-WIRE-BASELINE",
        tenant_id=TENANT,
        shared_type=1,
        project_code=None,
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:test",
    )
    assert case_id2 is not None
    case2 = session.get(ApprovalCaseRecord, case_id2)
    assert case2.flow_schema_code is None  # baseline 路径不写 flow_schema_code
    steps2 = list(
        session.execute(
            select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case2.id)
        ).scalars()
    )
    assert len(steps2) == 4  # baseline 有条件 4 级，golden


# ── golden baseline 回归 ────────────────────────────────────────────────────

def test_golden_baseline_unchanged(session):
    """baseline 路径行为钉死：shared_type=1 → 4 级、shared_type=2 → 1 级。"""
    from sqlalchemy import select

    from zw_brain.domain.approval_flow_baseline import start_approval_workflow_from_baseline
    from zw_brain.domain.models import ApprovalStepRecord

    c1 = start_approval_workflow_from_baseline(
        session, application_code="APP-GOLDEN-1", tenant_id=TENANT, shared_type=1, submitted_by="x"
    )
    s1 = list(session.execute(select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == c1.id)).scalars())
    assert [s.step_name for s in sorted(s1, key=lambda r: r.step_no)] == [
        "业务管理员审核", "数据管理员审核", "申请单位部门审", "部门负责人终审",
    ]
    c2 = start_approval_workflow_from_baseline(
        session, application_code="APP-GOLDEN-2", tenant_id=TENANT, shared_type=2, submitted_by="x"
    )
    s2 = list(session.execute(select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == c2.id)).scalars())
    assert [s.step_name for s in s2] == ["数据管理员快速审核"]
