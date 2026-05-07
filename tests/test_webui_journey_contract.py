from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP_JS = REPO / "zw-brain-web" / "js" / "app.js"
PAGES_JS = REPO / "zw-brain-web" / "js" / "pages.js"


def test_backflow_button_uses_backflow_skill() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    start = app_js.index("confirmBackflow(taskId)")
    block = app_js[start : app_js.index("triggerDeliveryRecovery", start)]
    assert "performWrite('backflow.confirm'" in block
    assert "performWrite('delivery.access.grant'" not in block


def test_request_flow_uses_active_request_not_fixture_id() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.requestFlow = function")
    block = pages_js[start : pages_js.index("PAGES.requestDetail", start)]
    assert "const request = activeRequest();" in block
    assert "REQ-2026-04-25-0011" not in block


def test_completed_request_action_uses_matching_delivery() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("function requestActionBar")
    action_bar = pages_js[start : pages_js.index("function businessNavLabel", start)]
    completed = action_bar[action_bar.index("if (item.status === 'completed')") : action_bar.index("if (item.status === 'rejected')")]
    assert "deliveryByRequestId(item.id)" in completed
    assert "DLV-2026-04-25-0011" not in completed


def test_backflow_button_requires_reconciled_receipt() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.deliveryTaskDetail = function")
    block = pages_js[start : pages_js.index("PAGES.provider", start)]
    assert "task.receiptStatus === 'reconciled'" in block
    assert "backflowKey !== 'confirmed'" in block


def test_status_tokens_have_display_labels() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    for token, label in {
        "open": "待核查",
        "provider_investigating": "提供方核查中",
        "escalated": "已升级",
        "resolved": "已解决",
        "ok": "成功",
    }.items():
        assert f"{token}: '{label}'" in pages_js
    assert "待回流确认" in pages_js
    assert "backflowStatusKey" in pages_js


def test_entity_lookup_does_not_silent_fallback_to_first_row() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "|| window.RUNTIME_REQUESTS[0]" not in pages_js
    assert "|| window.RUNTIME_APPROVALS[0]" not in pages_js
    assert "|| window.RUNTIME_DISCOVERY.resources[0]" not in pages_js
    assert "|| window.RUNTIME_DELIVERY_TASKS[0]" not in pages_js
    assert "|| window.RUNTIME_DISPUTES[0]" not in pages_js
    assert "|| window.RUNTIME_ZONES[0]" not in pages_js
    assert "|| window.RUNTIME_CAPABILITY_PACKAGES[0]" not in pages_js


def test_sync_route_refreshes_review_detail_same_as_request() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "route.startsWith('#/p3-request-flow/review/')" in app_js
    review_idx = app_js.index("p3-request-flow/review/")
    view_idx = app_js.index("'request.view'", review_idx)
    approval_idx = app_js.index("'approval.view'", review_idx)
    assert view_idx < approval_idx


def test_dispatch_enforces_page_access_map() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "window.ZW_PAGE_ACCESS" in app_js
    assert "renderAccessDeniedShell" in app_js
    assert "assertRouteAccessParity" in app_js


def test_role_switch_refetches_snapshot() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    start = app_js.index("switcher.addEventListener('change'")
    block = app_js[start : start + 900]
    assert "await refreshSnapshot()" in block


def test_pages_expose_access_map_for_app_router() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "window.ZW_PAGE_ACCESS" in pages_js
    assert "window.renderAccessDeniedShell" in pages_js
