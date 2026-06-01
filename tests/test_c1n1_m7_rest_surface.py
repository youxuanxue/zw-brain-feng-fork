"""REST-surface coverage: N1 write-deny + M7 robustness (non-dict body, empty snapshots).

N1 (REST): #183 derived an identity role for the no-cookie POST path but *degraded* a
forged role even for writes. A low-privilege bearer forging a write role it doesn't hold
must now be denied (403), not silently downgraded to a role that executes the write.

M7: a non-dict JSON POST body must return 400 (REST previously 500'd via AttributeError
in role stamping), matching A2A/CLI which already return 400.
"""
from __future__ import annotations

from tempfile import TemporaryDirectory

from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    http_request,
    mint_bearer,
    run_server,
    stop_server,
)

# Write capability (side_effects) held only by ROLE_BUSIAUDIT.
WRITE_CAP = "catalog.entry.reverse_draft.confirm"


def test_rest_bearer_low_priv_write_forge_is_denied() -> None:
    """N1: operator-only bearer forging ROLE_BUSIAUDIT on a write cap → 403 (not degrade)."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/{WRITE_CAP}",
                body={"role": "ROLE_BUSIAUDIT", "catalog_code": "cat-x", "confirmed": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied", body
        finally:
            stop_server(server, thread)


def test_rest_bearer_authorized_identity_write_passes_authz() -> None:
    """A BUSIAUDIT bearer requesting the same write role passes the authz boundary (the
    fix denies only the *forge*, not a legitimately-held write role). Business-layer
    failures (missing draft etc.) are acceptable as long as it is NOT a 403 authz deny."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_BUSIAUDIT"])
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/{WRITE_CAP}",
                body={"role": "ROLE_BUSIAUDIT", "catalog_code": "cat-x", "confirmed": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            # Not a role-authorization denial: the held role cleared the boundary.
            assert not (status == 403 and isinstance(body, dict) and body.get("error") == "access_denied"), body
        finally:
            stop_server(server, thread)


def test_rest_non_dict_post_body_returns_400() -> None:
    """M7: a JSON array body (non-dict) must be 400, never 500."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/data.search",
                body=["not", "a", "dict"],  # type: ignore[arg-type]
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 400, body
            assert isinstance(body, dict) and body.get("error") == "bad_request", body
        finally:
            stop_server(server, thread)


def test_rest_empty_actor_snapshots_guarded_against_index_error() -> None:
    """M7: the OAuth token-exchange path must guard ``actor_snapshots[0]`` against an empty
    list (→ IndexError → 500). Source contract: the blind ``[0]`` index is gone and an
    emptiness guard precedes the access."""
    import inspect

    from zw_brain.entry.rest.server import RestHandler

    src = inspect.getsource(RestHandler._handle_iaf_token)
    assert 'actor_result["result"]["actor_snapshots"][0]' not in src, (
        "blind actor_snapshots[0] index must be removed (M7)"
    )
    assert "if not snapshots:" in src and "snapshots[0]" in src, (
        "token-exchange path must guard empty actor_snapshots before indexing (M7)"
    )
