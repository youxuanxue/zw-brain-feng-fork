"""B1.2 身份治理 Web 消费面：registry skill 必须有真实 UI 消费者。"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.no_db


def test_iam_governance_route_uses_real_page() -> None:
    router = (REPO / "zw-brain-web" / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    placeholder_component = "Page" + "Placeholder"
    assert "B12IamGovernance" in router
    assert "import B12IamGovernance from '@/pages/B12IamGovernance.vue'" in router
    assert "/integration-admin/iam-governance', component: B12IamGovernance" in router
    assert placeholder_component not in router
    assert "PLogin" in router


def test_iam_governance_page_wires_actor_governance_only() -> None:
    page = (REPO / "zw-brain-web" / "src" / "pages" / "B12IamGovernance.vue").read_text(encoding="utf-8")
    assert "useActorGovernance" in page
    assert "用户与角色" in page
    assert "谁能访问什么" in page
    assert "旧权限映射审核" not in page
    assert "usePolicyCandidates" not in page
    assert "ReferencePicker" in page
    assert "orgDisplay" in page
    assert "name || code" not in page
    assert "item.org_name || item.org_code" not in page


def test_frontend_org_display_does_not_fallback_to_codes() -> None:
    current_org = (REPO / "zw-brain-web" / "src" / "composables" / "useCurrentOrg.ts").read_text(encoding="utf-8")
    datasource = (REPO / "zw-brain-web" / "src" / "pages" / "P5DataSourceManage.vue").read_text(encoding="utf-8")
    catalog_resources = (REPO / "zw-brain-web" / "src" / "composables" / "useCatalogResources.ts").read_text(encoding="utf-8")
    catalog_review = (REPO / "zw-brain-web" / "src" / "pages" / "P5CatalogReviewInbox.vue").read_text(encoding="utf-8")
    catalog_manage = (REPO / "zw-brain-web" / "src" / "pages" / "P5CatalogManageList.vue").read_text(encoding="utf-8")
    iam_page = (REPO / "zw-brain-web" / "src" / "pages" / "B12IamGovernance.vue").read_text(encoding="utf-8")
    provider_projection = (REPO / "zw-brain-web" / "src" / "lib" / "providerProjection.ts").read_text(encoding="utf-8")
    reference_picker = (REPO / "zw-brain-web" / "src" / "components" / "ReferencePicker.vue").read_text(encoding="utf-8")
    reverse_payload = (REPO / "zw-brain-web" / "src" / "lib" / "reverseDraftPayload.ts").read_text(encoding="utf-8")
    user_language = (REPO / "zw-brain-web" / "src" / "lib" / "userLanguage.ts").read_text(encoding="utf-8")

    assert "_currentOrgName.value || '')" in current_org
    assert "_currentOrgName.value || _currentOrgCode.value" not in current_org
    assert "ReferencePicker" in datasource and "org_code: form.value.org_code" in datasource
    assert "org_name: form.value.org_name" not in datasource
    assert "provider: String(a.owner_org_name ?? '')" in catalog_resources
    assert "provider: String(a.owner_org_id" not in catalog_resources
    assert ':title="item.org_code"' not in iam_page
    assert ':title="b.org_code"' not in iam_page
    assert "rp-code" not in reference_picker
    assert "displayRecordCode" in user_language
    assert "displayRecordCode(String(summary.data_catalog_code" in catalog_review
    assert "{ label: '目录编号', key: 'code'" in catalog_manage
    assert "code: displayRecordCode(displayCode, '编号')" in provider_projection
    assert "code: displayRecordCode(it.catalog_code, '目录')" in provider_projection
    assert "owner_org_id: catalog.ownerOrgId || undefined" in reverse_payload
    assert "owner_org_id: catalog.owner || undefined" not in reverse_payload


def test_docker_deployment_doc_describes_bff_cookie_not_bearer_in_browser() -> None:
    doc = (REPO / "docs" / "deployment" / "docker-image-deployment.md").read_text(encoding="utf-8")
    assert "zw_brain_session" in doc
    assert "Authorization: Bearer <access_token>" not in doc
    assert "ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only" in doc
