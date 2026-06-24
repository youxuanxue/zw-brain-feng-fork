# Wave: 2
# Engine: 审批流 NL 草稿 + 三步流程（E3 三引擎 F3）
# Covers: AC1（鞍山 4 级一句话→入库 e2e + deterministic NL 草稿链路）
# Not covered: UI（F7）/ J1 集成（F2）
"""F3 — NL 草稿 deterministic + draft/preview/revert/commit 三步流程 e2e。"""
from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted

# 每个测试由 root conftest 的 autouse function-scoped fixture 分到一个空 PG 克隆库；
# NL 草稿落库写进各自隔离克隆，不依赖真实旧平台数据。


@pytest.fixture()
def session():
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        yield s


# ──────────────────────────────────────────────────────────────────────────
# Tier 1 deterministic
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.no_db
def test_generate_draft_payload_deterministic_4_level_approval():
    from zw_brain.domain.approval_flow_nl_draft import generate_draft_payload

    payload, meta = generate_draft_payload(
        "鞍山 4 级审批流程",
        tenant_id="sd-default",
        deterministic_only=True,
    )
    nodes = payload["nodes"]
    # start + 4 approval + end = 6
    assert len(nodes) == 6
    assert sum(1 for n in nodes if n["node_type"] == "start") == 1
    assert sum(1 for n in nodes if n["node_type"] == "end") == 1
    assert sum(1 for n in nodes if n["node_type"] == "approval") == 4
    assert meta["tier"] == "deterministic"
    assert meta["level"] == 4


@pytest.mark.no_db
def test_generate_draft_payload_deterministic_chinese_numerals():
    from zw_brain.domain.approval_flow_nl_draft import generate_draft_payload

    payload, meta = generate_draft_payload(
        "三级会签流程",
        tenant_id="sd-default",
        deterministic_only=True,
    )
    nodes = payload["nodes"]
    assert len(nodes) == 5  # start + 3 approval + end
    assert meta["level"] == 3
    assert meta["kind"] == "会签"


