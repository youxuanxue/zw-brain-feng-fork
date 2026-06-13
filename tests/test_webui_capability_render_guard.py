"""段 52 render-debt 守卫升级回潮锁（debt render-guard-slug-grep-false-negative 根治，2026-06-13）。

锁住「webui 可达」判据 = LIT slug 字面量 ∪ ROUTE 专属路由 ∪ PINNED 契约测试钉死（非纯 slug-grep），
防止有人把守卫退回纯字面量 grep → system.snapshot(全站读路径)/契约钉死能力再被误判「未渲染」。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_webui_capability_rendered", REPO / "scripts" / "check_webui_capability_rendered.py"
)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)  # type: ignore[union-attr]


def test_r1_dedicated_route_map_includes_system_snapshot() -> None:
    """ROUTE：openapi 专属路由 /api/snapshot(x-zwbrain-skill-id) → system.snapshot，现取非硬编码。"""
    routes = guard.dedicated_routes()
    assert routes.get("system.snapshot") == "/api/snapshot"
    # 通用 /api/skills/<slug> 路由不得进专属映射（那会让每个能力虚假可达，掏空棘轮）。
    assert all(not p.startswith("/api/skills/") for p in routes.values())


def test_r4_contract_pinned_includes_registry_dispatch_and_base_caps() -> None:
    """PINNED：手写契约测试钉死 5 面 webui 的能力被识别（非循环人工锚）。"""
    pinned = guard.contract_pinned_webui()
    assert "governance.iam_overview" in pinned
    assert "tenant.policy.evaluate" in pinned


def test_system_snapshot_is_reachable_via_r1_not_slug_literal() -> None:
    """全站唯一读路径 system.snapshot：前端无 slug 字面量(LIT=False) 但经专属路由可达(ROUTE=True)。"""
    routes, pinned = guard.reachability_index()
    assert guard.appears_in_src("system.snapshot") is False  # LIT 看不到（走 /api/snapshot）
    assert guard.is_reachable("system.snapshot", routes, pinned) is True  # ROUTE 认


def test_nl_agent_tools_stay_unreachable_and_need_exemption() -> None:
    """platform.docs.*（内置 Agent 工具）既非 LIT/ROUTE/PINNED 可达 → 仍需 NL 豁免（守卫设计内）。"""
    routes, pinned = guard.reachability_index()
    for slug in ("platform.docs.read", "platform.docs.search"):
        assert guard.is_reachable(slug, routes, pinned) is False
        assert slug in guard.load_exemptions()


def test_unknown_capability_is_not_reachable() -> None:
    """棘轮完整性：无任何信号(LIT/ROUTE/PINNED)的未知能力不得被误判可达，否则守卫静默放过真漂移。"""
    routes, pinned = guard.reachability_index()
    assert guard.is_reachable("nonexistent.fake.capability", routes, pinned) is False
    # 通用 /api/skills/<slug> 路由不得当 ROUTE 信号（否则每个能力虚假可达，掏空棘轮）。
    assert "nonexistent.fake.capability" not in routes


def test_guard_passes_no_drift_after_upgrade() -> None:
    """活树现状：所有 live+webui 能力要么 LIT/ROUTE/PINNED 可达、要么登记 NL 豁免——净零漂移。"""
    slugs = set(guard.live_webui_slugs())
    routes, pinned = guard.reachability_index()
    unreached = {s for s in slugs if not guard.is_reachable(s, routes, pinned)}
    exempt = guard.load_exemptions()
    assert unreached - exempt == set(), f"净新增漂移: {sorted(unreached - exempt)}"
    # 台账不得登记已可达 slug（ROUTE/PINNED 现能识别的别再挂手工豁免）。
    stale = {s for s in exempt if s in slugs and s not in unreached}
    assert stale == set(), f"过期豁免(应删): {sorted(stale)}"
