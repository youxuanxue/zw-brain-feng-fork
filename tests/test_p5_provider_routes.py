"""P5 提供方子路由 — 组件接线与占位路由回归."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTER = REPO_ROOT / "zw-brain-web" / "src" / "router" / "index.ts"

pytestmark = pytest.mark.no_db

P5_LIVE_ROUTES: tuple[tuple[str, str], ...] = (
    ("/provider/inbox/field-decision", "P5FieldDecisionInbox"),
    ("/provider/inbox/hookup-review", "P5HookupReviewInbox"),
    ("/provider/inbox/demand-match", "P5DemandMatchInbox"),
    ("/provider/inbox/demand-match/:id", "P5DemandMatchDetail"),
    ("/provider/inbox/objection", "P5ObjectionInbox"),
    ("/provider/inbox/objection/:id", "P5ObjectionDetail"),
    ("/provider/wizard/reverse-catalog", "P5ReverseCatalogWizard"),
    ("/provider/wizard/api-service", "P5ApiServiceWizard"),
)


def test_p5_subroutes_use_live_components_not_placeholder() -> None:
    src = ROUTER.read_text(encoding="utf-8")
    placeholder_component = "Page" + "Placeholder"
    assert placeholder_component not in src
    for path, component in P5_LIVE_ROUTES:
        needle = f"path: '{path}', component: {component}"
        assert needle in src, f"missing live route wiring: {needle}"


def test_f6_p5_smoke_script_exists_and_executable() -> None:
    import os

    smoke = REPO_ROOT / "tests" / "e2e" / "wave1_j2_provider_p5_smoke.py"
    assert smoke.exists()
    assert os.access(smoke, os.X_OK | os.R_OK)