# ──────────────────────────────────────────────────────────────────────────
# deterministic-only：zw-brain 不持有推理 SDK/env
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.no_db
def test_generate_draft_payload_uses_deterministic_without_inference(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl

    assert not hasattr(nl, "_inference_chat")
    payload, meta = nl.generate_draft_payload(
        "二级审批流程",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "deterministic"
    assert meta["level"] == 2
    from zw_brain.domain.approval_flow_schema import _validate_payload
    _validate_payload(payload)


# ──────────────────────────────────────────────────────────────────────────
# generate_draft 落库
# ──────────────────────────────────────────────────────────────────────────

def test_generate_draft_creates_record_with_source_kind_nl_draft(session):
    from zw_brain.domain.approval_flow_nl_draft import generate_draft
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    repo = ApprovalFlowSchemaRepo(session)
    record, meta = generate_draft(
        repo,
        tenant_id="sd-default",
        schema_code="nl_draft_v1",
        title="2 级审批",
        intent_text="2 级审批流程",
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        deterministic_only=True,
    )
    assert record.status == "draft"
    assert record.source_kind == "nl_draft"
    assert record.draft_source_text == "2 级审批流程"
    assert meta["tier"] == "deterministic"


# ──────────────────────────────────────────────────────────────────────────
# Skill dispatch 端到端
# ──────────────────────────────────────────────────────────────────────────

def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss), audit_bus, ds


def test_nl_draft_skill_e2e():
    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
                     brain,
                     "approval_flow.nl_draft",
                     {
                "tenant_id": "sd-default",
                "schema_code": "e2e_nl_draft_v1",
                "title": "3 级审批",
                "intent_text": "3 级审批流程",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                     role="ROLE_SYSTEM",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["skill_id"] == "approval_flow.nl_draft"
    res = result["result"]
    assert res["status"] == "draft"
    assert res["source_kind"] == "nl_draft"
    assert res["payload_summary"]["node_count"] == 5  # start + 3 approval + end


def test_promote_to_preview_skill_e2e():
    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "approval_flow.nl_draft",
                    {
                "tenant_id": "sd-default",
                "schema_code": "e2e_promote_v1",
                "title": "1 级审批",
                "intent_text": "1 级审批",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        promoted = invoke_trusted(
                       brain,
                       "approval_flow.schema.promote_to_preview",
                       {
                "tenant_id": "sd-default",
                "schema_id": schema_id,
                "confirmed": True,
            },
                       role="ROLE_SYSTEM",
                   )
    finally:
        audit_bus.clear_sink()

    assert promoted["ok"] is True
    assert promoted["result"]["status"] == "preview"


def test_revert_to_draft_skill_e2e():
    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "approval_flow.nl_draft",
                    {
                "tenant_id": "sd-default",
                "schema_code": "e2e_revert_v1",
                "title": "2 级审批",
                "intent_text": "2 级审批",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {
                "tenant_id": "sd-default",
                "schema_id": schema_id,
                "confirmed": True,
            },
            role="ROLE_SYSTEM",
        )
        reverted = invoke_trusted(
                       brain,
                       "approval_flow.schema.revert_to_draft",
                       {
                "tenant_id": "sd-default",
                "schema_id": schema_id,
                "confirmed": True,
            },
                       role="ROLE_SYSTEM",
                   )
    finally:
        audit_bus.clear_sink()

    assert reverted["result"]["status"] == "draft"


def test_promote_skill_rejects_already_preview():
    from zw_brain.domain.approval_flow_schema import ApprovalFlowTransitionError

    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "approval_flow.nl_draft",
                    {
                "tenant_id": "sd-default",
                "schema_code": "e2e_dup_promote_v1",
                "title": "2 级审批",
                "intent_text": "2 级审批",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        with pytest.raises(ApprovalFlowTransitionError):
            invoke_trusted(
                brain,
                "approval_flow.schema.promote_to_preview",
                {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                role="ROLE_SYSTEM",
            )
    finally:
        audit_bus.clear_sink()


# ──────────────────────────────────────────────────────────────────────────
# 鞍山 4 级 e2e — AC1 关键证据
# ──────────────────────────────────────────────────────────────────────────

def test_anshan_4_level_e2e_one_sentence_to_live():
    """一句话 → nl_draft → promote → commit → live；4 个 approval 节点 + audit chain。"""
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo

    brain, audit_bus, ds = _new_brain()
    intent = "鞍山审批流程：编制→二级部门审→一级部门审→发布，共 4 级审批"
    try:
        draft = invoke_trusted(
                    brain,
                    "approval_flow.nl_draft",
                    {
                "tenant_id": "sd-default",
                "schema_code": "anshan_4level_e2e_v1",
                "title": "鞍山 4 级审批流",
                "intent_text": intent,
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:anshan",
            },
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        assert draft["result"]["payload_summary"]["node_count"] == 6  # start + 4 approval + end
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        committed = invoke_trusted(
                        brain,
                        "approval_flow.schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                        role="ROLE_SYSTEM",
                    )
    finally:
        audit_bus.clear_sink()

    res = committed["result"]
    assert res["version"] == 2
    assert res["committed_at"]

    # 直接读 record 确认节点结构与 source_kind
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        repo = ApprovalFlowSchemaRepo(s)
        record = repo.get(schema_id)
        assert record.status == "live"
        assert record.source_kind == "nl_draft"
        assert record.draft_source_text == intent
        approval_nodes = [n for n in record.payload_json["nodes"] if n["node_type"] == "approval"]
        assert len(approval_nodes) == 4

    # audit chain：nl_draft / promote / commit 至少 3 条
    from sqlalchemy import select as sql_select

    from zw_brain.domain.models import AuditEventRecord
    with SessionLocal() as s:
        skills_seen = {
            row[0]
            for row in s.execute(sql_select(AuditEventRecord.skill_id).where(AuditEventRecord.skill_id.like("approval_flow%"))).all()
        }
    assert {"approval_flow.nl_draft", "approval_flow.schema.promote_to_preview", "approval_flow.schema.commit"} <= skills_seen


@pytest.mark.no_db
def test_manifest_load_passes() -> None:
    from zw_brain.capability_registry.runtime import load_manifests

    m = load_manifests()
    for sid, expected_ccc in [
        ("approval_flow.schema.commit", "live"),
        ("approval_flow.nl_draft", "draft"),
        ("approval_flow.schema.promote_to_preview", "preview"),
        ("approval_flow.schema.revert_to_draft", "draft"),
    ]:
        assert sid in m, f"missing manifest: {sid}"
        assert m[sid]["config_change_class"] == expected_ccc, f"{sid} ccc != {expected_ccc}"
