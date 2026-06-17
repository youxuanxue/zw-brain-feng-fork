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
    """平台运维员不进 J1 主旅程，但须有工作台 + B1 服务调用监控 / 接入顶栏（roles.md §ROLE_SYSTEM）。

    查审计拆分（D55/P8·P9，Wave1-S3）：平台运维员退审计日志（compliance-ops），
    保服务调用监控（service-ops）。故 B1 顶栏入口从 compliance-ops 迁到 service-ops。
    """
    assert "ROLE_SYSTEM" in _roles_for_key("workbench")
    # 退审计日志：平台运维员不再看到「查审计」导航（无权 = 不可见）。
    assert "ROLE_SYSTEM" not in _roles_for_key("compliance-ops")
    # 保服务调用监控：平台运维员看到「服务调用监控」导航（v5 服务调用日志 = 平台运维员）。
    assert "ROLE_SYSTEM" in _roles_for_key("service-ops")
    assert "ROLE_SYSTEM" in _roles_for_key("integration-admin")
    # 「办申请」(request-flow) 导航项已随 IA 重构整体删除（我的申请/授权并入领数据、
    # 受理/审核迁工作台），不再有 request-flow 导航键——平台运维员自然不可见。
