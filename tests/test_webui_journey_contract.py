import json
from http.server import HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlencode

import pytest

import zw_brain.command.runtime as runtime
from tests.test_legacy_migration_batch import _write_core_dumps
from tests.test_rest_runtime import request_json
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_acceptance_migration
from zw_brain.command.runtime import reset_service
from zw_brain.entry.rest.server import RestHandler

REPO = Path(__file__).resolve().parents[1]
APP_JS = REPO / "zw-brain-web" / "js" / "app.js"
PAGES_JS = REPO / "zw-brain-web" / "js" / "pages.js"
INDEX_HTML = REPO / "zw-brain-web" / "index.html"
PYPROJECT = REPO / "pyproject.toml"


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
    action_bar = pages_js[start : pages_js.index("function isBusinessNavCollapsed", start)]
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


def test_request_detail_refresh_does_not_request_approval_view() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    request_start = app_js.index("route.startsWith('#/p3-request-flow/request/')")
    request_block = app_js[request_start : app_js.index("route.startsWith('#/p3-request-flow/review/')", request_start)]
    assert "'request.view'" in request_block
    assert "'approval.view'" not in request_block


def test_sync_route_refreshes_review_detail_with_approval_view() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "route.startsWith('#/p3-request-flow/review/') && roleCan(['r2', 'r5'])" in app_js
    assert "reviewDetail: ['r2', 'r5']" in pages_js
    review_idx = app_js.index("p3-request-flow/review/")
    view_idx = app_js.index("'request.view'", review_idx)
    approval_idx = app_js.index("'approval.view'", review_idx)
    assert view_idx < approval_idx


def test_delivery_task_detail_uses_delivery_projection_without_request_projection() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.deliveryTaskDetail = function")
    block = pages_js[start : pages_js.index("PAGES.provider", start)]
    assert "entityNotFoundShell('p4', '关联共享申请'" not in block
    assert "关联申请仅作可选补充" in block
    assert "const requestCompleted = request ? request.status === 'completed' : task.status === 'completed' || task.summaryConfirmed === true;" in block


def test_review_detail_guards_non_list_approval_fields() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.reviewDetail = function")
    block = pages_js[start : pages_js.index("PAGES.deliveryExchange", start)]
    assert "function asList" in pages_js
    assert "const reasonItems = asList(approval.reason);" in block
    assert "const riskItems = asList(approval.risk);" in block
    assert "const exceptionItems = asList(approval.exceptionItems);" in block
    assert "approval.reason.map" not in block
    assert "approval.risk.map" not in block
    assert "approval.exceptionItems.map" not in block


def test_p7_publish_projection_action_is_r7_only() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    action_start = app_js.index("publishZoneTopicProjection(zoneId)")
    action_block = app_js[action_start : app_js.index("reconcileDeliveryReceipt", action_start)]
    zone_start = pages_js.index("PAGES.zoneDetail = function")
    zone_block = pages_js[zone_start : pages_js.index("PAGES.integrationAdmin", zone_start)]
    assert "currentRole !== 'r7'" in action_block
    assert "return;" in action_block
    assert "performWrite('zone.publish_topic_projection'" in action_block
    assert "window.STATE.role === 'r7'" in zone_block
    assert "正式投影发布由目录管理员处理" in zone_block


def test_current_parking_mainline_copy_does_not_mix_legal_entity_template() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "停车场信息" in pages_js
    assert "停车场信息共享目录" in pages_js
    assert "法人模板" not in pages_js
    assert "法人基础信息" not in pages_js


def test_dispatch_enforces_page_access_map() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "window.ZW_PAGE_ACCESS" in app_js
    assert "renderAccessDeniedShell" in app_js
    assert "assertRouteAccessParity" in app_js


def test_role_switch_refetches_snapshot() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    if "switcher.addEventListener('change'" not in app_js:
      assert "allowRoleSwitch" in app_js
      return
    start = app_js.index("switcher.addEventListener('change'")
    block = app_js[start : start + 900]
    assert "await refreshSnapshot()" in block


def test_pages_expose_access_map_for_app_router() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "window.ZW_PAGE_ACCESS" in pages_js
    assert "window.renderAccessDeniedShell" in pages_js


def test_webui_routes_and_actions_use_shared_skill_policy_gateways() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "const access = window.ZW_PAGE_ACCESS && window.ZW_PAGE_ACCESS[matched.page]" in app_js
    assert "renderAccessDeniedShell" in app_js
    assert "fetch(`/api/skills/${skillId}${encodeParams(payload)}`" in app_js
    assert "fetch(`/api/skills/${skillId}`" in app_js
    assert "Object.assign({ role: currentRole, confirmed: true }, payload)" in app_js
    assert "window.ZW_PAGE_ACCESS" in pages_js
    assert "integrationAdmin: ['r7']" in pages_js
    assert "packageDetail: ['r7']" in pages_js


