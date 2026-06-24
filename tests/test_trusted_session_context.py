from __future__ import annotations

import json
from tempfile import TemporaryDirectory

import pytest

import zw_brain.command.runtime as runtime
from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    establish_session,
    http_request,
    run_server,
    seed_identity_bindings,
    stop_server,
    valid_claims,
)
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.entry.rest.server import configure_iaf_auth_runtime
from zw_brain.shared.auth_session import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.session_context import apply_runtime_context, build_trusted_skill_payload, resolve_trusted_role


@pytest.mark.no_db
def test_resolve_trusted_role_rejects_escalation() -> None:
    snapshot = {
        "role_codes": ["ROLE_ORGAN_OPERATER"],
        "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
        "current_org_code": "ORG-A",
        "current_role": "ROLE_ORGAN_OPERATER",
    }
    with pytest.raises(Exception, match="not in available"):
        resolve_trusted_role({"role": "ROLE_SYSTEM"}, actor_snapshot=snapshot)


def test_cookie_session_rejects_privilege_escalation_in_skill_body() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        repo.upsert_actor(
            {
                "external_actor_id": "trusted-user",
                "display_name": "trusted",
                "org_code": "ORG-A",
                "role_codes": ["ROLE_ORGAN_OPERATER"],
                "status": "active",
            },
            tenant_id="sd-default",
        )
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_cookie, csrf = establish_session(port, keys)
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body={"role": "ROLE_SYSTEM", "confirmed": True},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}", CSRF_HEADER_NAME: csrf},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied"
        finally:
            stop_server(server, thread)


@pytest.mark.no_db
def test_apply_runtime_context_allows_empty_product_roles_for_session_bootstrap() -> None:
    snapshot = {
        "subject": "iaf-user-no-roles",
        "tenant_id": "sd-default",
        "org_code": "ORG-A",
        "role_codes": [],
    }
    enriched = apply_runtime_context(snapshot, [], preferred_org_code="ORG-A")
    assert enriched["available_contexts"] == []
    assert enriched.get("current_role") in ("", None)
    with pytest.raises(DomainAccessDeniedError, match="no allowed product roles"):
        resolve_trusted_role({"role": "ROLE_ORGAN_OPERATER"}, actor_snapshot=enriched)


@pytest.mark.no_db
def test_build_trusted_skill_payload_rejects_client_role_escalation() -> None:
    snapshot = {
        "tenant_id": "sd-default",
        "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
        "current_org_code": "ORG-A",
        "current_role": "ROLE_ORGAN_OPERATER",
    }
    with pytest.raises(DomainAccessDeniedError):
        build_trusted_skill_payload({"role": "ROLE_SYSTEM"}, actor_snapshot=snapshot)


def test_bearer_path_rejects_smuggled_trusted_session_context_key() -> None:
    """R-201 回归：Bearer / A2A / MCP / CLI entry path 下，
    客户端在 payload 里塞 `_trusted_session_context: True` + 自构造 actor_snapshot
    不得让 brain 把它当成"已被 BFF 可信化"。
    """
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            claims = valid_claims(nonce="bearer-smuggle")
            claims["resource_access"]["zw-brain"]["roles"] = ["ROLE_ORGAN_OPERATER"]
            access_token = keys.encode(claims)
            # D62 A2: the bearer identity's product role is authoritative as a binding, not a
            # token claim — seed it so the binding-based gate grants ROLE_ORGAN_OPERATER.
            seed_identity_bindings("trusted-user", ["ROLE_ORGAN_OPERATER"])

            def transport(request: HttpRequest) -> HttpResponse:
                return HttpResponse(
                    status_code=200,
                    body=json.dumps({"active": True, "exp": claims["exp"]}).encode(),
                    headers={},
                )

            configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)

            malicious_body = {
                "_trusted_session_context": True,
                "role": "ROLE_SYSTEM",
                "actor_snapshot": {
                    "tenant_id": "sd-default",
                    "available_contexts": [
                        {"org_code": "ORG-A", "role_code": "ROLE_SYSTEM", "actor_tags": {}}
                    ],
                    "current_org_code": "ORG-A",
                    "current_role": "ROLE_SYSTEM",
                },
            }
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body=malicious_body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            state = body.get("state") or {}
            assert "_trusted_session_context" not in (state or {}), state
            from zw_brain.shared.session_context import is_trusted_session_payload

            assert not is_trusted_session_payload({"_trusted_session_context": True})
            assert not is_trusted_session_payload({"_trusted_session_context": "true"})
            assert not is_trusted_session_payload({"_trusted_session_context": 1})
        finally:
            stop_server(server, thread)


