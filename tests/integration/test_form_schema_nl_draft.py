# Wave: 2
# Engine: 表单 schema NL 草稿 + 三步流程（E3 三引擎 F5）
# Covers: AC2（四川 7 字段一句话→入库 e2e + 3-tier 降级链路）
# Not covered: UI（F7）/ J1/J2 表单页消费集成
"""F5 — NL 草稿 3-tier + draft/preview/revert/commit 三步流程 e2e。

LLM 调用必须经 zw_brain.shared.inference.client；本测试用 monkeypatch 拦截
_inference_chat 证明走的是 shared client 不直连第三方。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F5_form_schema_nl_shadow.db"


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

def test_generate_draft_payload_deterministic_7_field_form():
    from zw_brain.domain.form_schema_nl_draft import generate_draft_payload

    payload, meta = generate_draft_payload(
        "四川申请表单：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件",
        tenant_id="sd-default",
        deterministic_only=True,
    )
    assert len(payload["fields"]) == 7
    assert meta["tier"] == "deterministic"
    assert meta["matched_pattern"] == "field_aliases"
    assert meta["field_count"] == 7


def test_generate_draft_payload_recognizes_common_field_names():
    from zw_brain.domain.form_schema_nl_draft import generate_draft_payload

    payload, _ = generate_draft_payload(
        "申请表：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件",
        tenant_id="sd-default",
        deterministic_only=True,
    )
    codes_to_types = {f["field_code"]: f["field_type"] for f in payload["fields"]}
    assert codes_to_types["applicant_name"] == "text"
    assert codes_to_types["id_card"] == "text"
    assert codes_to_types["phone"] == "text"
    assert codes_to_types["applicant_org"] == "text"
    assert codes_to_types["apply_reason"] == "textarea"
    assert codes_to_types["apply_date"] == "date"
    assert codes_to_types["attachment"] == "file"

    # 身份证 → regex；联系电话 → length；附件 → file_size
    validators_by_field: dict[str, set[str]] = {}
    for v in payload["validators"]:
        validators_by_field.setdefault(v["applies_to_field_code"], set()).add(v["validator_kind"])
    assert "regex" in validators_by_field["id_card"]
    assert "length" in validators_by_field["phone"]
    assert "file_size" in validators_by_field["attachment"]


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / 3 LLM mock + fallback
# ──────────────────────────────────────────────────────────────────────────

def test_generate_draft_payload_falls_back_when_inference_unavailable(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test")))

    payload, meta = nl.generate_draft_payload(
        "申请表：姓名、联系电话",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "llm-fallback"
    assert "fallback_reason" in meta
    # 兜底必须 valid
    from zw_brain.domain.form_schema import _validate_payload
    _validate_payload(payload)


def test_generate_draft_payload_uses_llm_when_available(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import ChatResult

    valid_json = (
        '{"sections": [{"section_code": "basic", "title": "基本信息"}],'
        '"fields": ['
        '{"field_code": "applicant_name", "section_code": "basic", "field_name": "姓名", "field_type": "text", "required": true}'
        '], "validators": []}'
    )
    captured: dict = {}

    def _fake_chat(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return ChatResult(text=valid_json, model="claude-sonnet-4-7", usage={}, finish_reason="stop")

    monkeypatch.setattr(nl, "_inference_chat", _fake_chat)
    payload, meta = nl.generate_draft_payload(
        "只要姓名",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "llm"
    assert len(payload["fields"]) == 1
    assert captured["kwargs"]["model"] == "claude-sonnet-4-7"
    assert captured["kwargs"]["request_id"]


def test_generate_draft_payload_rejects_invalid_llm_json(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import ChatResult

    monkeypatch.setattr(
        nl,
        "_inference_chat",
        lambda *a, **k: ChatResult(text="not json at all", model="claude-sonnet-4-7", usage={}, finish_reason="stop"),
    )
    payload, meta = nl.generate_draft_payload(
        "申请表：姓名、身份证号、联系电话、单位、事由、申请日期、附件",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "llm-fallback"
    assert "json_decode_error" in meta["fallback_reason"]
    # deterministic 兜底应识别到 7 字段
    assert len(payload["fields"]) == 7


# ──────────────────────────────────────────────────────────────────────────
# 落库
# ──────────────────────────────────────────────────────────────────────────

def test_generate_draft_creates_record_with_source_kind_nl_draft(session):
    from zw_brain.domain.form_schema import FormSchemaRepo
    from zw_brain.domain.form_schema_nl_draft import generate_draft

    repo = FormSchemaRepo(session)
    record, meta = generate_draft(
        repo,
        tenant_id="sd-default",
        form_code="nl_draft_v1",
        title="申请表",
        intent_text="申请表：姓名、联系电话",
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        deterministic_only=True,
    )
    assert record.status == "draft"
    assert record.source_kind == "nl_draft"
    assert meta["tier"] == "deterministic"


# ──────────────────────────────────────────────────────────────────────────
# Skill dispatch
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
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test")))

    brain, audit_bus, _ = _new_brain()
    try:
        result = invoke_trusted(
                     brain,
                     "form_schema.nl_draft",
                     {
                "tenant_id": "sd-default",
                "form_code": "e2e_nl_v1",
                "title": "申请表",
                "intent_text": "申请表：姓名、联系电话",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                     role="ROLE_ORGAN_MANAGER",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["result"]["status"] == "draft"
    assert result["result"]["source_kind"] == "nl_draft"
    assert result["result"]["payload_summary"]["field_count"] == 2


def test_promote_to_preview_skill_e2e(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test")))

    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "form_schema.nl_draft",
                    {
                "tenant_id": "sd-default",
                "form_code": "e2e_promote_v1",
                "title": "申请表",
                "intent_text": "申请表：姓名",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        promoted = invoke_trusted(
                       brain,
                       "form_schema.promote_to_preview",
                       {
                "tenant_id": "sd-default",
                "schema_id": schema_id,
                "confirmed": True,
            },
                       role="ROLE_ORGAN_MANAGER",
                   )
    finally:
        audit_bus.clear_sink()

    assert promoted["result"]["status"] == "preview"


def test_revert_to_draft_skill_e2e(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test")))

    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "form_schema.nl_draft",
                    {
                "tenant_id": "sd-default",
                "form_code": "e2e_revert_v1",
                "title": "申请表",
                "intent_text": "申请表：姓名",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
            role="ROLE_ORGAN_MANAGER",
        )
        reverted = invoke_trusted(
                       brain,
                       "form_schema.revert_to_draft",
                       {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
                       role="ROLE_ORGAN_MANAGER",
                   )
    finally:
        audit_bus.clear_sink()

    assert reverted["result"]["status"] == "draft"


def test_promote_skill_rejects_already_preview(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.domain.form_schema import FormSchemaTransitionError
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("test")))

    brain, audit_bus, _ = _new_brain()
    try:
        draft = invoke_trusted(
                    brain,
                    "form_schema.nl_draft",
                    {
                "tenant_id": "sd-default",
                "form_code": "e2e_dup_v1",
                "title": "申请表",
                "intent_text": "申请表：姓名",
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:e2e",
            },
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
            role="ROLE_ORGAN_MANAGER",
        )
        with pytest.raises(FormSchemaTransitionError):
            invoke_trusted(
                brain,
                "form_schema.promote_to_preview",
                {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
                role="ROLE_ORGAN_MANAGER",
            )
    finally:
        audit_bus.clear_sink()


# ──────────────────────────────────────────────────────────────────────────
# 四川 7 字段 e2e — AC2 关键证据
# ──────────────────────────────────────────────────────────────────────────

def test_sichuan_7_field_e2e_one_sentence_to_live(monkeypatch):
    """一句话 → nl_draft → promote → commit → live；7 字段 + 关键 validator + JSON Schema。"""
    import zw_brain.domain.form_schema_nl_draft as nl
    from zw_brain.domain.form_schema import FormSchemaRepo
    from zw_brain.shared.inference.client import InferenceError

    monkeypatch.setattr(nl, "_inference_chat", lambda *a, **k: (_ for _ in ()).throw(InferenceError("sichuan e2e mock")))

    brain, audit_bus, _ = _new_brain()
    intent = "四川申请表单：姓名、身份证号、联系电话、单位、申请事由、申请日期、附件"
    try:
        draft = invoke_trusted(
                    brain,
                    "form_schema.nl_draft",
                    {
                "tenant_id": "sd-default",
                "form_code": "sichuan_7field_e2e_v1",
                "title": "四川 7 字段表单",
                "intent_text": intent,
                "created_by": "user:gov:ROLE_ORGAN_MANAGER:sichuan",
            },
                    role="ROLE_ORGAN_MANAGER",
                )
        schema_id = draft["result"]["schema_id"]
        assert draft["result"]["payload_summary"]["field_count"] == 7
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
            role="ROLE_ORGAN_MANAGER",
        )
        committed = invoke_trusted(
                        brain,
                        "form_schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_ORGAN_MANAGER"},
                        role="ROLE_ORGAN_MANAGER",
                    )
    finally:
        audit_bus.clear_sink()

    res = committed["result"]
    assert res["version"] == 2
    assert res["committed_at"]

    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as s:
        repo = FormSchemaRepo(s)
        record = repo.get(schema_id)
        assert record.status == "live"
        assert record.source_kind == "nl_draft"
        assert record.draft_source_text == intent
        assert len(record.payload_json["fields"]) == 7
        # 关键 validator 必到位
        v_by_field: dict[str, set[str]] = {}
        for v in record.payload_json["validators"]:
            v_by_field.setdefault(v["applies_to_field_code"], set()).add(v["validator_kind"])
        assert "regex" in v_by_field["id_card"]
        assert "length" in v_by_field["phone"]
        assert "file_size" in v_by_field["attachment"]
        # JSON Schema 投影含 7 properties
        json_schema = FormSchemaRepo.to_json_schema(record)
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert len(json_schema["properties"]) == 7
        assert json_schema["properties"]["id_card"].get("pattern")

    # audit chain：nl_draft / promote / commit 三个 skill_id 全部留痕
    from sqlalchemy import select as sql_select

    from zw_brain.domain.models import AuditEventRecord
    with SessionLocal() as s:
        skills_seen = {
            row[0]
            for row in s.execute(sql_select(AuditEventRecord.skill_id).where(AuditEventRecord.skill_id.like("form_schema%"))).all()
        }
    assert {"form_schema.nl_draft", "form_schema.promote_to_preview", "form_schema.commit"} <= skills_seen


def test_manifest_load_passes() -> None:
    from zw_brain.skill_registration.runtime import load_manifests

    m = load_manifests()
    for sid, expected_ccc in [
        ("form_schema.commit", "live"),
        ("form_schema.nl_draft", "draft"),
        ("form_schema.promote_to_preview", "preview"),
        ("form_schema.revert_to_draft", "draft"),
    ]:
        assert sid in m, f"missing manifest: {sid}"
        assert m[sid]["config_change_class"] == expected_ccc, f"{sid} ccc != {expected_ccc}"
