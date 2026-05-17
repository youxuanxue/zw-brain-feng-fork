import json
import shutil
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
AUTH_JS = REPO / "zw-brain-web" / "js" / "auth.js"
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


def test_webui_iam_auth_contract_uses_session_storage_and_user_menu() -> None:
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    auth_js = AUTH_JS.read_text(encoding="utf-8")
    pages_js = PAGES_JS.read_text(encoding="utf-8")

    assert '<script src="/js/auth.js"></script>' in index_html
    assert 'id="zw-login-button"' in index_html
    assert 'id="user-menu"' in index_html
    assert '退出登录' in index_html
    assert '个人中心' in index_html
    assert 'window.sessionStorage.setItem(STORAGE_KEY' in auth_js
    assert 'window.localStorage' not in auth_js
    assert "readAuthConfig" in auth_js
    assert "development_iam_bypass_enabled" in auth_js
    assert "writeDevelopmentIamBypassSession" in auth_js
    assert "session.development_iam_bypass !== true" in auth_js
    assert "authConfig = await readAuthConfig()" in auth_js
    # Bypass identity (display name, role list) now flows from /auth/iaf/config — frontend reads
    # development_iam_bypass_user instead of hardcoding it; verifies the single source of truth.
    assert "development_iam_bypass_user" in auth_js
    assert "DEV_IAM_BYPASS_ROLES" not in auth_js
    assert "访客" not in auth_js
    assert "headers.set('Authorization', `Bearer ${session.access_token}`)" in auth_js
    assert "session.development_iam_bypass !== true" in auth_js
    assert "tokenSecondsLeft(session) <= 0" in auth_js
    assert "authConfig.development_iam_bypass_enabled === true" in auth_js
    assert 'setInterval' in auth_js and '5 * 60 * 1000' in auth_js
    assert 'REFRESH_THRESHOLD_SECONDS = 60' in auth_js
    assert 'safeDecodeJwtPayload' in auth_js
    assert 'await window.ZW_AUTH.bootstrapAuth()' in app_js
    assert 'window.ZW_AUTH.authFetch(`/api/snapshot' in app_js
    assert "{ test: /^#\\/profile$/, page: 'profile', nav: null }" in app_js
    assert 'PAGES.profile = function' in pages_js


def test_role_switch_refetches_snapshot() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    if "switcher.addEventListener('change'" not in app_js:
      assert "allowRoleSwitch" in app_js
      return
    start = app_js.index("switcher.addEventListener('change'")
    block = app_js[start : start + 900]
    assert "await refreshSnapshot()" in block


def test_snapshot_role_hydration_overrides_default_role() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    assert "currentRole = state.role || currentRole || 'r1';" in app_js
    assert "currentRole = currentRole || state.role || 'r1';" not in app_js


def test_provider_page_uses_three_step_task_flow_and_existing_actions() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    provider_start = pages_js.index("PAGES.provider = function")
    provider_block = pages_js[provider_start : pages_js.index("PAGES.complianceOps", provider_start)]
    assert "第一步：确认目录说明" in provider_block
    assert "第二步：确认资源可用性" in provider_block
    assert "第三步：值守预填与回流服务" in provider_block
    assert "window.ACTIONS.manageCatalogEntry" in provider_block
    assert "window.ACTIONS.manageResourceAsset" in provider_block
    assert "window.ACTIONS.publishProviderService" in provider_block
    assert "window.ACTIONS.suspendProviderService" in provider_block


def test_pages_expose_access_map_for_app_router() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "window.ZW_PAGE_ACCESS" in pages_js
    assert "window.renderAccessDeniedShell" in pages_js


def test_webui_routes_and_actions_use_shared_skill_policy_gateways() -> None:
    app_js = APP_JS.read_text(encoding="utf-8")
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    assert "const access = window.ZW_PAGE_ACCESS && window.ZW_PAGE_ACCESS[matched.page]" in app_js
    assert "renderAccessDeniedShell" in app_js
    assert "window.ZW_AUTH.authFetch(`/api/skills/${skillId}${encodeParams(payload)}`" in app_js
    assert "window.ZW_AUTH.authFetch(`/api/skills/${skillId}`" in app_js
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


