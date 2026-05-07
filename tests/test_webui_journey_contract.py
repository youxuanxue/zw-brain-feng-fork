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
