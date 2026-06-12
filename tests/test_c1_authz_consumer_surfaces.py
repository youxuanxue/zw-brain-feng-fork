"""C1 completion + N1 — verified-identity role boundary across MCP / A2A / CLI.

#183 closed the read-authorization-bypass (C1) only at the REST entry layer. The shared
resolution point (``brain._resolve_role``) still trusted ``payload["role"]`` verbatim for
every non-cookie payload, and the MCP / A2A / CLI entry paths never derived the role from a
verified identity. A client of those daemons could therefore forge ``role`` and read/call a
capability its identity does not hold.

This suite proves the fix is now enforced at the *shared boundary* and is visible on all
three consumer surfaces #183 missed:

  * C1 (read): a low-privilege identity forging ``ROLE_SECURITY_AUDIT`` cannot read
    ``audit.event.query`` — the request degrades to its real role, which lacks audit-read
    permission, so it is denied.
  * N1 (write): the same identity forging ``ROLE_ORGAN_MANAGER`` on a *write* capability
    (``catalog.entry.reverse_draft.confirm``, held only by ROLE_ORGAN_MANAGER per D57⑧
    两级管线部门审) is denied outright (not silently degraded to a role that would execute
    with a forged actor / corrupt audit attribution).

The daemons start only under dev-IAM-bypass, whose synthetic identity normally holds every
role (resolver is then a no-op). These tests narrow that identity via
``ZW_BRAIN_DEV_IAM_BYPASS_ROLES`` to reproduce a restricted real-world caller. Removing the
fix (the shared resolver / the dev-identity binding) makes every deny assertion FAIL — the
forged role would be honored — which is exactly the bug being guarded.
"""
from __future__ import annotations

import pytest

from zw_brain.domain.errors import AccessDeniedError

# A read capability the operator role does NOT hold (SECURITY_AUDIT/BUSIAUDIT/SYSTEM only).
READ_CAP = "audit.event.query"
# A write capability (side_effects) held only by ROLE_ORGAN_MANAGER (D57⑧ 部门审).
WRITE_CAP = "catalog.entry.reverse_draft.confirm"


@pytest.fixture
def low_priv_dev_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """dev-IAM-bypass narrowed to a single low-privilege product role.

    This is the realistic forge scenario: an authenticated identity that holds only
    ROLE_ORGAN_OPERATER attempting to act as a higher-privilege role it was never granted.
    """
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", "ROLE_ORGAN_OPERATER")


# ─── C1 read bypass — MCP ────────────────────────────────────────────────────


def test_mcp_low_priv_cannot_forge_audit_read(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.mcp.server import call_tool

    with pytest.raises(AccessDeniedError):
        # Forge SECURITY_AUDIT: identity holds only OPERATER → degrade to OPERATER →
        # OPERATER lacks audit.event.query.execute → denied.
        call_tool(READ_CAP, {"role": "ROLE_SECURITY_AUDIT"})


def test_mcp_low_priv_cannot_read_audit_without_role(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.mcp.server import call_tool

    with pytest.raises(AccessDeniedError):
        call_tool(READ_CAP, {})


def test_mcp_handle_tools_call_forged_audit_returns_error(low_priv_dev_identity: None) -> None:
    """The JSON-RPC surface (Cursor/Claude path) must also reject, surfacing an error
    envelope rather than the audit data."""
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(
        id_=7, params={"name": READ_CAP, "arguments": {"role": "ROLE_SECURITY_AUDIT"}}
    )
    assert "error" in resp, resp
    assert "AccessDenied" in resp["error"]["message"], resp


# ─── C1 read bypass — A2A ────────────────────────────────────────────────────


def test_a2a_low_priv_cannot_forge_audit_read(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.a2a.server import invoke

    with pytest.raises(AccessDeniedError):
        invoke(READ_CAP, {"role": "ROLE_SECURITY_AUDIT"})


# ─── C1 read bypass — CLI ────────────────────────────────────────────────────


def test_cli_low_priv_cannot_forge_audit_read(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.cli.main import _invoke_inprocess

    code, result = _invoke_inprocess(READ_CAP, {"role": "ROLE_SECURITY_AUDIT"})
    assert code != 0, result
    assert "AccessDenied" in str(result.get("error", "")), result


# ─── N1 write deny — all surfaces ────────────────────────────────────────────


def test_mcp_low_priv_write_forge_is_denied(low_priv_dev_identity: None) -> None:
    """N1: forging ROLE_ORGAN_MANAGER on a write capability must be denied outright — the
    request is NOT degraded to a role that could execute the write with a forged actor."""
    from zw_brain.entry.mcp.server import call_tool

    with pytest.raises(AccessDeniedError):
        call_tool(WRITE_CAP, {"role": "ROLE_ORGAN_MANAGER", "catalog_code": "cat-x", "confirmed": True})


def test_a2a_low_priv_write_forge_is_denied(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.a2a.server import invoke

    with pytest.raises(AccessDeniedError):
        invoke(WRITE_CAP, {"role": "ROLE_ORGAN_MANAGER", "catalog_code": "cat-x", "confirmed": True})


def test_cli_low_priv_write_forge_is_denied(low_priv_dev_identity: None) -> None:
    from zw_brain.entry.cli.main import _invoke_inprocess

    code, result = _invoke_inprocess(
        WRITE_CAP, {"role": "ROLE_ORGAN_MANAGER", "catalog_code": "cat-x", "confirmed": True}
    )
    assert code != 0, result
    assert "AccessDenied" in str(result.get("error", "")), result


# ─── Non-regression: full-role dev identity still works (dev-bypass unbroken) ─


def test_full_role_dev_identity_read_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default dev-IAM-bypass (all roles) is unaffected: a forged role is "held" by the
    synthetic identity, so MCP/A2A/CLI keep working exactly as before."""
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", raising=False)
    from zw_brain.entry.mcp.server import call_tool

    # Full-role synthetic identity holds SECURITY_AUDIT → audit read is permitted.
    result = call_tool(READ_CAP, {"role": "ROLE_SECURITY_AUDIT"})
    assert result["tool"] == READ_CAP