def _prepare_real_legacy_offline_db(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, Path]:
    db_path = root / "real-customer.db"
    dumps_dir = REPO / "old" / "10示例数据"
    report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, reset_db=True, strict=True))
    assert report["status"] == "succeeded"
    offline_source = root / "legacy-source-offline"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.setenv("ZW_BRAIN_LEGACY_DUMPS_DIR", str(offline_source))
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    reset_service()
    return report, offline_source


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


def test_f3_r1_read_side_hits_real_medical_catalog_and_basic_element(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, offline_source = _prepare_imported_offline_db(root, monkeypatch)
        server, thread, base_url = _start_rest_server()
        try:
            status, discovery = _get(base_url, "data.search", query="医疗", page=1, role="r1")
            discovery = _assert_ok_dict(status, discovery)
            ids = {item["id"] for item in discovery["results"]}
            assert "307013370000308002000000/000049" in ids
            assert "basic-elem:0b26783950004ed882ec9309fae73310" in ids
            assert "停车场" not in discovery["summary"]["summary"]
            assert not offline_source.exists()

            status, detail = _get(base_url, "catalog.resource_view", resource_id="307013370000308002000000/000049", role="r1")
            detail = _assert_ok_dict(status, detail)
            assert detail["name"] == "区县域医疗机构院主要业务情况统计表"
            assert detail["provider"] == "省大数据局"
            assert detail["regionCode"] == "370000000000"
            assert detail["accessPolicy"]["shareWay"] == "0204"
            assert detail["sensitivePolicy"]["maskedOnRead"] is True
            assert detail["fieldBindingSummary"]["diagnosis"] == "ok"
            assert "出院者平均住院日" in detail["fields"]
            assert detail["fieldBindings"][0]["catalog_item_title"] == "出院者平均住院日"
            assert detail["fieldBindings"][0]["explain"]["source_column"] == "fdcdc442107540e5a0b10c9385b2775d"
            assert detail["fieldBindings"][0]["replay"]["steps"][2]["ref"] == "fdcdc442107540e5a0b10c9385b2775d"
            assert detail["resourceAssets"][0]["resource_code"] == "66dd29e00efe45729babe2c5bba118fa"
            assert detail["schemaSnapshots"]
            assert any(item["legacy_object_type"] == "data_catalog" for item in detail["legacyMappings"])
            assert detail["reuseGapHint"]["message"]

            status, resource_detail = _get(base_url, "catalog.resource_view", resource_id="66dd29e00efe45729babe2c5bba118fa", role="r1")
            resource_detail = _assert_ok_dict(status, resource_detail)
            assert resource_detail["repository"]["catalogCode"] == "307013370000308002000000/000049"
            assert resource_detail["fieldBindingSummary"]["diagnosis"] == "ok"

            status, metadata = _get(base_url, "metadata.catalog_item.query", catalog_code="307013370000308002000000/000049", role="r7")
            metadata = _assert_ok_dict(status, metadata)
            assert metadata["summary"]["diagnosis"] == "ok"
            assert metadata["catalogFields"][0]["title"] == "出院者平均住院日"
            assert metadata["items"][0]["catalog_item_title"] == "出院者平均住院日"

            status, basic = _get(base_url, "metadata.catalog_item.query", catalog_code="basic-elem:0b26783950004ed882ec9309fae73310", role="r7")
            basic = _assert_ok_dict(status, basic)
            assert basic["summary"]["diagnosis"] == "catalog_fields_only"
            assert basic["catalogFields"][0]["title"] == "人员姓名"

            combined = json.dumps([discovery, detail, resource_detail, metadata, basic], ensure_ascii=False)
            for marker in ["13800001111", "370102197001010011", "jdbc:", "10.0.", "192.168."]:
                assert marker not in combined
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()


def test_f3_webui_resource_detail_surfaces_business_evidence_copy() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.resourceDetail = function")
    block = pages_js[start : pages_js.index("PAGES.requestFlow", start)]
    assert "共享条件与安全策略" in pages_js
    assert "复用与缺口判断" in pages_js
    assert "资源与 schema 证据" in pages_js
    assert "旧平台回指证据" in pages_js
    assert "字段口径" in block
    assert "只申请本次确需字段" in block
    for forbidden in ["原型说明", "操作手册", "旧平台菜单"]:
        assert forbidden not in block


def test_f3_webui_review_detail_surfaces_r2_business_evidence_chain() -> None:
    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.reviewDetail = function")
    block = pages_js[start : pages_js.index("PAGES.deliveryExchange", start)]
    for expected in [
        "申请材料与复用范围",
        "准入证据链",
        "建议决策与授权边界",
        "旧平台回指与审计来源",
        "历史与重复线索",
        "质量投影",
        "通过复用、退回缩小范围、驳回重复或转口径确认",
    ]:
        assert expected in block
    for forbidden in ["技术调试", "debug", "原型说明", "操作手册", "旧平台菜单"]:
        assert forbidden not in block


@pytest.mark.legacy_migration_acceptance
def test_f3_r2_parking_read_side_surfaces_real_approval_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_id = "86013a7aaaf74724b7eb156272292e24"
    resource_id = "39a41e4b4e80439187e0f86218bae5d9"
    catalog_code = "370000308004000000/000001"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        report, offline_source = _prepare_real_legacy_offline_db(root, monkeypatch)
        assert report["stages"]["apply"]["dumps"]["dsp_catalog"]["tables"].get("data_apply_renewal", 0) == 0
        server, thread, base_url = _start_rest_server()
        try:
            status, request_view = _get(base_url, "request.view", request_id=apply_id, role="r2")
            request_view = _assert_ok_dict(status, request_view)
            assert request_view["id"] == apply_id
            assert request_view["resourceId"] == resource_id
            assert request_view["resourceName"] == "停车场信息_库表资源"
            assert request_view["status"] == "approved"
            assert request_view["applicationMaterials"]["catalogCode"] == catalog_code
            assert request_view["applicationMaterials"]["resourceId"] == resource_id
            assert request_view["applicationMaterials"]["minimal"] is True
            assert request_view["applicationMaterials"]["frequency"] == {"times": "1", "mostTimes": "1", "timeWindow": "每日（8:00-18:00)", "useDays": "1"}
            assert [item["title"] for item in request_view["requestedItems"]] == ["名称", "地址"]
            assert request_view["applicationMaterials"]["requestedItems"] == request_view["requestedItems"]
            assert request_view["reuseCandidate"]["catalogCode"] == catalog_code
            assert request_view["reuseCandidate"]["fieldBindingSummary"]["diagnosis"] == "ok"
            assert request_view["reuseCandidate"]["resourceStatus"] == "active"
            assert request_view["sensitivePolicy"]["fieldSensitiveLevels"] == ["1"]
            assert {item["catalog_item_title"] for item in request_view["fieldBindings"]} == {"名称", "地址"}
            assert {item["explain"]["source_column"] for item in request_view["fieldBindings"]} == {"name", "address"}
            assert request_view["historicalContext"]["duplicateConclusion"] == "无在途重复申请，可按复用授权边界继续审批。"
            assert request_view["historicalContext"]["relatedApplicationCount"] >= 1
            assert request_view["qualityEvidence"]["status"] == "ready"
            assert "字段绑定" in request_view["qualityEvidence"]["summary"]
            assert [(item["resource_code"], item["lifecycle_status"]) for item in request_view["resourceAssets"]] == [(resource_id, "suspended")]
            assert any(item["legacy_object_type"] == "data_apply" for item in request_view["legacyMappings"])
            assert any(item["legacy_object_type"] == "data_catalog" for item in request_view["sourceEvidence"]["legacyMappings"])
            assert not offline_source.exists()

            status, approval_view = _get(base_url, "approval.view", request_id=apply_id, role="r2")
            approval_view = _assert_ok_dict(status, approval_view)
            assert approval_view["requestId"] == apply_id
            assert approval_view["case"] == {"currentStatus": "approved", "currentStep": 4}
            assert [item["stepName"] for item in approval_view["steps"]] == ["申请", "受理", "审核", "备案"]
            assert [item["decision"] for item in approval_view["decisions"]] == ["approved", "approved", "approved", "approved"]
            assert approval_view["applicationMaterials"] == request_view["applicationMaterials"]
            assert approval_view["reuseCandidate"]["catalogCode"] == catalog_code
            assert approval_view["fieldEvidence"]["fieldBindingSummary"]["diagnosis"] == "ok"
            assert {item["lifecycle_status"] for item in approval_view["fieldEvidence"]["resourceAssets"]} == {"suspended"}
            assert approval_view["historicalContext"]["inFlightDuplicateCount"] == 0
            assert approval_view["qualityEvidence"]["source"] == "schema_mapping_projection"
            assert approval_view["grantEvidence"]["state"] == "granted"
            assert approval_view["grantEvidence"]["accessGrant"]["status"] == 0
            assert approval_view["grantEvidence"]["accessGrant"]["apply_status"] == 9
            assert approval_view["recommendedDecision"]["primary"] == "approve_reuse"
            assert "不伪造续期" in approval_view["recommendedDecision"]["renewalBoundary"]
            assert any(item["legacy_object_type"] == "data_apply_course" and item["canonical_type"] == "approval_decision" for item in approval_view["legacyMappings"])

            status, delivery_view = _get(base_url, "delivery.view", task_id=apply_id, role="r6")
            delivery_view = _assert_ok_dict(status, delivery_view)
            assert delivery_view["id"] == apply_id
            assert delivery_view["requestId"] == apply_id
            assert delivery_view["status"] == "granted"
            assert delivery_view["applicationMaterials"] == request_view["applicationMaterials"]
            assert delivery_view["accessGrantSnapshot"]["limit_day"] == 180
            assert delivery_view["authorizationBoundary"]["renewalSourceRows"] == 0
            assert delivery_view["schemaEvidence"]["fieldBindingSummary"]["diagnosis"] == "ok"
            assert delivery_view["schemaEvidence"]["qualityEvidence"]["status"] == "ready"
            assert delivery_view["backflow"]["status"] == "不适用"
            assert any(item["legacy_object_type"] == "data_apply_authrization" for item in delivery_view["legacyMappings"])

            status, audit = _get(base_url, "audit.list", role="r8")
            audit = _assert_ok_dict(status, audit)
            audit_json = json.dumps(audit, ensure_ascii=False)
            assert apply_id in audit_json
            assert "legacy.exchange.import" in audit_json
            assert "data_apply_course" in audit_json
            assert "data_apply_authrization" in audit_json

            combined = json.dumps([request_view, approval_view, delivery_view, audit], ensure_ascii=False)
            for marker in ["13800001111", "370102197001010011", "jdbc:", "10.0.", "192.168."]:
                assert marker not in combined
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()


@pytest.mark.legacy_migration_acceptance
def test_f4_r2_parking_review_decision_matrix_writes_policy_audit_and_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_id = "86013a7aaaf74724b7eb156272292e24"
    decisions = {
        "approve_reuse": ("granted", "granted", "grantBoundary", False),
        "approve_with_supplement": ("supplementing", "supplementing", "supplementBoundary", False),
        "return_for_fix": ("need-fix", "blocked", "nonGrantBoundary", True),
        "reject_duplicate": ("rejected", "blocked", "nonGrantBoundary", True),
        "route_to_provider_or_catalog_admin": ("pending-provider-confirmation", "blocked", "nonGrantBoundary", True),
    }
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        report, offline_source = _prepare_real_legacy_offline_db(root, monkeypatch)
        base_db = root / "real-customer.db"
        assert report["stages"]["apply"]["dumps"]["dsp_catalog"]["tables"].get("data_apply_renewal", 0) == 0
        assert not offline_source.exists()
        for decision, (expected_status, expected_delivery_state, boundary_key, non_grant) in decisions.items():
            case_db = root / f"{decision}.db"
            shutil.copyfile(base_db, case_db)
            monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(case_db))
            reset_service()
            server, thread, base_url = _start_rest_server()
            try:
                if decision == "approve_reuse":
                    status, denied = _post(
                        base_url,
                        "application.resource.review",
                        {"request_id": apply_id, "decision": decision, "role": "r1", "confirmed": True},
                    )
                    assert status == 403
                    assert isinstance(denied, dict)
                    assert denied["error"] == "access_denied"

                    status, unconfirmed = _post(
                        base_url,
                        "application.resource.review",
                        {"request_id": apply_id, "decision": decision, "role": "r2", "confirmed": False},
                    )
                    assert status == 409
                    assert isinstance(unconfirmed, dict)
                    assert unconfirmed["error"] == "confirmation_required"

                status, result = _post(
                    base_url,
                    "application.resource.review",
                    {"request_id": apply_id, "decision": decision, "role": "r2", "confirmed": True},
                )
                result = _assert_ok_dict(status, result)
                assert result["skill_id"] == "application.resource.review"
                assert result["result"]["decision"] == decision
                assert result["result"]["status"] == expected_status
                assert result["result"]["delivery_state"] == expected_delivery_state
                assert result["result"]["evidence"]["renewal_source_rows"] == 0

                status, approval_view = _get(base_url, "approval.view", request_id=apply_id, role="r2")
                approval_view = _assert_ok_dict(status, approval_view)
                assert approval_view["decisions"][-1]["decision"] == decision
                assert approval_view["decisions"][-1]["decisionReason"]
                assert approval_view["decisions"][-1]["evidence"]["decision"] == decision
                assert approval_view["reviewBoundary"]["decision"] == decision
                assert approval_view["reviewBoundary"]["actor"].endswith(":刘主任")
                assert approval_view["reviewBoundary"]["evidence"]["resource_id"] == "39a41e4b4e80439187e0f86218bae5d9"

                status, delivery_view = _get(base_url, "delivery.view", task_id=apply_id, role="r6")
                delivery_view = _assert_ok_dict(status, delivery_view)
                assert delivery_view["status"] == expected_delivery_state
                assert delivery_view["r2Review"]["decision"] == decision
                assert delivery_view[boundary_key]
                assert "不伪造续期" in delivery_view["renewalBoundary"]
                if non_grant:
                    assert delivery_view["nonGrantBoundary"]["no_new_grant"] is True
                    assert "grantBoundary" not in delivery_view or delivery_view["grantBoundary"] == {}
                    assert "supplementBoundary" not in delivery_view or delivery_view["supplementBoundary"] == {}
                else:
                    assert delivery_view[boundary_key]["field_scope"] == ["名称", "地址"]

                status, audit = _get(base_url, "audit.list", role="r8")
                audit = _assert_ok_dict(status, audit)
                audit_json = json.dumps(audit, ensure_ascii=False)
                assert "application.resource.review.after" in audit_json
                assert decision in audit_json
                assert apply_id in audit_json

                combined = json.dumps([result, approval_view, delivery_view, audit], ensure_ascii=False)
                for marker in ["13800001111", "370102197001010011", "jdbc:", "10.0.", "192.168."]:
                    assert marker not in combined
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                runtime._service = None
                reset_service()


