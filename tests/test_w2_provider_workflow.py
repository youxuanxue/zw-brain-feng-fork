"""W2 提供方部门 P5 工作流卡片 contract test.

Covers:
- catalog.entry.reverse_draft.suggest skill manifest + dispatch + role grant
- 三档预填 helper (reverse_draft_suggest.build_field_suggestions / build_title_suggestion)
- WebUI: P5 has 4 workflow cards (提供方部门 only) + 3 wizard subpages registered
- WebUI: actions wire up to skills via documented chain
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zw_brain.command.reverse_draft_suggest import (
    build_field_suggestions,
    build_title_suggestion,
)
from zw_brain.domain.policy import PERMISSION_ROLES
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.state_store import StateStore
from zw_brain.skill_registration.runtime import get_manifest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def svc(tmp_path: Path):
    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp_path / "zw_brain_w2.db")
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    store = DatabaseStore()
    audit_bus.configure_sink(store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=store))


def test_suggest_skill_registered_with_correct_audit_class() -> None:
    manifest = get_manifest("catalog.entry.reverse_draft.suggest")
    assert manifest["audit_class"] == "read-trace"
    assert manifest["side_effects"] == []
    for surface in ("webui", "api", "cli", "mcp", "a2a"):
        assert surface in manifest["compatibility"]
    allowed = PERMISSION_ROLES.get("catalog.entry.reverse_draft.suggest.execute") or set()
    assert "ROLE_ORGAN_MANAGER" in allowed and "ROLE_BUSIAUDIT" in allowed


def test_field_suggestions_three_tier_coverage_against_real_schema() -> None:
    """Tier 1 (comment) > Tier 2 (PII pattern) > Tier 3 (LLM stub fallback)."""
    schema = {
        "table_name": "park_lot_info",
        "columns": [
            # Tier 1: column with Chinese comment
            {"column_name": "park_id", "comment": "停车场编号", "data_type": "varchar"},
            # Tier 1: data standard Chinese name takes precedence over comment
            {"column_name": "license_no", "meta_standard_cn": "证照编号", "comment": "license number"},
            # Tier 2: PII pattern hits mobile_phone → "手机号" + sensitive 3
            {"column_name": "mobile_phone", "data_type": "varchar"},
            # Tier 2: id_card_no → "身份证号" + sensitive 4
            {"column_name": "id_card_no", "data_type": "varchar"},
            # Tier 2: addr → "地址"
            {"column_name": "home_addr", "data_type": "varchar"},
            # Tier 3: no comment, no PII match → llm-stub placeholder
            {"column_name": "park_capacity_total", "data_type": "int"},
        ],
    }
    suggestions, coverage = build_field_suggestions(schema)
    assert coverage["total"] == 6
    by_en = {s["field_en"]: s for s in suggestions}
    assert by_en["park_id"]["confidence"] == "green"
    assert by_en["park_id"]["field_cn"] == "停车场编号"
    assert by_en["license_no"]["confidence"] == "green"
    assert by_en["license_no"]["source"] == "data-standard"
    assert by_en["license_no"]["field_cn"] == "证照编号"
    assert by_en["mobile_phone"]["confidence"] == "yellow"
    assert by_en["mobile_phone"]["field_cn"] == "手机号"
    assert by_en["mobile_phone"]["sensitive_level"] == "3"
    assert by_en["id_card_no"]["sensitive_level"] == "4"
    assert by_en["home_addr"]["confidence"] == "yellow"
    assert by_en["park_capacity_total"]["confidence"] == "orange"
    assert "字段_" in by_en["park_capacity_total"]["field_cn"]
    assert coverage["green"] == 2
    assert coverage["yellow"] == 3
    assert coverage["orange"] == 1


def test_field_suggestions_handle_fields_key() -> None:
    """Some adapters use 'fields' instead of 'columns'."""
    schema = {"fields": [{"name": "user_id", "comment": "用户编号"}]}
    suggestions, _ = build_field_suggestions(schema)
    assert len(suggestions) == 1
    assert suggestions[0]["field_cn"] == "用户编号"


def test_field_suggestions_empty_input() -> None:
    suggestions, coverage = build_field_suggestions(None)
    assert suggestions == []
    assert coverage["total"] == 0


def test_title_suggestion_prefers_comment_over_table_name() -> None:
    s = build_title_suggestion({"table_name": "park_lot_info", "table_comment": "停车场信息"})
    assert s["title"] == "停车场信息"
    assert s["confidence"] == "green"
    s2 = build_title_suggestion({"table_name": "park_lot_info"})
    assert s2["confidence"] == "yellow"
    assert "park" in s2["title"].lower()


def test_suggest_skill_returns_envelope_for_missing_schema(svc) -> None:
    result = svc.invoke_skill(
        "catalog.entry.reverse_draft.suggest",
        {"role": "ROLE_ORGAN_MANAGER", "schema_ref": "snap-nonexistent"},
    )
    assert result["found"] is False
    assert result["fields"] == []
    assert result["coverage"]["total"] == 0


def test_suggest_skill_returns_three_tier_for_real_snapshot(svc) -> None:
    from zw_brain.domain.models import ResourceSchemaSnapshotRecord
    from zw_brain.shared.db import create_session_factory

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        session.add(
            ResourceSchemaSnapshotRecord(
                tenant_id="sd-default",
                snapshot_ref="snap-w2-001",
                resource_code="resource-停车场",
                schema_hash="h1",
                schema_json={
                    "table_name": "park_lot_info",
                    "columns": [
                        {"column_name": "park_id", "comment": "停车场编号"},
                        {"column_name": "mobile_phone"},
                        {"column_name": "capacity"},
                    ],
                },
            )
        )
        session.commit()

    result = svc.invoke_skill(
        "catalog.entry.reverse_draft.suggest",
        {"role": "ROLE_ORGAN_MANAGER", "schema_ref": "snap-w2-001"},
    )
    assert result["found"] is True
    assert result["coverage"]["total"] == 3
    assert result["title_suggestion"]["title"]


def test_webui_p5_workflow_cards_and_wizards_wired() -> None:
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")

    # 1. Workflow cards function visible to ROLE_ORGAN_MANAGER only
    assert "r6ProviderWorkflowCards" in pages_js
    assert "反向编目（提供方部门 → 业务运营员）" in pages_js
    assert "API 服务化交付（提供方部门 → 业务运营员/审批人）" in pages_js
    assert "自动检测规则维护（提供方部门）" in pages_js

    # 2. Three wizard pages registered
    assert "PAGES.providerWizardReverseCatalog" in pages_js
    assert "PAGES.providerWizardApiService" in pages_js
    assert "PAGES.providerWizardQualityRule" in pages_js
    for key in (
        "providerWizardReverseCatalog",
        "providerWizardApiService",
        "providerWizardQualityRule",
    ):
        assert f"{key}: ['ROLE_ORGAN_MANAGER']" in pages_js, f"missing access for {key}"
        assert f"{key}: 'p5'" in pages_js, f"missing shell key for {key}"

    # 3. Routes — regex form in JS uses backslash-escaped slashes
    for slug in ("reverse-catalog", "api-service", "quality-rule"):
        assert f"\\/wizard\\/{slug}" in app_js, f"missing route for {slug}"

    # 4. ACTIONS for reverse-catalog wizard chain
    assert "loadReverseCatalogCandidates" in app_js
    assert "pickReverseCatalogSource" in app_js
    assert "submitReverseCatalogDraft" in app_js
    # 5. ACTIONS for API service wizard call the three-skill chain
    assert "resource.api.register" in app_js
    assert "resource.api.policy.update" in app_js
    assert "resource.api.submit_review" in app_js
    # 6. ACTIONS for quality rule wizard call the three new skills
    assert "submitQualityRule" in app_js
    assert "runQualityTask" in app_js
    assert "replayQualityTask" in app_js
