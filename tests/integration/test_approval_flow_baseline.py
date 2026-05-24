# Wave: 2
# Engine: 审批流基线 + J1 集成（E3 三引擎 F2）
# Covers: AC1（plan 停止条件：J1 申请按 shared_type=1/2 自动选择对应基线流程）
"""F2 — Seeder idempotent + start_workflow + J1 申请提交 hook e2e。

不动 F1/F3/F4/F5/F6 任何落地物；J1 hook 失败不破业务主路径（D4）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F2_approval_flow_baseline_shadow.db"


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
    yield


@pytest.fixture()
def session():
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        yield s


# ──────────────────────────────────────────────────────────────────────────
# Seeder
# ──────────────────────────────────────────────────────────────────────────

def test_seeder_creates_both_baselines_idempotent(session):
    from sqlalchemy import select

    from zw_brain.domain.approval_flow_baseline import (
        BASELINE_CONDITIONAL_CODE,
        BASELINE_UNCONDITIONAL_CODE,
        ApprovalFlowBaselineSeeder,
    )
    from zw_brain.domain.models import ApprovalFlowSchemaRecord

    seeder = ApprovalFlowBaselineSeeder(session)
    result1 = seeder.seed_all(tenant_id="sd-default")
    assert BASELINE_CONDITIONAL_CODE in result1
    assert BASELINE_UNCONDITIONAL_CODE in result1
    n_after_first = session.execute(
        select(ApprovalFlowSchemaRecord).where(ApprovalFlowSchemaRecord.tenant_id == "sd-default")
    ).all()
    # 跑第二次必须 idempotent
    result2 = seeder.seed_all(tenant_id="sd-default")
    n_after_second = session.execute(
        select(ApprovalFlowSchemaRecord).where(ApprovalFlowSchemaRecord.tenant_id == "sd-default")
    ).all()
    assert len(n_after_first) == len(n_after_second)
    assert result1[BASELINE_CONDITIONAL_CODE].id == result2[BASELINE_CONDITIONAL_CODE].id


def test_seeder_conditional_has_4_approval_nodes(session):
    from zw_brain.domain.approval_flow_baseline import (
        BASELINE_CONDITIONAL_CODE,
        ApprovalFlowBaselineSeeder,
    )

    seeder = ApprovalFlowBaselineSeeder(session)
    result = seeder.seed_all(tenant_id="sd-default")
    conditional = result[BASELINE_CONDITIONAL_CODE]
    nodes = conditional.payload_json["nodes"]
    approval = [n for n in nodes if n["node_type"] == "approval"]
    assert len(approval) == 4
    kinds = {r["rule_kind"] for r in conditional.payload_json["selection_rules"]}
    assert {"role", "org_unit", "org_unit_leader"} <= kinds


def test_seeder_unconditional_has_1_approval_node(session):
    from zw_brain.domain.approval_flow_baseline import (
        BASELINE_UNCONDITIONAL_CODE,
        ApprovalFlowBaselineSeeder,
    )

    seeder = ApprovalFlowBaselineSeeder(session)
    result = seeder.seed_all(tenant_id="sd-default")
    unconditional = result[BASELINE_UNCONDITIONAL_CODE]
    nodes = unconditional.payload_json["nodes"]
    approval = [n for n in nodes if n["node_type"] == "approval"]
    assert len(approval) == 1


def test_get_baseline_for_shared_type_1_returns_conditional(session):
    from zw_brain.domain.approval_flow_baseline import (
        BASELINE_CONDITIONAL_CODE,
        ApprovalFlowBaselineSeeder,
    )

    seeder = ApprovalFlowBaselineSeeder(session)
    seeder.seed_all(tenant_id="sd-default")
    baseline = seeder.get_baseline_for_shared_type("sd-default", 1)
    assert baseline is not None
    assert baseline.schema_code == BASELINE_CONDITIONAL_CODE


def test_get_baseline_for_shared_type_2_returns_unconditional(session):
    from zw_brain.domain.approval_flow_baseline import (
        BASELINE_UNCONDITIONAL_CODE,
        ApprovalFlowBaselineSeeder,
    )

    seeder = ApprovalFlowBaselineSeeder(session)
    seeder.seed_all(tenant_id="sd-default")
    baseline = seeder.get_baseline_for_shared_type("sd-default", 2)
    assert baseline is not None
    assert baseline.schema_code == BASELINE_UNCONDITIONAL_CODE


def test_get_baseline_for_unknown_shared_type_returns_none(session):
    from zw_brain.domain.approval_flow_baseline import ApprovalFlowBaselineSeeder

    seeder = ApprovalFlowBaselineSeeder(session)
    seeder.seed_all(tenant_id="sd-default")
    assert seeder.get_baseline_for_shared_type("sd-default", 99) is None
    assert seeder.get_baseline_for_shared_type("sd-default", None) is None
    assert seeder.get_baseline_for_shared_type("sd-default", "abc") is None


# ──────────────────────────────────────────────────────────────────────────
# start_approval_workflow_from_baseline
# ──────────────────────────────────────────────────────────────────────────

def test_start_workflow_creates_case_and_steps_from_baseline(session):
    from sqlalchemy import select

    from zw_brain.domain.approval_flow_baseline import (
        ApprovalFlowBaselineSeeder,
        start_approval_workflow_from_baseline,
    )
    from zw_brain.domain.models import ApprovalStepRecord

    ApprovalFlowBaselineSeeder(session).seed_all(tenant_id="sd-default")
    case = start_approval_workflow_from_baseline(
        session,
        application_code="APP-TEST-001",
        tenant_id="sd-default",
        shared_type=1,
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:test",
    )
    assert case is not None
    # baseline 写 application_code 加 #baseline 后缀避免与 legacy upsert 路径冲突
    assert case.application_code == "APP-TEST-001#baseline"
    assert case.current_status == "in_progress"
    steps = session.execute(
        select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case.id).order_by(ApprovalStepRecord.step_no)
    ).scalars().all()
    assert len(steps) == 4  # conditional baseline
    assert steps[0].status == "pending"
    assert steps[0].started_at is not None  # 第 1 步 started
    assert steps[1].started_at is None
    # selection_rule 投影
    assert "selection_rule" in steps[0].approver_scope_json


def test_start_workflow_with_no_baseline_returns_none_no_throw(session):
    from zw_brain.domain.approval_flow_baseline import start_approval_workflow_from_baseline

    # 不调 seeder：empty-tenant 无任何 baseline → None
    result = start_approval_workflow_from_baseline(
        session,
        application_code="APP-NIL",
        tenant_id="empty-tenant",
        shared_type=1,
        submitted_by="user:gov:ROLE_ORGAN_OPERATER:test",
    )
    assert result is None

    # 已 seed sd-default，但 shared_type 不在 {1,2}
    from zw_brain.domain.approval_flow_baseline import ApprovalFlowBaselineSeeder
    ApprovalFlowBaselineSeeder(session).seed_all(tenant_id="sd-default")
    result2 = start_approval_workflow_from_baseline(
        session,
        application_code="APP-NIL-2",
        tenant_id="sd-default",
        shared_type=99,
        submitted_by="x",
    )
    assert result2 is None


# ──────────────────────────────────────────────────────────────────────────
# J1 dispatch e2e
# ──────────────────────────────────────────────────────────────────────────

def _new_brain_and_seed():
    from zw_brain.command.brain import BrainService
    from zw_brain.domain.approval_flow_baseline import ApprovalFlowBaselineSeeder
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.db import create_session_factory
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        ApprovalFlowBaselineSeeder(s).seed_all(tenant_id="sd-default")
    brain = BrainService(state_store=ss)
    # 清空 seed snapshot 中的 pending requests，避免与新建申请冲突
    brain._snapshot["requests"] = []
    return brain, audit_bus


def _next_resource_id() -> str:
    # res-jbxx-ledger 是 seed_snapshot.discovery.resources 内可解析的资源；
    # 用 _new_brain_and_seed 先清 snapshot.requests 避免 "active request already exists" 冲突
    return "res-jbxx-ledger"


def _submit_and_get_case(brain, shared_type, resource_id: str | None = None):
    rid = resource_id or _next_resource_id()
    res = brain.invoke_skill(
        "application.resource.submit",
        {
            "resource_id": rid,
            "confirmed": True,
            "role": "ROLE_ORGAN_OPERATER",
            "purpose": "F2 baseline e2e",
            "shared_type": shared_type,
        },
    )
    return res


def test_j1_application_submit_with_shared_type_1_triggers_conditional_baseline():
    from sqlalchemy import select

    from zw_brain.domain.models import ApprovalCaseRecord, ApprovalStepRecord
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.db import create_session_factory

    brain, _ = _new_brain_and_seed()
    try:
        result = _submit_and_get_case(brain, 1)
    finally:
        audit_bus.clear_sink()
    assert result["ok"] is True
    approval_case_id = result["result"].get("approval_case_id")
    assert approval_case_id, "shared_type=1 应触发 baseline 并返回 approval_case_id"

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        case = s.get(ApprovalCaseRecord, approval_case_id)
        assert case is not None
        steps = s.execute(
            select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == approval_case_id)
        ).scalars().all()
        assert len(steps) == 4


def test_j1_application_submit_with_shared_type_2_triggers_unconditional_baseline():
    from sqlalchemy import select

    from zw_brain.domain.models import ApprovalStepRecord
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.db import create_session_factory

    brain, _ = _new_brain_and_seed()
    try:
        result = _submit_and_get_case(brain, 2)
    finally:
        audit_bus.clear_sink()
    case_id = result["result"].get("approval_case_id")
    assert case_id
    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        steps = s.execute(
            select(ApprovalStepRecord).where(ApprovalStepRecord.approval_case_id == case_id)
        ).scalars().all()
        assert len(steps) == 1


def test_j1_application_submit_with_no_shared_type_succeeds_without_baseline():
    from zw_brain.shared import audit as audit_bus

    brain, _ = _new_brain_and_seed()
    try:
        result = brain.invoke_skill(
            "application.resource.submit",
            {
                "resource_id": _next_resource_id(),
                "confirmed": True,
                "role": "ROLE_ORGAN_OPERATER",
                "purpose": "F2 no-shared-type",
                # 不传 shared_type
            },
        )
    finally:
        audit_bus.clear_sink()
    assert result["ok"] is True
    # 不应有 approval_case_id 字段（或为 None）
    assert "approval_case_id" not in result["result"]


def test_j1_application_submit_continues_if_baseline_hook_fails(monkeypatch, caplog):
    """R-001 fix: hook 失败时业务主路径不破，**且** logger.warning 必须发出（不可静默吞错）。"""
    import logging

    from zw_brain.command.handlers.j1 import request as request_handler
    from zw_brain.shared import audit as audit_bus

    def _raising(*args, **kwargs):
        raise RuntimeError("simulated baseline hook failure")

    monkeypatch.setattr(
        request_handler, "start_approval_workflow_from_baseline", _raising
    )

    brain, _ = _new_brain_and_seed()
    try:
        with caplog.at_level(logging.WARNING, logger="zw_brain.command.handlers.j1.request"):
            result = brain.invoke_skill(
                "application.resource.submit",
                {
                    "resource_id": _next_resource_id(),
                    "confirmed": True,
                    "role": "ROLE_ORGAN_OPERATER",
                    "purpose": "F2 hook fail defensive",
                    "shared_type": 1,
                },
            )
    finally:
        audit_bus.clear_sink()
    assert result["ok"] is True
    # hook 失败 → 不返 approval_case_id，但业务主路径不破
    assert "approval_case_id" not in result["result"]
    # R-001：必须有 logger.warning 记录，含 error_class / shared_type / application_code
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "approval_flow.baseline.hook.failed" in r.getMessage()]
    assert warnings, "expected logger.warning approval_flow.baseline.hook.failed (R-001 fix)"
    warn = warnings[0]
    assert getattr(warn, "error_class", None) == "RuntimeError"
    assert getattr(warn, "shared_type", None) == 1
    assert getattr(warn, "application_code", None)  # 非空
