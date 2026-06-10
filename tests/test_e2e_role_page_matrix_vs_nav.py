"""守卫：e2e 角色×页面矩阵 spec 须与 PRODUCT_SHELL_NAV 单一事实源一致。

背景（#236）：twin_browser_pages.spec.ts 在 CI seed-light allowlist 内，但其 PAGE_MATRIX
**硬编码** role→page；D55 导航收权后（业务运营员退外部系统/流程表单 → 平台运维员）矩阵漏更，
3 行陈旧断言把 e2e + feature measurement job 拖红，而 capture 只打印 tail[-1]（"N passed"）
把失败吞掉、极难定位。同类陈旧还悄悄蔓延到 6 个 dump-依赖、CI 不跑的 spec。

本守卫把「e2e 矩阵行不得与 nav 角色矛盾」从靠自觉硬化成 **CI 机械检查**（全局宪法 §5）：
任一矩阵行断言某角色可达某顶层页、而 PRODUCT_SHELL_NAV 未把该页授予该角色 → 立即 FAIL，
无需实跑 e2e（pytest 每次 CI 必跑）。这样权限矩阵改一处（nav 配置）即唯一事实源，矩阵 spec
再漂移会在提交期被逮住，而非等 dump 全栈走查才暴露。

范围：只守「hash 路径恰等于某 nav 项 to」的**顶层页**（顶栏可达性 = nav.roles 权威）。更深
子路由（/provider/wizard/* 等）由 pageAccess.ts ROUTE_ROLE_OVERRIDES + activeShellKey 治理，
不在本守卫范围（纳入会误报，因 override 比 shell 更严/更宽）。矩阵里这类行被跳过、不校验。
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_NAV_TS = _ROOT / "zw-brain-web" / "src" / "config" / "productShellNav.ts"

# 矩阵式 spec（每行 = 一个 {role, hash, ...} 断言「该角色应能渲染该页」）。
_MATRIX_SPECS = [
    _ROOT / "tests" / "e2e" / "twin_browser_pages.spec.ts",
    _ROOT / "tests" / "e2e" / "r12_rendered_language.spec.ts",
]


def _nav_to_roles() -> dict[str, set[str]]:
    """解析 PRODUCT_SHELL_NAV，返回 {to 路径: 授权角色集}。

    nav 项字段顺序固定为 ... to: '...', group: '...', (注释) roles: [...]，
    用非贪婪把每个 to 配到其后第一个 roles。自包含文件、无外部 import，可纯文本解析。
    """
    text = _NAV_TS.read_text(encoding="utf-8")
    pairs = re.findall(r"to: '(/[^']+)',[\s\S]*?roles: \[([^\]]+)\]", text)
    out: dict[str, set[str]] = {}
    for to, roles in pairs:
        out[to] = {m.strip().strip("'\"") for m in roles.split(",") if m.strip()}
    return out


def _matrix_rows(spec: Path) -> list[tuple[str, str]]:
    """抽取 spec 里 PAGE_MATRIX 数组内的 (role, hash) 行。只取矩阵块，避开其它 test 的 setRole。"""
    text = spec.read_text(encoding="utf-8")
    block = re.search(r"const PAGE_MATRIX[\s\S]*?=\s*\[([\s\S]*?)\n\];", text)
    assert block, f"{spec.name}: 未找到 PAGE_MATRIX 数组（矩阵 spec 形态变了？）"
    return re.findall(r"role: '(ROLE_[A-Z_]+)',\s*hash: '(#/[^']+)'", block.group(1))


def test_nav_parser_self_check() -> None:
    """防解析器静默失效：nav 至少解析出工作台 + 外部系统，且外部系统已收归平台运维员独有（D55）。"""
    nav = _nav_to_roles()
    assert nav.get("/workbench"), "nav 解析失败：缺 /workbench"
    assert nav.get("/integration-admin") == {"ROLE_SYSTEM"}, (
        f"外部系统应平台运维员独有（D55/P2），实得 {nav.get('/integration-admin')}"
    )


def test_e2e_matrix_rows_match_nav_roles() -> None:
    """每个矩阵 spec 的顶层页行：断言角色须在 PRODUCT_SHELL_NAV 该页授权集内（否则即陈旧漂移）。"""
    nav = _nav_to_roles()
    violations: list[str] = []
    checked = 0
    for spec in _MATRIX_SPECS:
        for role, hash_ in _matrix_rows(spec):
            path = hash_[1:]  # 去掉前导 '#'
            if path not in nav:
                # 更深子路由 / 已退役路由：不在顶层 nav.to，交给 override 层，本守卫跳过。
                continue
            checked += 1
            if role not in nav[path]:
                violations.append(
                    f"{spec.name}: 行 role={role} hash={hash_} 与 nav 矛盾 "
                    f"——该页授权 {sorted(nav[path])}，不含 {role}（D55 导航收权后矩阵漏更？）"
                )
    assert checked > 0, "未校验到任何顶层页矩阵行（解析失效，fail-closed）"
    assert not violations, "e2e 角色×页面矩阵与 nav 单一事实源漂移：\n" + "\n".join(violations)
