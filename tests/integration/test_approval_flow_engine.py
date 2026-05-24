# Wave: 2
# Engine: 审批流可视化（E3 三引擎 F1）
# Covers: AC1 第一步（数据模型 + 状态机 + commit skill 端到端）
# Not covered: NL 草稿 (F3) / J1 基线 (F2) / UI (F7)
"""F1 — 审批流模板数据模型 + 状态机 + commit skill dispatch 端到端。

数据隔离：用独立 shadow DB（ZW_BRAIN_DB_PATH 切到 tests/.data/test_F1_shadow.db），
不污染 sd-default 主库；session 级 reset_and_upgrade() 从空库重建 schema。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F1_approval_flow_shadow.db"


def _build_payload() -> dict:
    return {
        "nodes": [
            {"node_code": "start", "node_type": "start", "node_name": "开始"},
            {
                "node_code": "dept_review",
                "node_type": "approval",
                "node_name": "部门审核",
                "selection_rule_code": "dept_manager_rule",
            },
            {"node_code": "end", "node_type": "end", "node_name": "结束"},
        ],
        "selection_rules": [
            {
                "rule_code": "dept_manager_rule",
                "rule_kind": "role",
                "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"},
            }
        ],
        "branches": [
            {"from_node_code": "start", "to_node_code": "dept_review", "condition_kind": "always"},
            {"from_node_code": "dept_review", "to_node_code": "end", "condition_kind": "on_decision"},
        ],
    }


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
# 状态机基本流转
# ──────────────────────────────────────────────────────────────────────────

def test_create_draft_sets_status_draft(session):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="anshan_4level_v1",
        title="鞍山 4 级审批流",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    assert record.status == "draft"
    assert record.version == 1
    assert record.committed_at is None
    assert record.tenant_id == "sd-default"


def test_promote_draft_to_preview(session):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="promote_test",
        title="promote",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    promoted = repo.promote_to_preview(record.id)
    assert promoted.status == "preview"
    assert promoted.committed_at is None


def test_revert_preview_to_draft(session):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="revert_test",
        title="revert",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)
    reverted = repo.revert_to_draft(record.id)
    assert reverted.status == "draft"


def test_commit_preview_to_live_bumps_version_and_sets_committed_at(session):
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="commit_test",
        title="commit",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)
    live = repo.commit_to_live(record.id)
    assert live.status == "live"
    assert live.version == 2
    assert live.committed_at is not None


# ──────────────────────────────────────────────────────────────────────────
# 非法转换
# ──────────────────────────────────────────────────────────────────────────

def test_invalid_transition_draft_to_live_raises(session):
    from zw_brain.domain.approval_flow_schema import (
        ApprovalFlowSchemaRepo,
        ApprovalFlowTransitionError,
    )

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="bad_draft_to_live",
        title="bad",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    with pytest.raises(ApprovalFlowTransitionError):
        repo.commit_to_live(record.id)


def test_invalid_transition_live_to_anything_raises(session):
    from zw_brain.domain.approval_flow_schema import (
        ApprovalFlowSchemaRepo,
        ApprovalFlowTransitionError,
    )

    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="bad_live_to_x",
        title="bad",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)
    repo.commit_to_live(record.id)
    with pytest.raises(ApprovalFlowTransitionError):
        repo.promote_to_preview(record.id)
    with pytest.raises(ApprovalFlowTransitionError):
        repo.revert_to_draft(record.id)
    with pytest.raises(ApprovalFlowTransitionError):
        repo.commit_to_live(record.id)


# ──────────────────────────────────────────────────────────────────────────
# payload 结构校验
# ──────────────────────────────────────────────────────────────────────────

def test_payload_validation_requires_unique_start_end(session):
    from zw_brain.domain.approval_flow_schema import (
        ApprovalFlowPayloadError,
        ApprovalFlowSchemaRepo,
    )

    payload = _build_payload()
    payload["nodes"].append({"node_code": "extra_end", "node_type": "end", "node_name": "重复结束"})

    repo = ApprovalFlowSchemaRepo(session)
    with pytest.raises(ApprovalFlowPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            schema_code="dup_end",
            title="dup_end",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_branches_must_reference_known_nodes(session):
    from zw_brain.domain.approval_flow_schema import (
        ApprovalFlowPayloadError,
        ApprovalFlowSchemaRepo,
    )

    payload = _build_payload()
    payload["branches"].append(
        {"from_node_code": "ghost_node", "to_node_code": "end", "condition_kind": "always"}
    )
    repo = ApprovalFlowSchemaRepo(session)
    with pytest.raises(ApprovalFlowPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            schema_code="bad_branch",
            title="bad_branch",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


# ──────────────────────────────────────────────────────────────────────────
# Dispatch 端到端：BrainService.invoke_skill('approval_flow.schema.commit')
# ──────────────────────────────────────────────────────────────────────────

def test_commit_via_skill_dispatch_returns_ok_and_audit_id(session):
    from zw_brain.command.brain import BrainService
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    # 准备一个 preview 状态的模板
    repo = ApprovalFlowSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        schema_code="dispatch_e2e",
        title="dispatch_e2e",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)

    # BrainService 走 dispatch（审计 sink 强制同步落库，D4）
    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    try:
        brain = BrainService(state_store=ss)
        result = brain.invoke_skill(
            "approval_flow.schema.commit",
            {
                "tenant_id": "sd-default",
                "schema_id": record.id,
                "confirmed": True,
                "role": "ROLE_ORGAN_MANAGER",
            },
        )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["skill_id"] == "approval_flow.schema.commit"
    assert result["audit_id"]
    payload = result["result"]
    assert payload["schema_id"] == record.id
    assert payload["version"] == 2
    assert payload["committed_at"] is not None


def test_manifest_registered_and_validates() -> None:
    """commit manifest 通过 validate_manifest 且 config_change_class=live。"""
    from zw_brain.skill_registration.runtime import load_manifests

    manifests = load_manifests()
    assert "approval_flow.schema.commit" in manifests
    m = manifests["approval_flow.schema.commit"]
    assert m["config_change_class"] == "live"
    assert m["audit_class"] == "write-critical"
    assert m["human_confirmation_required"] is True
    assert m["product_scope"] == {"journey": "b1", "status": "live"}
