"""WebUI 路由岗位门禁：与 zw-brain-web/src/lib/pageAccess.ts 语义一致。"""

from __future__ import annotations

# 与 productShellNav.ts PRODUCT_SHELL_NAV 同步
_SHELL_ROLES: dict[str, frozenset[str]] = {
    "workbench": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
            "ROLE_SYSTEM",
        }
    ),
    "discovery": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    "request-flow": frozenset({"ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER"}),
    "delivery-exchange": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    "provider": frozenset({"ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT"}),
    "compliance-ops": frozenset(
        {
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
            "ROLE_SECURITY_ADMIN",
            "ROLE_SYSTEM",
        }
    ),
    "zones-pack": frozenset(
        {
            "ROLE_ORGAN_OPERATER",
            "ROLE_ORGAN_MANAGER",
            "ROLE_BUSIAUDIT",
            "ROLE_SECURITY_AUDIT",
        }
    ),
    "integration-admin": frozenset({"ROLE_BUSIAUDIT", "ROLE_SYSTEM"}),
}


def _active_shell_key(path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    if p.startswith("/discovery"):
        return "discovery"
    if p.startswith("/request-flow"):
        return "request-flow"
    if p.startswith("/delivery-exchange"):
        return "delivery-exchange"
    if p.startswith("/provider"):
        return "provider"
    if p.startswith("/compliance-ops"):
        return "compliance-ops"
    if p.startswith("/zones-pack"):
        return "zones-pack"
    if p.startswith("/integration-admin"):
        return "integration-admin"
    return "workbench"


def _is_route_allowed(path: str, role: str) -> bool:
    key = _active_shell_key(path)
    return role in _SHELL_ROLES.get(key, frozenset())


def test_operater_cannot_access_integration_admin() -> None:
    assert not _is_route_allowed("/integration-admin", "ROLE_ORGAN_OPERATER")
    assert not _is_route_allowed("/integration-admin/engines", "ROLE_ORGAN_OPERATER")


def test_system_can_access_integration_admin() -> None:
    assert _is_route_allowed("/integration-admin", "ROLE_SYSTEM")


def test_operater_can_access_workbench() -> None:
    assert _is_route_allowed("/workbench", "ROLE_ORGAN_OPERATER")
