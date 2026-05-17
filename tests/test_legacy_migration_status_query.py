"""Contract test for the legacy.migration.status.query skill + WebUI P0 wiring.

Covers:
- the skill manifest is registered with the correct surfaces + audit class
- BrainService.get_legacy_migration_status returns the expected envelope
- the 11 M0 work-queue cards are always emitted in a stable order with the
  correct status logic against varied input shapes
- the P0 WebUI surface (pages.js + app.js) registers the route, access list,
  shell key, render function, and pre-mount data fetch
"""
from __future__ import annotations

from pathlib import Path

from zw_brain.skill_registration.runtime import get_manifest

REPO = Path(__file__).resolve().parents[1]


def test_skill_manifest_is_registered_and_read_only() -> None:
    manifest = get_manifest("legacy.migration.status.query")
    assert manifest["audit_class"] == "read-trace"
    assert manifest["side_effects"] == []
    assert manifest["audit_required"] is True
    for surface in ("webui", "api"):
        assert surface in manifest["compatibility"]


def test_policy_grants_r7_and_r8() -> None:
    from zw_brain.domain.policy import PERMISSION_ROLES

    allowed = PERMISSION_ROLES.get("legacy.migration.status.query.execute") or set()
    assert "r7" in allowed and "r8" in allowed


def test_brain_service_returns_eleven_work_queue_cards(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "p0_card_contract.sqlite"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    from zw_brain.shared.migrate import ensure_runtime_schema
    ensure_runtime_schema()
    from zw_brain.command.brain import BrainService

    svc = BrainService()
    result = svc.invoke_skill("legacy.migration.status.query", {"role": "r7"})
    assert "totals" in result
    assert "work_queue_cards" in result
    cards = result["work_queue_cards"]
    assert len(cards) == 11
    ids = [c["id"] for c in cards]
    # Fixed order matches the M0 experience document.
    assert ids == [
        "export",
        "import",
        "mapping_verify",
        "catalog_migration_review",
        "schema_mapping",
        "application_history",
        "projection",
        "compliance_sample",
        "handover",
        "gap_reimport",
        "rollback",
    ]
    for card in cards:
        assert card["status"] in {"ready", "partial", "pending", "failed"}
        assert card["owner"]
        assert isinstance(card["summary"], str)


def test_work_queue_card_status_logic_against_synthetic_data() -> None:
    from zw_brain.command.brain import BrainService

    cards = BrainService._build_m0_work_queue_cards(
        totals={"mappings": 0, "mapped": 0, "conflicted": 0, "rolled_back": 0},
        by_canonical={},
        adapter_runs=[],
        rollbacks=[],
    )
    assert {c["id"]: c["status"] for c in cards}["export"] == "pending"
    assert {c["id"]: c["status"] for c in cards}["mapping_verify"] == "pending"

    cards = BrainService._build_m0_work_queue_cards(
        totals={"mappings": 100, "mapped": 100, "conflicted": 0, "rolled_back": 0},
        by_canonical={
            "catalog_entry": {"total": 10, "mapped": 10, "conflicted": 0, "rolled_back": 0},
            "resource_asset": {"total": 50, "mapped": 50, "conflicted": 0, "rolled_back": 0},
            "application_record": {"total": 20, "mapped": 20, "conflicted": 0, "rolled_back": 0},
            "DeliveryTaskRecord": {"total": 20, "mapped": 20, "conflicted": 0, "rolled_back": 0},
            "TopicPackageRecord": {"total": 5, "mapped": 5, "conflicted": 0, "rolled_back": 0},
            "ObjectionCaseRecord": {"total": 3, "mapped": 3, "conflicted": 0, "rolled_back": 0},
        },
        adapter_runs=[{"adapter_slug": f"a{i}", "operation": "import", "status": "succeeded"} for i in range(6)],
        rollbacks=[],
    )
    by_id = {c["id"]: c["status"] for c in cards}
    assert by_id["mapping_verify"] == "ready"
    assert by_id["catalog_migration_review"] == "ready"
    assert by_id["application_history"] == "ready"
    assert by_id["handover"] == "ready"


def test_webui_p0_route_and_access_are_wired() -> None:
    """
    P0 是实施工具，不在客户产品导航里：
    - 路由仍然存在（admin / 实施工程师可直达 URL）
    - ZW_PAGE_ACCESS 收窄到只有 admin（去掉 r7/r8 看见的能力）
    - PRODUCT_SHELL_NAV 不再有 p0 entry — R7/R8/客户都看不到导航入口
    - 渲染函数 PAGES.migrationAcceptance 仍存在以供 admin 直达
    """
    app_js = (REPO / "zw-brain-web" / "js" / "app.js").read_text(encoding="utf-8")
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    # Route registered — admin can still直达
    assert "#/p0-migration-acceptance" in app_js
    assert "page: 'migrationAcceptance'" in app_js
    # Pre-mount data fetch wire 仍在 admin 视角生效
    assert "legacy.migration.status.query" in app_js
    # Access map 收紧到 admin only
    assert "migrationAcceptance: ['admin']" in pages_js
    assert "migrationAcceptance: 'p0'" in pages_js
    # PRODUCT_SHELL_NAV 不再含 p0 nav entry — 没有 "key: 'p0'" 在 PRODUCT_SHELL_NAV
    # 但 ZW_PAGE_SHELL 仍有 p0 映射（用于面包屑/shell key）
    assert "PAGES.migrationAcceptance" in pages_js
    # 验证 p0 不在 product shell nav 中（仅出现在 access/shell 映射、不出现在 nav array）
    import re
    nav_block = re.search(r"const PRODUCT_SHELL_NAV = \[(.*?)\];", pages_js, re.DOTALL)
    assert nav_block, "PRODUCT_SHELL_NAV array must exist"
    assert "key: 'p0'" not in nav_block.group(1), "PRODUCT_SHELL_NAV 不应再含 p0 (M0 不暴露给客户)"


def test_webui_p0_render_handles_missing_state() -> None:
    """Render must not throw when RUNTIME_MIGRATION_ACCEPTANCE is null (pre-mount)."""
    pages_js = (REPO / "zw-brain-web" / "js" / "pages.js").read_text(encoding="utf-8")
    # Look for the early-return loading placeholder.
    assert "正在加载迁移状态" in pages_js