@pytest.mark.legacy_migration_acceptance
def test_f5_r2_delivery_readback_replays_grant_supplement_non_grant_and_webui_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    apply_id = "86013a7aaaf74724b7eb156272292e24"
    decisions = {
        "approve_reuse": ("grantBoundary", "granted"),
        "approve_with_supplement": ("supplementBoundary", "supplementing"),
        "reject_duplicate": ("nonGrantBoundary", "blocked"),
    }
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _prepare_real_legacy_offline_db(root, monkeypatch)
        base_db = root / "real-customer.db"
        for decision, (boundary_key, expected_delivery_state) in decisions.items():
            case_db = root / f"f5-{decision}.db"
            shutil.copyfile(base_db, case_db)
            monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(case_db))
            reset_service()
            server, thread, base_url = _start_rest_server()
            try:
                status, result = _post(
                    base_url,
                    "application.resource.review",
                    {"request_id": apply_id, "decision": decision, "role": "r2", "confirmed": True},
                )
                result = _assert_ok_dict(status, result)
                assert result["result"]["delivery_state"] == expected_delivery_state

                status, request_view = _get(base_url, "request.view", request_id=apply_id, role="r2")
                request_view = _assert_ok_dict(status, request_view)
                assert [item["title"] for item in request_view["requestedItems"]] == ["名称", "地址"]
                assert request_view["sensitivePolicy"]["fieldSensitiveLevels"] == ["1"]
                assert request_view["applicationMaterials"]["frequency"] == {
                    "times": "1",
                    "mostTimes": "1",
                    "timeWindow": "每日（8:00-18:00)",
                    "useDays": "1",
                }

                status, approval_view = _get(base_url, "approval.view", request_id=apply_id, role="r2")
                approval_view = _assert_ok_dict(status, approval_view)
                assert approval_view["reviewBoundary"]["decision"] == decision
                assert approval_view["grantEvidence"]["accessGrant"]["limit_day"] == 180
                assert "不伪造续期" in approval_view["recommendedDecision"]["renewalBoundary"]

                status, delivery_view = _get(base_url, "delivery.view", task_id=apply_id, role="r6")
                delivery_view = _assert_ok_dict(status, delivery_view)
                assert delivery_view["status"] == expected_delivery_state
                assert delivery_view["accessGrantSnapshot"]["limit_day"] == 180
                assert delivery_view["accessGrantSnapshot"]["res_type"] == "table"
                assert delivery_view["authorizationBoundary"] == {
                    "limitDays": 180,
                    "resourceType": "table",
                    "applyStatus": 9,
                    "renewalSourceRows": 0,
                    "renewalPolicy": "真实 data_apply_renewal 无行；不伪造续期成功路径。",
                }
                assert "不伪造续期" in delivery_view["renewalBoundary"]
                boundary = delivery_view[boundary_key]
                if boundary_key == "nonGrantBoundary":
                    assert boundary == {"mode": decision, "no_new_grant": True}
                    assert delivery_view["grantBoundary"] == {}
                    assert delivery_view["supplementBoundary"] == {}
                else:
                    assert boundary["field_scope"] == ["名称", "地址"]
                    assert boundary["sensitive_levels"] == ["1"]
                    assert boundary["frequency"] == request_view["applicationMaterials"]["frequency"]
                    assert boundary["limit_day"] == 180
                    assert boundary["access_grant_snapshot"] == delivery_view["accessGrantSnapshot"]
                    if boundary_key == "supplementBoundary":
                        assert boundary["gap_fields"] == []

                combined = json.dumps([request_view, approval_view, delivery_view], ensure_ascii=False)
                for marker in ["13800001111", "370102197001010011", "jdbc:", "10.0.", "192.168."]:
                    assert marker not in combined
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                runtime._service = None
                reset_service()

    pages_js = PAGES_JS.read_text(encoding="utf-8")
    start = pages_js.index("PAGES.deliveryTaskDetail = function")
    block = pages_js[start : pages_js.index("PAGES.provider", start)]
    for expected in [
        "授权 / 续期边界回放",
        "字段范围",
        "敏感级别",
        "访问频次",
        "完成时限",
        "access_grant_snapshot",
        "续期边界",
        "非通过处理",
        "no_new_grant",
        "delivery-authorization-boundary",
    ]:
        assert expected in block
    for forbidden in ["原型说明", "操作手册", "旧平台菜单"]:
        assert forbidden not in block


