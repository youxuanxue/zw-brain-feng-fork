"""W3 R7 P5 工作收件箱 contract test.

Covers:
- catalog.entry.query 新增 source / lifecycle_status 过滤
- R7 工作流卡片仅 R7 可见（角色权限）
- 3 个 inbox 页面 + 2 个 detail 页面已注册 + 路由 wired
- ACTIONS: confirmFieldDecision / rejectFieldDecision / approveResourceReview
  / rejectResourceReview / dispatchDemand 都调用对应的 W1 skill
- 端到端：R6 反向编目 create → catalog.entry.query(source=reverse, lifecycle=draft)
  返回该草稿 → R7 confirm → 草稿进入 pending_review，再 query 不返回
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zw_brain.shared import audit as audit_bus
from zw_brain.shared.state_store import StateStore

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def svc(tmp_path: Path):
    os.environ["ZW_BRAIN_DB_PATH"] = str(tmp_path / "zw_brain_w3.db")
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    store = DatabaseStore()
    audit_bus.configure_sink(store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=store))


def test_catalog_entry_query_filter_by_source_and_lifecycle(svc) -> None:
    """Create one reverse draft and one non-reverse draft; query must
    return only the reverse one when both filters are applied."""
    # Reverse draft
    svc.invoke_skill("catalog.entry.reverse_draft.create", {
        "role": "r6", "confirmed": True,
        "catalog_code": "TC-W3-001", "title": "反向草稿 A",
        "schema_ref": "snap-A",
    })
    # Non-reverse draft (regular catalog draft)
    svc.invoke_skill("catalog.entry.create_draft", {
        "role": "r6", "confirmed": True,
        "catalog_code": "TC-W3-002", "title": "普通草稿 B",
        "summary_json": {"source": "manual"},
    })
    result = svc.invoke_skill("catalog.entry.query", {
        "role": "r7", "source": "reverse", "lifecycle_status": "draft",
    })
    codes = {item["catalog_code"] for item in result["items"]}
    assert "TC-W3-001" in codes
    assert "TC-W3-002" not in codes


def test_r7_confirm_drops_draft_from_pending_query(svc) -> None:
    """After R7 confirms, the draft should no longer appear under (reverse, draft)."""
    svc.invoke_skill("catalog.entry.reverse_draft.create", {
        "role": "r6", "confirmed": True,
        "catalog_code": "TC-W3-003", "title": "待裁决 C",
        "schema_ref": "snap-C",
    })
    before = svc.invoke_skill("catalog.entry.query", {
        "role": "r7", "source": "reverse", "lifecycle_status": "draft",
    })
    assert "TC-W3-003" in {item["catalog_code"] for item in before["items"]}

    svc.invoke_skill("catalog.entry.reverse_draft.confirm", {
        "role": "r7", "confirmed": True,
        "catalog_code": "TC-W3-003",
        "field_decisions": [],
        "comment": "字段口径与目录模板一致",
    })
    after = svc.invoke_skill("catalog.entry.query", {
        "role": "r7", "source": "reverse", "lifecycle_status": "draft",
    })
    assert "TC-W3-003" not in {item["catalog_code"] for item in after["items"]}

    pending = svc.invoke_skill("catalog.entry.query", {
        "role": "r7", "source": "reverse", "lifecycle_status": "pending_review",
    })
    assert "TC-W3-003" in {item["catalog_code"] for item in pending["items"]}


def test_r7_workflow_cards_visible_only_to_r7() -> None:
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    # Cards function references R7 role check
    assert "r7ProviderWorkflowCards" in pages_js
    assert "window.STATE.role !== 'r7'" in pages_js
    # Each of 3 inbox cards rendered
    assert "字段口径裁决（" in pages_js
    assert "资源挂接审核（" in pages_js
    assert "供需对接（" in pages_js


def test_r7_inbox_pages_and_routes_registered() -> None:
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")
    for page in (
        "providerInboxFieldDecision",
        "providerInboxFieldDecisionDetail",
        "providerInboxHookupReview",
        "providerInboxDemandMatch",
        "providerInboxDemandMatchDetail",
    ):
        assert f"PAGES.{page}" in pages_js, f"missing page renderer {page}"
        assert f"{page}: ['r7']" in pages_js, f"missing access map for {page}"
        assert f"{page}: 'p5'" in pages_js, f"missing shell key for {page}"
    for slug in ("field-decision", "hookup-review", "demand-match"):
        assert f"\\/inbox\\/{slug}" in app_js, f"missing route for {slug}"


def test_r7_inbox_actions_call_w1_skills() -> None:
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")
    # 字段口径裁决 → confirm/reject 通过 W1.1
    assert "confirmFieldDecision" in app_js
    assert "catalog.entry.reverse_draft.confirm" in app_js
    assert "rejectFieldDecision" in app_js
    assert "catalog.entry.reverse_draft.reject" in app_js
    # 挂接审核 → resource.asset.review
    assert "approveResourceReview" in app_js
    assert "rejectResourceReview" in app_js
    assert "resource.asset.review" in app_js
    # 供需对接 → W1.4 require.resource.dispatch
    assert "dispatchDemand" in app_js
    assert "require.resource.dispatch" in app_js


def test_r7_inbox_pre_fetch_routing_wired() -> None:
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")
    # P5 R7 视图预拉收件箱条数
    assert "RUNTIME_R7_FIELD_DRAFTS" in app_js
    assert "RUNTIME_R7_HOOKUP_PENDING" in app_js
    assert "RUNTIME_R7_DEMAND_PENDING" in app_js
    # field-decision/<code> detail 路由要调 reverse_draft.suggest
    assert "catalog.entry.reverse_draft.suggest" in app_js
    # demand-match/<code> detail 要调 require.resource.match
    assert "require.resource.match" in app_js