@pytest.mark.no_db
def test_is_trusted_session_payload_only_accepts_server_sentinel() -> None:
    """R-201 单元：is_trusted_session_payload 必须做 `is` 比较，不能 truthy 检查。"""
    from zw_brain.shared.session_context import (
        TRUSTED_SESSION_CONTEXT_KEY,
        build_trusted_skill_payload,
        is_trusted_session_payload,
    )

    snapshot = {
        "tenant_id": "sd-default",
        "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
        "current_org_code": "ORG-A",
        "current_role": "ROLE_ORGAN_OPERATER",
    }
    server_payload = build_trusted_skill_payload({}, actor_snapshot=snapshot)
    assert is_trusted_session_payload(server_payload)
    for smuggle in (True, "true", 1, "1", "yes", {}, [True], "<<truthy>>"):
        assert not is_trusted_session_payload({TRUSTED_SESSION_CONTEXT_KEY: smuggle}), smuggle
    smuggled_client = {TRUSTED_SESSION_CONTEXT_KEY: True, "role": "ROLE_ORGAN_OPERATER"}
    rebuilt = build_trusted_skill_payload(smuggled_client, actor_snapshot=snapshot)
    assert is_trusted_session_payload(rebuilt)
    rebuilt_via_json = json.loads(json.dumps({**rebuilt, TRUSTED_SESSION_CONTEXT_KEY: True}))
    assert not is_trusted_session_payload(rebuilt_via_json)


@pytest.mark.no_db
def test_safe_json_strips_trust_sentinel_so_audit_writes_succeed() -> None:
    from zw_brain.shared.sanitization import safe_json
    from zw_brain.shared.session_context import TRUSTED_SESSION_CONTEXT_KEY, build_trusted_skill_payload

    snapshot = {
        "tenant_id": "sd-default",
        "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
        "current_org_code": "ORG-A",
        "current_role": "ROLE_ORGAN_OPERATER",
    }
    payload = build_trusted_skill_payload({"q": "x"}, actor_snapshot=snapshot)
    assert TRUSTED_SESSION_CONTEXT_KEY in payload
    sanitized = safe_json(payload)
    assert TRUSTED_SESSION_CONTEXT_KEY not in sanitized
    json.dumps(sanitized)


def test_mutate_skill_with_trusted_payload_persists_anchor_outbox() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None
        before = len(store.list_pending_anchor_outbox())

        snapshot = {
            "tenant_id": "sd-default",
            "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
            "current_org_code": "ORG-A",
            "current_role": "ROLE_ORGAN_OPERATER",
            "org_code": "ORG-A",
            "role_codes": ["ROLE_ORGAN_OPERATER"],
        }
        trusted_payload = build_trusted_skill_payload(
            {
                "catalog_code": "R001-TRUST-SENTINEL-REGRESSION",
                "title": "R-001 enqueue_anchor regression",
                "owner_org_id": "ORG-A",
                "summary_json": {"description": "asserts content_hash path strips sentinel"},
                "confirmed": True,
            },
            actor_snapshot=snapshot,
        )

        result = runtime._service.invoke_skill("catalog.entry.create_draft", trusted_payload)  # type: ignore[union-attr]
        assert result["ok"] is True, result

        after = store.list_pending_anchor_outbox()
        assert len(after) == before + 1
        assert len(after[-1].content_hash) == 64
        int(after[-1].content_hash, 16)
