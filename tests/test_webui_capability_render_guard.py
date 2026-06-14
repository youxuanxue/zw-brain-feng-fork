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


def test_r4_pinned_requires_real_frontend_surface_not_manifest_assertion() -> None:
    """PINNED 只认「手写测试钉死真实前端 surface 文件」的能力，**拒绝循环锚**。

    旧实现把「测试断言 manifest 的 compatibility 含 webui」当 PINNED——但 discover_skills()
    读的就是 manifest，断言 manifest=循环信号(等同 pages.generated.ts)。2026-06-14 上帝视角
    trace 坐实 governance.iam_overview / tenant.policy.evaluate 在 web/src 下**无真实 surface**
    （仅出现在生成产物 pages.generated.ts），故**不得**被 PINNED 误判可达。
    """
    pinned = guard.contract_pinned_webui()
    # 真实 surface 锚（test_iam_governance_web_surface 钉死 .vue/composable）→ 应在 PINNED。
    assert "governance.policy_candidate.list" in pinned
    assert "governance.policy_candidate.review" in pinned
    # 纯 manifest-compatibility 断言的两能力无真实前端落点 → 必须 OUT（消除循环假可达）。
    assert "governance.iam_overview" not in pinned
    assert "tenant.policy.evaluate" not in pinned


def test_pinned_rejects_manifest_reads_manifest_circular_anchor() -> None:
    """回潮锁：PINNED 不接受「manifest-读-manifest」循环锚。

    手工合成一段「断言 discover_skills 的 compatibility 含 webui」(无真实 surface 文件) 不应
    使任意 slug 被 PINNED——否则等于把 manifest 当自身证据，掏空棘轮。这里直接验证 surface 锚
    正则不命中 manifest 路径/生成产物，且 compatibility 断言不构成 surface。
    """
    # manifest 注册目录 / 生成产物路径不算真实 surface。
    assert guard._REAL_SURFACE_ANCHOR.search("registry/pages.generated.ts") is None or \
        guard._GENERATED_PATH_HINT.search("registry/pages.generated.ts") is not None
    assert guard._GENERATED_PATH_HINT.search("zw-brain-web/src/registry/pages.generated.ts") is not None
    # 纯 compatibility 断言行（无 web/src 前端文件）不构成 surface 锚。
    compat_line = 'assert set(skill["compatibility"]) == {"webui", "api", "cli", "mcp", "a2a"}'
    assert guard._REAL_SURFACE_ANCHOR.search(compat_line) is None
    # 真实 .vue surface 锚行命中（且非生成产物）。
    surface_line = '''page = (REPO / "zw-brain-web" / "src" / "pages" / "B12IamGovernance.vue").read_text()'''
    assert guard._REAL_SURFACE_ANCHOR.search(surface_line) is not None
    assert guard._GENERATED_PATH_HINT.search(surface_line) is None


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
