"""B1.2 身份治理 Web 消费面：registry skill 必须有真实 UI 消费者。"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_iam_governance_route_uses_real_page() -> None:
    router = (REPO / "zw-brain-web" / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    placeholder_component = "Page" + "Placeholder"
    assert "B12IamGovernance" in router
    assert "import B12IamGovernance from '@/pages/B12IamGovernance.vue'" in router
    assert "/integration-admin/iam-governance', component: B12IamGovernance" in router
    assert placeholder_component not in router
    assert "PLogin" in router


def test_policy_candidates_composable_wires_registry_skills() -> None:
    composable = (REPO / "zw-brain-web" / "src" / "composables" / "usePolicyCandidates.ts").read_text(
        encoding="utf-8"
    )
    page = (REPO / "zw-brain-web" / "src" / "pages" / "B12IamGovernance.vue").read_text(encoding="utf-8")
    assert "governance.policy_candidate.list" in composable
    assert "governance.policy_candidate.review" in composable
    assert "authFetch" in composable
    assert "confirmed: true" in composable
    assert "usePolicyCandidates" in page
    assert "批准并写入策略" in page
    assert "canReview" in page
    assert ':disabled="!canReview"' in page


def test_docker_deployment_doc_describes_bff_cookie_not_bearer_in_browser() -> None:
    doc = (REPO / "docs" / "deployment" / "docker-image-deployment.md").read_text(encoding="utf-8")
    assert "zw_brain_session" in doc
    assert "Authorization: Bearer <access_token>" not in doc
    assert "ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only" in doc
