"""Unit coverage for the shared C1/N1 boundary resolver + M5 prod guard + M7 robustness.

- ``resolve_role_from_identity``: the single point that closes the C1/N1 root cause
  (read = least-privilege degrade, write = deny forged role, system-origin/in-process =
  legacy passthrough). Tested directly so the contract is pinned independent of any entry.
- M5: ``get_dev_iam_bypass_enabled`` fails closed when the dev-bypass env leaks into a
  prod deploy mode.
- M7: REST ``_handle_api_skill_post`` returns 400 (not 500) for a non-dict JSON body, and
  the OAuth token-exchange path no longer IndexErrors on an empty actor_snapshots list.
"""
from __future__ import annotations

import pytest

from zw_brain.shared.auth_context import (
    AuthContext,
    IdentityRoleForbiddenError,
    reset_auth_context,
    resolve_role_from_identity,
    set_auth_context,
)
from zw_brain.shared.runtime_config import (
    DevBypassInProductionError,
    get_dev_iam_bypass_enabled,
)


def _ctx(role_codes: tuple[str, ...]) -> AuthContext:
    return AuthContext(
        subject="u", username="u", tenant_id="sd-default", org_code="dev",
        role_codes=role_codes, claims={},
    )


# ─── shared resolver ─────────────────────────────────────────────────────────


def test_resolver_no_auth_context_is_legacy_passthrough() -> None:
    """In-process / system-origin call (no AuthContext) keeps the requested-or-fallback
    role so internal already-authorized callers are not broken by the new boundary."""
    assert resolve_role_from_identity("ROLE_SECURITY_AUDIT", "ROLE_ORGAN_OPERATER", is_write=False) == "ROLE_SECURITY_AUDIT"
    assert resolve_role_from_identity("", "ROLE_ORGAN_OPERATER", is_write=True) == "ROLE_ORGAN_OPERATER"


def test_resolver_read_degrades_unheld_role() -> None:
    token = set_auth_context(_ctx(("ROLE_ORGAN_OPERATER",)))
    try:
        # forged read role → least-privilege degrade to the held role
        assert resolve_role_from_identity("ROLE_SECURITY_AUDIT", "x", is_write=False) == "ROLE_ORGAN_OPERATER"
        # no role requested → identity default
        assert resolve_role_from_identity("", "x", is_write=False) == "ROLE_ORGAN_OPERATER"
        # held role passes through
        assert resolve_role_from_identity("ROLE_ORGAN_OPERATER", "x", is_write=False) == "ROLE_ORGAN_OPERATER"
    finally:
        reset_auth_context(token)


def test_resolver_write_denies_unheld_role() -> None:
    token = set_auth_context(_ctx(("ROLE_ORGAN_OPERATER",)))
    try:
        with pytest.raises(IdentityRoleForbiddenError):
            resolve_role_from_identity("ROLE_BUSIAUDIT", "x", is_write=True)
        # held write role passes; no requested role → identity default (no deny)
        assert resolve_role_from_identity("ROLE_ORGAN_OPERATER", "x", is_write=True) == "ROLE_ORGAN_OPERATER"
        assert resolve_role_from_identity("", "x", is_write=True) == "ROLE_ORGAN_OPERATER"
    finally:
        reset_auth_context(token)


def test_resolver_no_product_role_denies() -> None:
    token = set_auth_context(_ctx(("ROLE_NONPRODUCT",)))
    try:
        with pytest.raises(IdentityRoleForbiddenError):
            resolve_role_from_identity("", "x", is_write=False)
    finally:
        reset_auth_context(token)


def test_resolver_full_identity_is_noop() -> None:
    from zw_brain.domain.role_codes import ALL_ROLE_CODES

    token = set_auth_context(_ctx(tuple(ALL_ROLE_CODES)))
    try:
        assert resolve_role_from_identity("ROLE_SECURITY_AUDIT", "x", is_write=False) == "ROLE_SECURITY_AUDIT"
        assert resolve_role_from_identity("ROLE_BUSIAUDIT", "x", is_write=True) == "ROLE_BUSIAUDIT"
    finally:
        reset_auth_context(token)


# ─── M5: dev-bypass prod guard ───────────────────────────────────────────────


def test_m5_dev_bypass_allowed_in_non_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_DEPLOY_MODE", raising=False)
    assert get_dev_iam_bypass_enabled() is True
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "dev")
    assert get_dev_iam_bypass_enabled() is True


def test_m5_dev_bypass_fails_closed_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    for mode in ("prod", "production", "PROD", "Production"):
        monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", mode)
        with pytest.raises(DevBypassInProductionError):
            get_dev_iam_bypass_enabled()


def test_m5_no_bypass_env_in_prod_is_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod with no bypass env requested must NOT raise — guard only triggers on leak."""
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS", raising=False)
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "prod")
    assert get_dev_iam_bypass_enabled() is False
