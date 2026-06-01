"""C1 regression — read-capability server-side authorization must not be bypassable.

Defect: a read-only capability that declares ``permissions`` had its permission check
skipped whenever the inbound payload lacked a ``role`` key (the
``if not side_effects and "role" not in payload: return`` escape in
``enforce_manifest_policy``). Combined with the REST bearer path not stamping an
identity-derived role, a low-privilege IAF token holder could read sensitive
SECURITY_AUDIT/BUSIAUDIT capabilities (e.g. ``audit.event.query``) by simply not
sending a ``role``.

Two independent layers are asserted here:
  1. Domain (``enforce_manifest_policy``): a permissioned read with an under-privileged
     resolved role is rejected — no role-key escape.
  2. Entry (REST bearer/no-cookie path): the authorization role is derived from the
     verified identity, never trusted from the client; cookie + dev-bypass paths still
     work.
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    establish_session,
    http_request,
    mint_bearer,
    run_server,
    stop_server,
)
from zw_brain.domain.policy import DomainAccessDeniedError, enforce_manifest_policy
from zw_brain.shared.auth_session import SESSION_COOKIE_NAME

# ── Layer 1: domain policy ──────────────────────────────────────────────────


def test_permissioned_read_without_role_key_is_still_enforced() -> None:
    """The role-key escape is gone: a permissioned read-only cap is enforced against
    the resolved role even when the original payload carried no ``role`` key."""
    manifest = {
        "tenant_scope": "global",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": ["audit.event.query.execute"],
    }
    # ROLE_ORGAN_OPERATER does NOT hold audit.event.query.execute → must be denied
    # despite the empty payload (no "role" key).
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("audit.event.query", manifest, "ROLE_ORGAN_OPERATER", {})


def test_permissioned_read_with_authorized_role_passes() -> None:
    """An authorized resolved role still passes the same permissioned read — the fix
    denies only the *under-privileged* case, not legitimate reads."""
    manifest = {
        "tenant_scope": "global",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": ["audit.event.query.execute"],
    }
    enforce_manifest_policy("audit.event.query", manifest, "ROLE_SECURITY_AUDIT", {})


def test_unpermissioned_read_remains_public() -> None:
    """Capabilities that declare no permissions stay public-by-design (no-op check)."""
    manifest = {
        "tenant_scope": "global",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": [],
    }
    enforce_manifest_policy("public.read", manifest, "ROLE_ORGAN_OPERATER", {})


# ── Layer 2: REST entry boundary ────────────────────────────────────────────


def test_bearer_low_priv_cannot_read_audit_without_role() -> None:
    """A low-privilege bearer token (ROLE_ORGAN_OPERATER) calling audit.event.query with
    NO ?role= must be denied (403) — role is derived from the verified identity, not the
    absent query param, and the operator role lacks audit read permission."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied"
        finally:
            stop_server(server, thread)


def test_bearer_low_priv_cannot_spoof_role_in_query() -> None:
    """A low-privilege bearer token cannot escalate by passing ?role=ROLE_SECURITY_AUDIT;
    the identity-derived role overrides the client-supplied one."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/audit.event.query?role=ROLE_SECURITY_AUDIT",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied"
        finally:
            stop_server(server, thread)


def test_bearer_authorized_identity_can_read_audit() -> None:
    """A bearer token whose identity actually holds ROLE_SECURITY_AUDIT can read
    audit.event.query — the fix doesn't break legitimate auditors."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_SECURITY_AUDIT"])
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 200, body
        finally:
            stop_server(server, thread)


def test_bearer_low_priv_can_still_read_own_capability() -> None:
    """The operator identity can still read a capability its role holds (data.search)
    without sending a role — the fix denies only under-privileged access."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/data.search?query=test",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 200, body
        finally:
            stop_server(server, thread)


def test_cookie_session_audit_read_unaffected() -> None:
    """Cookie BFF path is unchanged: a session whose role holds audit read can read it."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys, extra_roles=["ROLE_SECURITY_AUDIT"])
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/audit.event.query?role=ROLE_SECURITY_AUDIT",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 200, body
        finally:
            stop_server(server, thread)