def _prepare_imported_offline_db(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    dumps_dir = root / "dumps"
    db_path = root / "customer.db"
    _write_core_dumps(dumps_dir)
    report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, strict=True))
    assert report["status"] == "succeeded"
    for entry in dumps_dir.iterdir():
        entry.unlink()
    dumps_dir.rmdir()
    offline_source = root / "legacy-source-offline"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.setenv("ZW_BRAIN_LEGACY_DUMPS_DIR", str(offline_source))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    reset_service()
    return db_path, offline_source


def _start_rest_server() -> tuple[HTTPServer, Thread, str]:
    server = HTTPServer(("127.0.0.1", 0), RestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _get(base_url: str, skill_id: str, **params: object) -> tuple[int, dict | str]:
    return request_json("GET", f"{base_url}/api/skills/{skill_id}?{urlencode(params)}")


def _post(base_url: str, skill_id: str, payload: dict) -> tuple[int, dict | str]:
    return request_json("POST", f"{base_url}/api/skills/{skill_id}", payload)


def _assert_ok_dict(status: int, body: dict | str) -> dict:
    assert status == 200, body
    assert isinstance(body, dict)
    return body


def test_f4_http_asset_smoke_records_browser_e2e_unavailable_reason() -> None:
    pyproject = PYPROJECT.read_text(encoding="utf-8").lower()
    repo_files = [path.name.lower() for pattern in ("**/*playwright*", "**/*selenium*") for path in REPO.glob(pattern)]
    assert "playwright" not in pyproject
    assert "selenium" not in pyproject
    assert repo_files == []


def test_f4_webui_copy_is_customer_journey_not_legacy_menu_or_chat_shell() -> None:
    combined = "\n".join(
        [
            INDEX_HTML.read_text(encoding="utf-8"),
            APP_JS.read_text(encoding="utf-8"),
            PAGES_JS.read_text(encoding="utf-8"),
        ]
    )
    assert "政务数据大脑" in combined
    assert "数据资源发现" in combined
    assert "共享申请与审批" in combined
    assert "交付交换与回流" in combined
    assert "合规运营与减负" in combined
    assert "审计回放" in combined
    for forbidden in ["旧平台菜单", "旧 BSP 菜单后台", "菜单后台", "原型说明", "操作手册", "裸对话框", "聊天框"]:
        assert forbidden not in combined
    assert "<textarea" not in combined
    assert "chat-input" not in combined


def test_f5_independent_delivery_acceptance_package(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, offline_source = _prepare_imported_offline_db(root, monkeypatch)
        server, thread, base_url = _start_rest_server()
        try:
            status, discovery = _get(base_url, "data.search", query="人口", page=1, role="r1")
            discovery = _assert_ok_dict(status, discovery)
            assert any(item["id"] == "BASE-POP-001" for item in discovery["results"])
            assert not offline_source.exists()

            status, detail = _get(base_url, "catalog.resource_view", resource_id="BASE-POP-001", role="r1")
            detail = _assert_ok_dict(status, detail)
            assert detail["fieldBindingSummary"]["diagnosis"] == "ok"
            assert detail["fieldBindings"][0]["replay"]["steps"][2]["ref"] == "field-name"

            status, metadata = _get(base_url, "metadata.catalog_item.query", catalog_code="BASE-POP-001", role="r7")
            metadata = _assert_ok_dict(status, metadata)
            assert metadata["summary"]["diagnosis"] == "ok"
            assert metadata["items"][0]["explain"]["source_column"] == "field-name"

            status, request = _post(
                base_url,
                "application.resource.submit",
                {"resource_id": "res-market-activity", "query": "市场主体活跃度复用", "role": "r1", "confirmed": True},
            )
            request = _assert_ok_dict(status, request)
            request_id = request["result"]["request_id"]
            task_id = request_id.replace("REQ-", "DLV-", 1)
            for skill_id, payload, expected in [
                ("application.resource.review", {"request_id": request_id, "decision": "approve", "role": "r2", "confirmed": True}, "supplementing"),
                ("supplement.submit", {"request_id": request_id, "role": "r3", "confirmed": True}, "summary-pending"),
                ("summary.confirm", {"request_id": request_id, "role": "r5", "confirmed": True}, "completed"),
            ]:
                status, body = _post(base_url, skill_id, payload)
                body = _assert_ok_dict(status, body)
                assert body["result"]["status"] == expected

            status, receipt = _post(base_url, "delivery.reconcile_receipt", {"task_id": task_id, "role": "r6", "confirmed": True})
            receipt = _assert_ok_dict(status, receipt)
            assert receipt["result"]["receipt_status"] == "reconciled"
            status, backflow = _post(base_url, "backflow.confirm", {"task_id": task_id, "role": "r6", "confirmed": True})
            backflow = _assert_ok_dict(status, backflow)
            assert backflow["result"]["status"] == "completed"

            status, adapter = _post(
                base_url,
                "adapter.national.delivery.receipt.sync",
                {
                    "adapter_slug": "national-platform",
                    "operation": "delivery_receipt_sync",
                    "direction": "outbound",
                    "local_aggregate_type": "delivery_task",
                    "local_aggregate_id": task_id,
                    "external_object_id": "np-failed-receipt-1",
                    "status": "failed",
                    "failure_count": 1,
                    "error_summary": "上级平台回执失败",
                    "role": "r8",
                    "confirmed": True,
                },
            )
            adapter = _assert_ok_dict(status, adapter)
            assert adapter["result"]["run"]["status"] == "failed"
            assert adapter["result"]["mapping"]["status"] == "mapped"

            status, mappings = _get(base_url, "adapter.external.mapping.query", local_aggregate_id=task_id, role="r8")
            mappings = _assert_ok_dict(status, mappings)
            assert any(item["external_object_id"] == "np-failed-receipt-1" for item in mappings["items"])

            status, stats = _get(base_url, "ops.catalog.statistics.query", role="r8")
            stats = _assert_ok_dict(status, stats)
            assert stats["summary"]["projection_only"] is True
            assert stats["summary"]["evidence"]["source_ref"] == "canonical_projection"

            status, audit = _get(base_url, "audit.list", role="r8")
            audit = _assert_ok_dict(status, audit)
            audit_json = json.dumps(audit, ensure_ascii=False)
            for marker in [
                "application.resource.submit.after",
                "application.resource.review.after",
                "delivery.reconcile_receipt.after",
                "backflow.confirm.after",
                "adapter.national.delivery.receipt.sync.after",
            ]:
                assert marker in audit_json
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()


def test_f4_customer_journey_http_asset_smoke_on_imported_db_with_legacy_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, offline_source = _prepare_imported_offline_db(root, monkeypatch)
        server, thread, base_url = _start_rest_server()
        try:
            status, html = request_json("GET", f"{base_url}/index.html")
            assert status == 200
            assert isinstance(html, str)
            assert "政务数据大脑" in html
            assert "/js/pages.js" in html
            assert "/js/app.js" in html

            for asset_path, expected in [("/js/app.js", "application.resource.submit"), ("/js/pages.js", "数据资源发现")]:
                status, asset = request_json("GET", f"{base_url}{asset_path}")
                assert status == 200
                assert isinstance(asset, str)
                assert expected in asset

            status, snapshot_r1 = request_json("GET", f"{base_url}/api/snapshot?role=r1")
            snapshot_r1 = _assert_ok_dict(status, snapshot_r1)
            assert snapshot_r1["state"]["role"] == "r1"
            assert not offline_source.exists()

            status, discovery = _get(base_url, "data.search", query="人口", page=1, role="r1")
            discovery = _assert_ok_dict(status, discovery)
            assert any(item["id"] == "BASE-POP-001" for item in discovery["results"])
            status, catalog_detail = _get(base_url, "catalog.resource_view", resource_id="BASE-POP-001", role="r1")
            catalog_detail = _assert_ok_dict(status, catalog_detail)
            assert catalog_detail["id"] == "BASE-POP-001"
            assert catalog_detail["name"] == "人口基本信息"
            assert catalog_detail["fieldBindingSummary"]["diagnosis"] == "ok"
            assert catalog_detail["fieldBindings"][0]["explain"]["source_column"] == "field-name"

            status, field_mapping = _get(base_url, "metadata.catalog_item.query", catalog_code="BASE-POP-001", role="r7")
            field_mapping = _assert_ok_dict(status, field_mapping)
            assert field_mapping["summary"] == {"total": 1, "active": 1, "missing": 0, "conflicted": 0, "inactive": 0, "diagnosis": "ok"}
            assert field_mapping["items"][0]["mapping_code"] == "map-1"
            assert field_mapping["items"][0]["replay"]["steps"][2]["ref"] == "field-name"

            status, denied = _post(
                base_url,
                "application.resource.review",
                {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "r1", "confirmed": True},
            )
            assert status == 403
            assert isinstance(denied, dict)
            assert denied["error"] == "access_denied"

            status, created = _post(
                base_url,
                "application.resource.submit",
                {"resource_id": "res-market-activity", "query": "市场主体活跃度复用", "role": "r1", "confirmed": True},
            )
            created = _assert_ok_dict(status, created)
            request_id = created["result"]["request_id"]
            task_id = request_id.replace("REQ-", "DLV-", 1)

            status, request_view = _get(base_url, "request.view", request_id=request_id, role="r1")
            request_view = _assert_ok_dict(status, request_view)
            assert request_view["status"] == "pending"
            assert request_view["auditId"].startswith("AE-")

            status, approved = _post(
                base_url,
                "application.resource.review",
                {"request_id": request_id, "decision": "approve", "role": "r2", "confirmed": True},
            )
            approved = _assert_ok_dict(status, approved)
            assert approved["result"]["status"] == "supplementing"

            status, supplemented = _post(base_url, "supplement.submit", {"request_id": request_id, "role": "r3", "confirmed": True})
            supplemented = _assert_ok_dict(status, supplemented)
            assert supplemented["result"]["status"] == "summary-pending"

            status, summarized = _post(base_url, "summary.confirm", {"request_id": request_id, "role": "r5", "confirmed": True})
            summarized = _assert_ok_dict(status, summarized)
            assert summarized["result"]["status"] == "completed"

            status, delivery_before = _get(base_url, "delivery.view", task_id=task_id, role="r6")
            delivery_before = _assert_ok_dict(status, delivery_before)
            assert delivery_before["requestId"] == request_id
            assert delivery_before["status"] == "reconciling"

            status, receipt = _post(base_url, "delivery.reconcile_receipt", {"task_id": task_id, "role": "r6", "confirmed": True})
            receipt = _assert_ok_dict(status, receipt)
            assert receipt["result"]["receipt_status"] == "reconciled"

            status, backflow = _post(base_url, "backflow.confirm", {"task_id": task_id, "role": "r6", "confirmed": True})
            backflow = _assert_ok_dict(status, backflow)
            assert backflow["result"]["status"] == "completed"

            status, delivery_after = _get(base_url, "delivery.view", task_id=task_id, role="r6")
            delivery_after = _assert_ok_dict(status, delivery_after)
            assert delivery_after["backflow"]["status"] == "已确认"
            assert delivery_after["receiptStatus"] == "reconciled"

            status, objection = _post(
                base_url,
                "objection.case.create",
                {
                    "target_type": "delivery",
                    "target_id": task_id,
                    "related_application_id": request_id,
                    "title": "交付回执口径异议",
                    "basis_text": "回执字段需补充来源说明",
                    "expected_result": "补充证据后关闭异议",
                    "role": "r1",
                    "confirmed": True,
                },
            )
            objection = _assert_ok_dict(status, objection)
            objection_id = objection["result"]["id"]
            assert objection["result"]["status"] == "draft"

            for skill_id, payload, expected_status in [
                ("objection.case.submit", {"objection_id": objection_id, "role": "r1", "confirmed": True}, "submitted"),
                ("objection.case.accept", {"objection_id": objection_id, "role": "r8", "confirmed": True}, "accepted"),
                (
                    "objection.case.assign",
                    {"objection_id": objection_id, "role": "r8", "confirmed": True, "target_status": "provider_investigating"},
                    "provider_investigating",
                ),
                (
                    "objection.case.review",
                    {"objection_id": objection_id, "role": "r8", "confirmed": True, "decision": "resolve", "resolved_summary": "回执证据已补齐"},
                    "resolved",
                ),
            ]:
                status, body = _post(base_url, skill_id, payload)
                body = _assert_ok_dict(status, body)
                assert body["result"]["status"] == expected_status

            status, objection_cases = _get(base_url, "objection.case.query", role="r8")
            objection_cases = _assert_ok_dict(status, objection_cases)
            assert any(item["id"] == objection_id and item["status"] == "resolved" for item in objection_cases["items"])
            status, objection_process = _get(base_url, "objection.process.query", objection_id=objection_id, role="r8")
            objection_process = _assert_ok_dict(status, objection_process)
            assert len(objection_process["items"]) >= 5

            status, compliance = _get(base_url, "governance.dispute_list", role="r8")
            compliance = _assert_ok_dict(status, compliance)
            assert compliance["items"]
            dispute_id = compliance["items"][0]["id"]
            status, dispute = _get(base_url, "governance.dispute_view", dispute_id=dispute_id, role="r8")
            dispute = _assert_ok_dict(status, dispute)
            assert dispute["id"] == dispute_id
            status, replay = _get(base_url, "audit.replay_evidence_chain", dispute_id=dispute_id, role="r8")
            replay = _assert_ok_dict(status, replay)
            assert replay["evidenceChain"]

            status, audit = _get(base_url, "audit.list", role="r8")
            audit = _assert_ok_dict(status, audit)
            audit_json = json.dumps(audit, ensure_ascii=False)
            for marker in [
                request_id,
                "application.resource.submit.after",
                "application.resource.review.after",
                "supplement.submit.after",
                "summary.confirm.after",
                "delivery.reconcile_receipt.after",
                "backflow.confirm.after",
                "objection.case.create.after",
                "objection.case.review.after",
            ]:
                assert marker in audit_json
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()
