"""主导航角色可见性 — ROLE_SYSTEM 须有 B1 入口（防顶栏整栏隐藏）.

ROLE_SECURITY_ADMIN（安全管理员）本期退役（D55/P16），其可见性断言一并移除。
"""
from __future__ import annotations

import re
from pathlib import Path

NAV_TS = Path(__file__).resolve().parents[1] / "zw-brain-web" / "src" / "config" / "productShellNav.ts"


def _roles_for_key(key: str) -> set[str]:
    text = NAV_TS.read_text(encoding="utf-8")
    pattern = rf"key: '{re.escape(key)}'[\s\S]*?roles: \[([^\]]+)\]"
    match = re.search(pattern, text)
    assert match, f"missing nav key {key}"
    return {m.strip().strip("'\"") for m in match.group(1).split(",") if m.strip()}


def test_role_system_sees_platform_ops_nav() -> None:
    """平台运维员不进 J1 主旅程，但须有工作台 + B1 合规/接入顶栏（roles.md §ROLE_SYSTEM）。"""
    assert "ROLE_SYSTEM" in _roles_for_key("workbench")
    assert "ROLE_SYSTEM" in _roles_for_key("compliance-ops")
    assert "ROLE_SYSTEM" in _roles_for_key("integration-admin")
    assert "ROLE_SYSTEM" not in _roles_for_key("request-flow")
