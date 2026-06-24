# Wave: 2
# Engine: 表单 schema NL 草稿 + 三步流程（E3 三引擎 F5）
# Covers: AC2（四川 7 字段一句话→入库 e2e + deterministic NL 草稿链路）
# Not covered: UI（F7）/ J1/J2 表单页消费集成
"""F5 — NL 草稿 deterministic + draft/preview/revert/commit 三步流程 e2e。"""
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


@pytest.mark.no_db
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
# deterministic-only：zw-brain 不持有推理 SDK/env
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.no_db
def test_generate_draft_payload_uses_deterministic_without_inference(monkeypatch):
    import zw_brain.domain.form_schema_nl_draft as nl

    assert not hasattr(nl, "_inference_chat")

    payload, meta = nl.generate_draft_payload(
        "申请表：姓名、联系电话",
        tenant_id="sd-default",
    )
    assert meta["tier"] == "deterministic"
    assert meta["field_count"] == 2
    from zw_brain.domain.form_schema import _validate_payload
    _validate_payload(payload)


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


def test_nl_draft_skill_e2e():
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
                     role="ROLE_SYSTEM",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["result"]["status"] == "draft"
    assert result["result"]["source_kind"] == "nl_draft"
    assert result["result"]["payload_summary"]["field_count"] == 2


def test_promote_to_preview_skill_e2e():
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
                    role="ROLE_SYSTEM",
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
                       role="ROLE_SYSTEM",
                   )
    finally:
        audit_bus.clear_sink()

    assert promoted["result"]["status"] == "preview"


def test_revert_to_draft_skill_e2e():
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
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        reverted = invoke_trusted(
                       brain,
                       "form_schema.revert_to_draft",
                       {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                       role="ROLE_SYSTEM",
                   )
    finally:
        audit_bus.clear_sink()

    assert reverted["result"]["status"] == "draft"


def test_promote_skill_rejects_already_preview():
    from zw_brain.domain.form_schema import FormSchemaTransitionError

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
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        with pytest.raises(FormSchemaTransitionError):
            invoke_trusted(
                brain,
                "form_schema.promote_to_preview",
                {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                role="ROLE_SYSTEM",
            )
    finally:
        audit_bus.clear_sink()


# ──────────────────────────────────────────────────────────────────────────
# 四川 7 字段 e2e — AC2 关键证据
# ──────────────────────────────────────────────────────────────────────────

def test_sichuan_7_field_e2e_one_sentence_to_live():
    """一句话 → nl_draft → promote → commit → live；7 字段 + 关键 validator + JSON Schema。"""
    from zw_brain.domain.form_schema import FormSchemaRepo

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
                    role="ROLE_SYSTEM",
                )
        schema_id = draft["result"]["schema_id"]
        assert draft["result"]["payload_summary"]["field_count"] == 7
        invoke_trusted(
            brain,
            "form_schema.promote_to_preview",
            {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
            role="ROLE_SYSTEM",
        )
        committed = invoke_trusted(
                        brain,
                        "form_schema.commit",
                        {"tenant_id": "sd-default", "schema_id": schema_id, "confirmed": True, "role": "ROLE_SYSTEM"},
                        role="ROLE_SYSTEM",
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


@pytest.mark.no_db
def test_manifest_load_passes() -> None:
    from zw_brain.capability_registry.runtime import load_manifests

    m = load_manifests()
    for sid, expected_ccc in [
        ("form_schema.commit", "live"),
        ("form_schema.nl_draft", "draft"),
        ("form_schema.promote_to_preview", "preview"),
        ("form_schema.revert_to_draft", "draft"),
    ]:
        assert sid in m, f"missing manifest: {sid}"
        assert m[sid]["config_change_class"] == expected_ccc, f"{sid} ccc != {expected_ccc}"