def test_f4_r1_minimal_application_timeline_and_audit_on_imported_medical_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _, offline_source = _prepare_imported_offline_db(root, monkeypatch)
        server, thread, base_url = _start_rest_server()
        try:
            submit_payload = {
                "resource_id": "66dd29e00efe45729babe2c5bba118fa",
                "query": "区县域医疗机构院主要业务情况统计表",
                "purpose": "业务协同",
                "time_window": "2026年5月",
                "requested_items": ["出院者平均住院日"],
                "gap_fields": ["统计时间窗", "区县范围"],
                "delivery_expectation": "提供按区县汇总后的脱敏结果",
                "role": "r1",
                "confirmed": True,
            }
            status, submitted = _post(base_url, "application.resource.submit", submit_payload)
            submitted = _assert_ok_dict(status, submitted)
            request_id = submitted["result"]["request_id"]
            task_id = submitted["result"]["task_id"]
            assert request_id.startswith("REQ-")
            assert task_id == request_id.replace("REQ-", "DLV-", 1)
            assert not offline_source.exists()

            status, request_view = _get(base_url, "request.view", request_id=request_id, role="r1")
            request_view = _assert_ok_dict(status, request_view)
            assert request_view["resourceName"] == "区县域医疗机构院主要业务情况统计表"
            assert request_view["applicationMaterials"]["minimal"] is True
            assert [item["title"] for item in request_view["applicationMaterials"]["requestedItems"]] == ["出院者平均住院日"]
            assert [item["title"] for item in request_view["requestedItems"]] == ["出院者平均住院日"]
            assert set(request_view["gapFields"]) == {"统计时间窗", "区县范围"}
            assert request_view["applicationMaterials"]["gapFields"] == request_view["gapFields"]
            assert request_view["deliveryExpectation"] == "提供按区县汇总后的脱敏结果"
            assert request_view["applicationMaterials"]["deliveryExpectation"] == request_view["deliveryExpectation"]
            assert request_view["sourceEvidence"]["legacyMappings"]
            assert "整表重报" not in json.dumps(request_view, ensure_ascii=False)

            status, approval_view = _get(base_url, "approval.view", request_id=request_id, role="r2")
            approval_view = _assert_ok_dict(status, approval_view)
            assert [item["stage"] for item in approval_view["statusTimeline"]] == ["待受理", "审核中", "审批结论", "delivery_task"]
            assert approval_view["applicationMaterials"] == request_view["applicationMaterials"]

            status, delivery_view = _get(base_url, "delivery.view", task_id=task_id, role="r6")
            delivery_view = _assert_ok_dict(status, delivery_view)
            assert delivery_view["id"] == task_id
            assert delivery_view["requestId"] == request_id
            assert delivery_view["applicationMaterials"] == request_view["applicationMaterials"]
            assert delivery_view["applicationMaterials"]["gapFields"] == ["统计时间窗", "区县范围"]
            assert delivery_view["backflow"]["candidateFields"] == ["统计时间窗", "区县范围"]

            status, denied = _post(
                base_url,
                "application.resource.review",
                {"request_id": request_id, "decision": "approve", "role": "r1", "confirmed": True},
            )
            assert status == 403
            assert isinstance(denied, dict)
            assert denied["error"] == "access_denied"

            status, approved = _post(
                base_url,
                "application.resource.review",
                {"request_id": request_id, "decision": "approve_with_supplement", "role": "r2", "confirmed": True},
            )
            approved = _assert_ok_dict(status, approved)
            assert approved["result"]["status"] == "supplementing"

            status, request_after_review = _get(base_url, "request.view", request_id=request_id, role="r1")
            request_after_review = _assert_ok_dict(status, request_after_review)
            assert request_after_review["status"] == "supplementing"

            status, audit = _get(base_url, "audit.list", role="r8")
            audit = _assert_ok_dict(status, audit)
            audit_json = json.dumps(audit, ensure_ascii=False)
            assert "application.resource.submit.after" in audit_json
            assert "application.resource.review.after" in audit_json

            combined = json.dumps([submitted, request_view, approval_view, delivery_view, approved, request_after_review, audit], ensure_ascii=False)
            for marker in ["13800001111", "370102197001010011", "jdbc:", "10.0.", "192.168."]:
                assert marker not in combined
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()


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
            assert metadata["summary"] == {"total": 1, "active": 1, "missing": 0, "conflicted": 0, "inactive": 0, "diagnosis": "ok"}
            assert metadata["items"][0]["explain"]["source_column"] == "field-name"
            assert metadata["items"][0]["evidence_ref"]
            assert [step["step"] for step in metadata["items"][0]["replay"]["steps"]] == [
                "catalog_item",
                "resource_binding",
                "source_field",
                "evidence",
            ]

            status, request = _post(
                base_url,
                "application.resource.submit",
                {"resource_id": "res-market-activity", "query": "市场主体活跃度复用", "role": "r1", "confirmed": True},
            )
            request = _assert_ok_dict(status, request)
            request_id = request["result"]["request_id"]
            task_id = request_id.replace("REQ-", "DLV-", 1)

            status, reviewed = _post(
                base_url,
                "application.resource.review",
                {"request_id": request_id, "decision": "approve_with_supplement", "role": "r2", "confirmed": True},
            )
            reviewed = _assert_ok_dict(status, reviewed)
            assert reviewed["result"]["status"] == "supplementing"

            status, audit_after_review = _get(base_url, "audit.list", role="r8")
            audit_after_review = _assert_ok_dict(status, audit_after_review)
            audit_review_json = json.dumps(audit_after_review, ensure_ascii=False)
            assert "application.resource.review.before" in audit_review_json
            assert "application.resource.review.after" in audit_review_json
            assert request_id in audit_review_json

            status, supplemented = _post(base_url, "supplement.submit", {"request_id": request_id, "role": "r3", "confirmed": True})
            supplemented = _assert_ok_dict(status, supplemented)
            assert supplemented["result"]["status"] == "summary-pending"

            status, summarized = _post(base_url, "summary.confirm", {"request_id": request_id, "role": "r5", "confirmed": True})
            summarized = _assert_ok_dict(status, summarized)
            assert summarized["result"]["status"] == "completed"

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

            status, provider = _get(base_url, "provider.view", role="r7")
            provider = _assert_ok_dict(status, provider)
            assert provider["repository"]["packageCount"] >= 1
            assert provider["repository"]["deliveryReceiptCount"] >= 1

            status, zone = _get(base_url, "zone.view", zone_id="business", role="r7")
            zone = _assert_ok_dict(status, zone)
            assert zone["repository"]["resourceCatalogCode"] == provider["repository"]["resourceCatalogCode"]
            assert "resourceLifecycleStatus" in zone["repository"]
            assert zone["trust"]

            status, stats = _get(base_url, "ops.catalog.statistics.query", role="r8")
            stats = _assert_ok_dict(status, stats)
            assert stats["summary"]["projection_only"] is True
            assert stats["summary"]["evidence"]["source_ref"] == "canonical_projection"
            assert stats["summary"]["evidence"]["generated_at"]

            status, quality = _get(base_url, "ops.catalog.quality.query", role="r8")
            quality = _assert_ok_dict(status, quality)
            assert quality["total"] >= 1
            assert quality["items"][0]["projection_only"] is True
            assert quality["items"][0]["evidence"]["source_ref"]
            assert quality["items"][0]["evidence"]["generated_at"]

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
            assert field_mapping["items"][0]["evidence_ref"]
            assert [step["step"] for step in field_mapping["items"][0]["replay"]["steps"]] == [
                "catalog_item",
                "resource_binding",
                "source_field",
                "evidence",
            ]
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
                {"request_id": request_id, "decision": "approve_with_supplement", "role": "r2", "confirmed": True},
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
