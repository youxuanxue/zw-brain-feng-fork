# Wave: 2
# Engine: 审批流 NL 草稿 + 三步流程（E3 三引擎 F3）
# Covers: AC1（鞍山 4 级一句话→入库 e2e + 3-tier 降级链路）
# Not covered: UI（F7）/ J1 集成（F2）
"""F3 — NL 草稿 3-tier + draft/preview/revert/commit 三步流程 e2e。

LLM 调用必须经 zw_brain.shared.inference.client（preflight 段 10 守卫）；
本测试用 monkeypatch 拦截 _inference_chat，证明走的是 shared client 不直连第三方。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F3_approval_flow_nl_shadow.db"


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
# Tier 1 deterministic
# ──────────────────────────────────────────────────────────────────────────

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
# Tier 2 / 3 LLM + fallback（mock）
# ──────────────────────────────────────────────────────────────────────────

def test_generate_draft_payload_falls_back_when_inference_unavailable(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    def _fake_chat(*args, **kwargs):
        raise InferenceError("base_url missing in test env")

    monkeypatch.setattr(nl, "_inference_chat", _fake_chat)
    payload, meta = nl.generate_draft_payload(
        "二级审批流程",
        tenant_id="sd-default",
    )
    assert "fallback_reason" in meta
    assert meta["tier"] == "llm-fallback"
    # 兜底也必须是 valid payload
    from zw_brain.domain.approval_flow_schema import _validate_payload
    _validate_payload(payload)


def test_generate_draft_payload_uses_llm_when_available(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import ChatResult

    valid_llm_json = (
        '{"nodes": ['
        '{"node_code": "start", "node_type": "start", "node_name": "开始"},'
        '{"node_code": "level1", "node_type": "approval", "node_name": "经办审批", "selection_rule_code": "default_manager"},'
        '{"node_code": "level2", "node_type": "approval", "node_name": "部门复核", "selection_rule_code": "default_manager"},'
        '{"node_code": "end", "node_type": "end", "node_name": "结束"}'
        '],'
        '"selection_rules": [{"rule_code": "default_manager", "rule_kind": "role", "rule_payload_json": {"role_code": "ROLE_ORGAN_MANAGER"}}],'
        '"branches": ['
        '{"from_node_code": "start", "to_node_code": "level1", "condition_kind": "always"},'
        '{"from_node_code": "level1", "to_node_code": "level2", "condition_kind": "on_decision"},'
        '{"from_node_code": "level2", "to_node_code": "end", "condition_kind": "on_decision"}'
        ']}'
    )

    captured: dict = {}

    def _fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return ChatResult(text=valid_llm_json, model="claude-sonnet-4-7", usage={}, finish_reason="stop")

    monkeypatch.setattr(nl, "_inference_chat", _fake_chat)
    payload, meta = nl.generate_draft_payload(
        "经办审批和部门复核两级",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "llm"
    assert len(payload["nodes"]) == 4
    # 证明走的是 shared.inference.client（含 request_id D4 trail）
    assert "messages" in captured
    assert captured["kwargs"]["model"] == "claude-sonnet-4-7"
    assert captured["kwargs"]["request_id"]


def test_generate_draft_payload_rejects_invalid_llm_json(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import ChatResult

    def _fake_chat(*args, **kwargs):
        return ChatResult(text="this is not json", model="claude-sonnet-4-7", usage={}, finish_reason="stop")

    monkeypatch.setattr(nl, "_inference_chat", _fake_chat)
    payload, meta = nl.generate_draft_payload(
        "5 级审批",
        tenant_id="sd-default",
    )
    # 非法 JSON 走 Tier 3 fallback：deterministic 兜底，meta 携带 fallback_reason
    assert meta["tier"] == "llm-fallback"
    assert "json_decode_error" in meta["fallback_reason"]
    # deterministic 兜底是 5 级 → 7 节点
    assert len(payload["nodes"]) == 7


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


def test_nl_draft_skill_e2e(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test mock")))

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
                     role="ROLE_ORGAN_MANAGER",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["skill_id"] == "approval_flow.nl_draft"
    res = result["result"]
    assert res["status"] == "draft"
    assert res["source_kind"] == "nl_draft"
    assert res["payload_summary"]["node_count"] == 5  # start + 3 approval + end


def test_promote_to_preview_skill_e2e(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test mock")))

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
                    role="ROLE_ORGAN_MANAGER",
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
                       role="ROLE_ORGAN_MANAGER",
                   )
    finally:
        audit_bus.clear_sink()

    assert promoted["ok"] is True
    assert promoted["result"]["status"] == "preview"


def test_revert_to_draft_skill_e2e(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test mock")))

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
                    role="ROLE_ORGAN_MANAGER",
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
            role="ROLE_ORGAN_MANAGER",
        )
        reverted = invoke_trusted(
                       brain,
                       "approval_flow.schema.revert_to_draft",
                       {
                "tenant_id": "sd-default",
                "schema_id": schema_id,
                "confirmed": True,
            },
                       role="ROLE_ORGAN_MANAGER",
                   )
    finally:
        audit_bus.clear_sink()

    assert reverted["result"]["status"] == "draft"


def test_promote_skill_rejects_already_preview(monkeypatch):
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.domain.approval_flow_schema import ApprovalFlowTransitionError
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test mock")))

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
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
            role="ROLE_ORGAN_MANAGER",
        )
        with pytest.raises(ApprovalFlowTransitionError):
            invoke_trusted(
                brain,
                "approval_flow.schema.promote_to_preview",
                {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
                role="ROLE_ORGAN_MANAGER",
            )
    finally:
        audit_bus.clear_sink()


# ──────────────────────────────────────────────────────────────────────────
# 鞍山 4 级 e2e — AC1 关键证据
# ──────────────────────────────────────────────────────────────────────────

def test_anshan_4_level_e2e_one_sentence_to_live(monkeypatch):
    """一句话 → nl_draft → promote → commit → live；4 个 approval 节点 + audit chain。"""
    import zw_brain.domain.approval_flow_nl_draft as nl
    from zw_brain.domain.approval_flow_schema import ApprovalFlowSchemaRepo
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("anshan e2e mock")))

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
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        assert draft["result"]["payload_summary"]["node_count"] == 6  # start + 4 approval + end
        invoke_trusted(
            brain,
            "approval_flow.schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
            role="ROLE_ORGAN_MANAGER",
        )
        committed = invoke_trusted(
                        brain,
                        "approval_flow.schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
                        role="ROLE_ORGAN_MANAGER",
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


def test_manifest_load_passes() -> None:
    from zw_brain.skill_registration.runtime import load_manifests

    m = load_manifests()
    for sid, expected_ccc in [
        ("approval_flow.schema.commit", "live"),
        ("approval_flow.nl_draft", "draft"),
        ("approval_flow.schema.promote_to_preview", "preview"),
        ("approval_flow.schema.revert_to_draft", "draft"),
    ]:
        assert sid in m, f"missing manifest: {sid}"
        assert m[sid]["config_change_class"] == expected_ccc, f"{sid} ccc != {expected_ccc}"
