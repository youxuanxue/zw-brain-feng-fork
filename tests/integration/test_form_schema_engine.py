# Wave: 2
# Engine: 表单 schema 化（E3 三引擎 F4）
# Covers: AC2 第一步（数据模型 + 状态机 + JSON Schema 投影 + commit skill 端到端）
# Not covered: NL 草稿 (F5) / UI (F7) / J1/J2 表单页消费集成
"""F4 — 表单 schema 数据模型 + 状态机 + commit skill dispatch 端到端。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests._trusted_payload import invoke_trusted

REPO_ROOT = Path(__file__).resolve().parents[2]
SHADOW_DB = REPO_ROOT / ".data" / "test_F4_form_schema_shadow.db"


def _build_payload() -> dict:
    return {
        "sections": [
            {"section_code": "basic", "title": "基本信息", "order_index": 0},
            {"section_code": "extra", "title": "扩展信息", "order_index": 1, "collapsible": True},
        ],
        "fields": [
            {
                "field_code": "applicant_name",
                "section_code": "basic",
                "field_name": "申请人姓名",
                "field_type": "text",
                "required": True,
                "order_index": 0,
            },
            {
                "field_code": "apply_date",
                "section_code": "basic",
                "field_name": "申请日期",
                "field_type": "date",
                "required": True,
                "order_index": 1,
            },
            {
                "field_code": "categories",
                "section_code": "extra",
                "field_name": "分类",
                "field_type": "multiselect",
                "order_index": 2,
            },
            {
                "field_code": "remark",
                "section_code": "extra",
                "field_name": "备注",
                "field_type": "textarea",
                "order_index": 3,
            },
        ],
        "validators": [
            {
                "validator_code": "name_len",
                "applies_to_field_code": "applicant_name",
                "validator_kind": "length",
                "validator_payload_json": {"minLength": 2, "maxLength": 32},
                "error_message_template": "姓名长度需在 2-32 之间",
            },
            {
                "validator_code": "name_pattern",
                "applies_to_field_code": "applicant_name",
                "validator_kind": "regex",
                "validator_payload_json": {"pattern": "^[\\u4e00-\\u9fa5A-Za-z]+$"},
                "error_message_template": "姓名仅支持中英文",
            },
            {
                "validator_code": "categories_enum",
                "applies_to_field_code": "categories",
                "validator_kind": "enum",
                "validator_payload_json": {"values": ["A", "B", "C"]},
            },
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
    from zw_brain.domain.form_schema import FormSchemaRepo

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="sichuan_7fields_v1",
        title="四川 7 字段表单",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    assert record.status == "draft"
    assert record.version == 1
    assert record.committed_at is None
    assert record.tenant_id == "sd-default"


def test_promote_draft_to_preview(session):
    from zw_brain.domain.form_schema import FormSchemaRepo

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="promote_test",
        title="promote",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    promoted = repo.promote_to_preview(record.id)
    assert promoted.status == "preview"
    assert promoted.committed_at is None


def test_revert_preview_to_draft(session):
    from zw_brain.domain.form_schema import FormSchemaRepo

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="revert_test",
        title="revert",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)
    reverted = repo.revert_to_draft(record.id)
    assert reverted.status == "draft"


def test_commit_preview_to_live_bumps_version_and_sets_committed_at(session):
    from zw_brain.domain.form_schema import FormSchemaRepo

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="commit_test",
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
    from zw_brain.domain.form_schema import FormSchemaRepo, FormSchemaTransitionError

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="bad_draft_to_live",
        title="bad",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    with pytest.raises(FormSchemaTransitionError):
        repo.commit_to_live(record.id)


def test_invalid_transition_live_to_anything_raises(session):
    from zw_brain.domain.form_schema import FormSchemaRepo, FormSchemaTransitionError

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="bad_live_to_x",
        title="bad",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)
    repo.commit_to_live(record.id)
    with pytest.raises(FormSchemaTransitionError):
        repo.promote_to_preview(record.id)
    with pytest.raises(FormSchemaTransitionError):
        repo.revert_to_draft(record.id)
    with pytest.raises(FormSchemaTransitionError):
        repo.commit_to_live(record.id)


# ──────────────────────────────────────────────────────────────────────────
# payload 结构校验
# ──────────────────────────────────────────────────────────────────────────

def test_payload_validation_requires_non_empty_sections_and_fields(session):
    from zw_brain.domain.form_schema import FormSchemaPayloadError, FormSchemaRepo

    repo = FormSchemaRepo(session)
    bad_sections = _build_payload()
    bad_sections["sections"] = []
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="no_sections",
            title="bad",
            payload=bad_sections,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )
    bad_fields = _build_payload()
    bad_fields["fields"] = []
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="no_fields",
            title="bad",
            payload=bad_fields,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_field_section_code_must_reference_known_section(session):
    from zw_brain.domain.form_schema import FormSchemaPayloadError, FormSchemaRepo

    payload = _build_payload()
    payload["fields"].append(
        {
            "field_code": "ghost",
            "section_code": "ghost_section",
            "field_name": "ghost",
            "field_type": "text",
        }
    )
    repo = FormSchemaRepo(session)
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="bad_section_ref",
            title="bad",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_validator_applies_to_field_code_must_reference_known_field(session):
    from zw_brain.domain.form_schema import FormSchemaPayloadError, FormSchemaRepo

    payload = _build_payload()
    payload["validators"].append(
        {
            "validator_code": "ghost_v",
            "applies_to_field_code": "no_such_field",
            "validator_kind": "regex",
            "validator_payload_json": {"pattern": ".*"},
        }
    )
    repo = FormSchemaRepo(session)
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="bad_validator_ref",
            title="bad",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


def test_unsupported_field_type_or_validator_kind_raises(session):
    from zw_brain.domain.form_schema import FormSchemaPayloadError, FormSchemaRepo

    payload = _build_payload()
    payload["fields"][0]["field_type"] = "rich_text"  # unsupported
    repo = FormSchemaRepo(session)
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="bad_field_type",
            title="bad",
            payload=payload,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )

    payload2 = _build_payload()
    payload2["validators"][0]["validator_kind"] = "xss_scan"  # unsupported
    with pytest.raises(FormSchemaPayloadError):
        repo.create_draft(
            tenant_id="sd-default",
            form_code="bad_validator_kind",
            title="bad",
            payload=payload2,
            created_by="user:gov:ROLE_ORGAN_MANAGER:test",
        )


# ──────────────────────────────────────────────────────────────────────────
# Dispatch 端到端
# ──────────────────────────────────────────────────────────────────────────

def test_commit_via_skill_dispatch_returns_ok_and_audit_id(session):
    from zw_brain.command.brain import BrainService
    from zw_brain.domain.form_schema import FormSchemaRepo
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="dispatch_e2e",
        title="dispatch_e2e",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )
    repo.promote_to_preview(record.id)

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    try:
        brain = BrainService(state_store=ss)
        result = invoke_trusted(
                     brain,
                     "form_schema.commit",
                     {
                "tenant_id": "sd-default",
                "schema_id": record.id,
                "confirmed": True,
            },
                     role="ROLE_ORGAN_MANAGER",
                 )
    finally:
        audit_bus.clear_sink()

    assert result["ok"] is True
    assert result["skill_id"] == "form_schema.commit"
    assert result["audit_id"]
    payload = result["result"]
    assert payload["schema_id"] == record.id
    assert payload["version"] == 2
    assert payload["committed_at"] is not None


# ──────────────────────────────────────────────────────────────────────────
# JSON Schema 投影（draft-07 兼容）
# ──────────────────────────────────────────────────────────────────────────

def test_to_json_schema_emits_valid_draft07(session):
    from zw_brain.domain.form_schema import FormSchemaRepo

    repo = FormSchemaRepo(session)
    record = repo.create_draft(
        tenant_id="sd-default",
        form_code="json_schema_test",
        title="四川 7 字段表单",
        payload=_build_payload(),
        created_by="user:gov:ROLE_ORGAN_MANAGER:test",
    )

    schema = FormSchemaRepo.to_json_schema(record)
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["type"] == "object"
    assert schema["title"] == "四川 7 字段表单"
    assert "applicant_name" in schema["properties"]
    name_prop = schema["properties"]["applicant_name"]
    assert name_prop["type"] == "string"
    assert name_prop["minLength"] == 2
    assert name_prop["maxLength"] == 32
    assert "pattern" in name_prop
    assert schema["properties"]["apply_date"]["format"] == "date"
    assert schema["properties"]["categories"]["type"] == "array"
    assert schema["properties"]["categories"]["enum"] == ["A", "B", "C"]
    assert set(schema["required"]) == {"applicant_name", "apply_date"}


def test_manifest_registered_and_validates() -> None:
    from zw_brain.capability_registry.runtime import load_manifests

    manifests = load_manifests()
    assert "form_schema.commit" in manifests
    m = manifests["form_schema.commit"]
    assert m["config_change_class"] == "live"
    assert m["audit_class"] == "write-critical"
    assert m["human_confirmation_required"] is True
    assert m["product_scope"] == {"journey": "b1", "status": "live"}
