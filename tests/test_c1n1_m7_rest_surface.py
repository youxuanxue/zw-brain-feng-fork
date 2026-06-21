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

# Write capability (side_effects) held only by ROLE_ORGAN_MANAGER (D57⑧ 反向编目部门审).
WRITE_CAP = "catalog.entry.reverse_draft.confirm"


def test_rest_bearer_low_priv_write_forge_is_denied() -> None:
    """N1: operator-only bearer forging ROLE_ORGAN_MANAGER on a write cap → 403 (not degrade)."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"])
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/{WRITE_CAP}",
                body={"role": "ROLE_ORGAN_MANAGER", "catalog_code": "cat-x", "confirmed": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied", body
        finally:
            stop_server(server, thread)


def test_rest_bearer_authorized_identity_write_passes_authz() -> None:
    """A MANAGER bearer requesting the same write role passes the authz boundary (the
    fix denies only the *forge*, not a legitimately-held write role). Business-layer
    failures (missing draft etc.) are acceptable as long as it is NOT a 403 authz deny."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            token = mint_bearer(keys, roles=["ROLE_ORGAN_MANAGER"])
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/{WRITE_CAP}",
                body={"role": "ROLE_ORGAN_MANAGER", "catalog_code": "cat-x", "confirmed": True},
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


# ── Bug1 (application-flow) 回归：无 cookie 路径把会话机构码注入 payload ──────────
# 根因：cookie BFF 路径经 build_trusted_skill_payload 把会话 org_code 钉进 payload，写侧
# caller_org_code 解析得到机构 → 草稿 applicant_org_code 非空 → 详情/快照 in-scope 腿稳定可见。
# bearer / dev-bypass 无 cookie 路径此前只盖 role、不盖 org_code → 草稿 applicant_org_code=''
# → 切岗位后从快照消失（「未找到该申请」）。修复 = _apply_verified_identity_role 两支均经
# _stamp_identity_org_code 从已验证身份补 org_code（永不信任客户端传值）。


def test_no_cookie_path_stamps_identity_org_code() -> None:
    """无 cookie 路径用已验证身份的机构码盖 payload['org_code']，caller_org_code 可解析。"""
    from zw_brain.entry.rest.server import RestHandler
    from zw_brain.shared.auth_context import AuthContext, reset_auth_context, set_auth_context
    from zw_brain.shared.session_context import caller_org_code

    ctx = AuthContext(
        subject="bearer-user", username="u", tenant_id="sd-default",
        org_code="ORG-A", role_codes=("ROLE_ORGAN_OPERATER",), claims={},
    )
    tok = set_auth_context(ctx)
    try:
        stamped = RestHandler._stamp_identity_org_code({"role": "ROLE_ORGAN_OPERATER", "resource_id": "x"})
        assert stamped["org_code"] == "ORG-A"
        assert caller_org_code(stamped) == "ORG-A", "写侧 caller_org_code 应能解析出会话机构"
        # 客户端传入的 org_code 一律被已验证身份覆盖（与 role 同款不信任客户端）。
        forged = RestHandler._stamp_identity_org_code({"org_code": "ORG-EVIL", "role": "x"})
        assert forged["org_code"] == "ORG-A"
    finally:
        reset_auth_context(tok)


def test_no_cookie_path_leaves_org_empty_without_identity_org() -> None:
    """身份无机构上下文（CLI/A2A）时不捏造 org_code，诚实留空 → 下游 fail-closed。"""
    from zw_brain.entry.rest.server import RestHandler
    from zw_brain.shared.auth_context import AuthContext, reset_auth_context, set_auth_context

    ctx = AuthContext(
        subject="cli", username="u", tenant_id="sd-default",
        org_code=None, role_codes=("ROLE_BUSIAUDIT",), claims={},
    )
    tok = set_auth_context(ctx)
    try:
        stamped = RestHandler._stamp_identity_org_code({"role": "ROLE_BUSIAUDIT"})
        assert "org_code" not in stamped, "无身份机构时不应注入 org_code 键（诚实空）"
    finally:
        reset_auth_context(tok)
