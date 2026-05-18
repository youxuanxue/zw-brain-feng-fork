from __future__ import annotations

import base64
import http.client
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import zw_brain.command.runtime as runtime
from zw_brain.command.brain import BrainService
from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer, configure_iaf_auth_runtime
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore


def _encode_mock_jwt(payload: dict[str, object]) -> str:
    def _b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("utf-8").rstrip("=")

    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(payload)}.sig"


class _KeyFixture:
    def __init__(self, kid: str = "callback-key") -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}
        self.kid = kid

    def encode(self, claims: dict[str, Any], *, key: Any | None = None, kid: str | None = None, alg: str = "RS256") -> str:
        return jwt.encode(claims, key or self.private_key, algorithm=alg, headers={"kid": kid or self.kid, "typ": "JWT"})


def _valid_claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": "iaf-bound-user",
        "iss": "https://iaf.example/auth/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "state": "state-e2e",
        "nonce": "nonce-e2e",
        "preferred_username": "bound_user",
        "project_id": "sd-default",
        "project": "shandong",
        "realm_access": {"roles": ["ACCOUNT_ADMIN"]},
        "resource_access": {"zw-brain": {"roles": ["r7"]}},
        "phone": "13800001111",
        "email": "bound@sd.gov.cn",
    }
    claims.update(overrides)
    return claims


def _new_database_service(tmp: str) -> tuple[DatabaseStore, BrainService]:
    os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
    os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
    os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/auth/realms/picp"
    os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    runtime._service = None
    return database_store, BrainService(state_store=StateStore(database_store=database_store))


def _apply_minimum_policy(service: BrainService) -> None:
    service.invoke_skill("package.review_decide", {"package_id": "PKG-2026-04-25-001", "decision": "approve", "role": "r7", "confirmed": True})
    service.invoke_skill("package.register_version", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
    service.invoke_skill("package.apply_tenant_policy", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})


def _assert_no_secrets(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ["secret", "password", "token", "refresh_token", "client_secret", "verification_code", "sms_status", "session", "cookie"]:
        assert forbidden not in text


def _request(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    accept: str = "application/json",
) -> tuple[int, dict[str, str], str]:
    parsed = urlparse(url)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Accept": accept, "Host": parsed.netloc}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=5)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        return response.status, {key.lower(): value for key, value in response.getheaders()}, raw
    finally:
        conn.close()


def _request_raw(method: str, url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=5)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request(method, path, body=None, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        hdrs = {k.lower(): v for k, v in response.getheaders()}
        return response.status, raw, hdrs
    finally:
        conn.close()


def _request_json(method: str, url: str, body: dict[str, object] | None = None) -> tuple[int, dict[str, Any]]:
    status, _headers, raw = _request(method, url, body)
    return status, json.loads(raw or "{}")


def _run_rest_server() -> tuple[ThreadingRestServer, Thread, int]:
    server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def test_f6_offline_iaf_legacy_policy_governance_acceptance_chain() -> None:
    with TemporaryDirectory() as tmp:
        database_store, service = _new_database_service(tmp)
        _apply_minimum_policy(service)
        database_store.capability_package_repo.upsert_tenant_policy(
            {
                "slug": "topic.package.publish",
                "status": "approved",
                "source": "offline-e2e",
                "auditClass": "write-critical",
                "requiresHuman": False,
                "tenantPolicy": {"role_codes": ["r7"]},
                "exposure": ["api", "webui", "cli", "mcp", "a2a"],
            },
            tenant_id="sd-default",
            exposed_surfaces=["api", "webui", "cli", "mcp", "a2a"],
        )
        service.invoke_skill(
            "org.projection.sync",
            {
                "tenant": {"tenant_id": "sd-default", "tenant_name": "山东省"},
                "regions": [{"region_code": "370000", "region_name": "山东省"}],
                "orgs": [{"org_code": "ORG-YBT", "org_name": "一表通专班", "region_code": "370000"}],
                "roles": [{"role_code": "r7", "role_name": "目录管理员"}],
                "role": "r7",
                "confirmed": True,
            },
        )
        token = _encode_mock_jwt(_valid_claims())
        actor_result = service.invoke_skill(
            "actor.projection.sync",
            {
                "iaf_claims": token,
                "expected_state": "state-e2e",
                "expected_nonce": "nonce-e2e",
                "tenant_id": "sd-default",
                "org_code": "ORG-YBT",
                "role": "r7",
                "confirmed": True,
            },
        )
        actor_snapshot = actor_result["result"]["actor_snapshots"][0]
        assert actor_snapshot["subject"] == "iaf-bound-user"
        assert actor_snapshot["status"] == "active"
        assert set(actor_snapshot["role_codes"]) == {"ACCOUNT_ADMIN", "r7"}
        assert actor_snapshot["account_flags"] == {"account_admin": True}

        dry_run = service.invoke_skill(
            "legacy.bsp.mapping.import",
            {
                "mode": "dry-run",
                "rows": [
                    {"legacy_permission_ref": "legacy:ledger:read", "legacy_role_ref": "ROLE_LEDGER", "capability_id": "topic.package.publish", "surface": "api", "evidence_json": {"source": "bsp-fixture", "password": "drop", "token": "drop"}},
                    {"legacy_permission_ref": "legacy:unknown", "legacy_role_ref": "ROLE_UNKNOWN", "capability_id": "unknown.capability", "surface": "api", "evidence_json": {"client_secret": "drop"}},
                    {"legacy_permission_ref": "legacy:iam-missing", "legacy_role_ref": "ROLE_IAM_MISSING", "capability_id": "topic.package.publish", "candidate_status": "iam_account_missing"},
                ],
                "role": "r7",
                "confirmed": True,
            },
        )
        assert dry_run["result"]["summary"]["source_count"] == 3
        assert dry_run["result"]["summary"]["blockers"]["unmapped_permission"] == 1
        assert dry_run["result"]["summary"]["blockers"]["iam_account_missing"] == 1
        _assert_no_secrets(dry_run)

        apply_payload = dry_run["result"]["items"]
        apply_rows = [
            {
                "legacy_permission_ref": item["legacy_permission_ref"],
                "legacy_role_ref": item["legacy_role_ref"],
                "capability_id": item["capability_id"],
                "surface": item.get("surface"),
                "candidate_status": item.get("candidate_status"),
                "evidence_json": item.get("evidence_json", {}),
            }
            for item in apply_payload
        ]
        applied_first = service.invoke_skill("legacy.bsp.mapping.import", {"mode": "apply", "rows": apply_rows, "role": "r7", "confirmed": True})
        applied_second = service.invoke_skill("legacy.bsp.mapping.import", {"mode": "apply", "rows": apply_rows, "role": "r7", "confirmed": True})
        assert applied_first["result"]["summary"] == applied_second["result"]["summary"]
        assert len(database_store.governance_projection_repo.list_policy_candidates(tenant_id="sd-default")) == 1

        allowed = service.invoke_skill(
            "tenant.policy.evaluate",
            {
                "tenant_id": "sd-default",
                "capability_id": "topic.package.publish",
                "surface": "api",
                "role": "r7",
                "role_codes": ["ACCOUNT_ADMIN", "r7"],
                "actor_snapshot": actor_snapshot,
                "org_snapshot": {"tenant_id": "sd-default", "org_code": "ORG-YBT"},
            },
        )
        assert allowed["allowed"] is True
        assert allowed["decision_reason"] == "allowed_by_tenant_policy"

        missing_policy = service.invoke_skill("tenant.policy.evaluate", {"tenant_id": "sd-default", "capability_id": "unknown.capability", "surface": "api", "role": "r7", "actor_snapshot": actor_snapshot})
        assert missing_policy["allowed"] is False
        assert missing_policy["decision_reason"] == "missing_tenant_policy"

        admin_only = dict(actor_snapshot) | {"role_codes": ["ACCOUNT_ADMIN"]}
        denied_admin = service.invoke_skill("tenant.policy.evaluate", {"tenant_id": "sd-default", "capability_id": "topic.package.publish", "surface": "api", "role": "r2", "role_codes": ["ACCOUNT_ADMIN"], "actor_snapshot": admin_only})
        assert denied_admin["allowed"] is False
        assert denied_admin["decision_reason"] == "role_not_allowed_by_registry"

        overview = service.invoke_skill("governance.iam_overview", {"tenant_id": "sd-default", "role": "r7"})
        assert overview["summary"]["actor_count"] == 1
        assert overview["summary"]["policy_count"] >= 1
        assert any(item["type"] in {"unmapped_permission", "iam_account_missing"} for item in overview["import_issues"])
        assert any(item["skill_id"] == "tenant.policy.evaluate" and item["phase"] == "after" for item in overview["audit_events"])
        _assert_no_secrets(overview)

        service.invoke_skill("tenant.capability.disable", {"package_id": "PKG-2026-04-25-001", "role": "r7", "confirmed": True})
        disabled = service.invoke_skill("tenant.policy.evaluate", {"tenant_id": "sd-default", "capability_id": "ledger.entity.base.read", "surface": "api", "role": "r7", "actor_snapshot": actor_snapshot})
        assert disabled["allowed"] is False
        assert disabled["decision_reason"] == "tenant_policy_disabled"

        audit_payloads = [item.payload_json for item in database_store.list_audit_events()]
        capability_payloads = [item.input_json | item.output_json for item in database_store.list_capability_calls()]
        _assert_no_secrets(audit_payloads)
        _assert_no_secrets(capability_payloads)
        assert os.environ.get("ZW_BRAIN_LEGACY_BSP_ONLINE_URL") is None


def test_iaf_oidc_rest_login_token_logout_uses_rs256_jwks_path() -> None:
    with TemporaryDirectory() as tmp:
        _new_database_service(tmp)
        keys = _KeyFixture()
        captured: dict[str, Any] = {}

        def transport(request: HttpRequest) -> HttpResponse:
            captured.setdefault("requests", []).append({"method": request.method, "url": request.url, "body": request.body.decode("utf-8")})
            if request.method == "POST":
                form = parse_qs(request.body.decode("utf-8"))
                token = keys.encode(_valid_claims(nonce=captured["nonce"]))
                captured["token_form"] = form
                return HttpResponse(status_code=200, body=json.dumps({"access_token": token, "refresh_token": "refresh-1", "id_token": token, "token_type": "Bearer", "expires_in": 300}).encode("utf-8"), headers={})
            return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode("utf-8"), headers={})

        configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
        server, thread, port = _run_rest_server()
        try:
            login_url = f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/"
            status, headers, body = _request("GET", login_url, accept="text/html")
            assert status == 302
            assert body == ""
            auth_params = parse_qs(urlparse(headers["location"]).query)
            assert auth_params["client_id"] == ["zw-brain"]
            assert auth_params["redirect_uri"] == [f"http://127.0.0.1:{port}/"]
            assert auth_params["response_mode"] == ["query"]
            assert auth_params["response_type"] == ["code"]
            assert auth_params["scope"] == ["openid"]
            login_state = auth_params["state"][0]
            captured["nonce"] = auth_params["nonce"][0]

            status, login = _request_json("GET", f"{login_url}&format=json")
            assert status == 200
            json_auth_params = parse_qs(urlparse(login["authorization_url"]).query)
            assert json_auth_params["response_mode"] == ["query"]
            assert json_auth_params["scope"] == ["openid"]
            assert json_auth_params["state"] == [login["state"]]
            assert json_auth_params["nonce"] == [login["nonce"]]

            status, callback = _request_json("POST", f"http://127.0.0.1:{port}/auth/iaf/token", {"code": "auth-code", "state": login_state})
            assert status == 200
            assert callback["authenticated"] is True
            assert callback["actor_snapshot"]["subject"] == "iaf-bound-user"
            assert callback["actor_snapshot"]["role_codes"] == ["ACCOUNT_ADMIN", "r7"]
            assert captured["token_form"]["code"] == ["auth-code"]
            assert captured["token_form"]["redirect_uri"] == [f"http://127.0.0.1:{port}/"]
            _assert_no_secrets({k: v for k, v in callback.items() if k in {"authenticated", "actor_snapshot", "audit_id"}})
            store = runtime.get_service()._state_store.database_store
            assert store is not None
            _assert_no_secrets([item.payload_json for item in store.list_audit_events()])
            _assert_no_secrets([item.input_json | item.output_json for item in store.list_capability_calls()])

            # Re-establish a session so the cookie path drives logout; the previous /auth/iaf/token
            # response set the cookie, but _request_json discards headers — we need a fresh login
            # whose Set-Cookie we capture and replay.
            status_re_login, _, login2_raw = _request("GET", f"{login_url}&format=json")
            assert status_re_login == 200
            login2 = json.loads(login2_raw)
            captured["nonce"] = login2["nonce"]
            status_re_token, token_headers, _ = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/token", {"code": "auth-code", "state": login2["state"]})
            assert status_re_token == 200
            session_cookie = ""
            for chunk in (token_headers.get("set-cookie", "") or "").split(","):
                for part in chunk.split(";"):
                    part = part.strip()
                    if part.startswith("zw_brain_session="):
                        session_cookie = part.split("=", 1)[1]
            assert session_cookie

            # Issue logout with the cookie attached so id_token_hint flows from the session.
            status_logout, logout_raw, _ = _request_raw(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri=http://127.0.0.1:{port}/",
                headers={"Accept": "application/json", "Cookie": f"zw_brain_session={session_cookie}"},
            )
            assert status_logout == 200
            logout = json.loads(logout_raw)
            assert logout["logout_url"].startswith("https://iaf.example/auth/realms/picp/protocol/openid-connect/logout")
            assert "post_logout_redirect_uri=" in logout["logout_url"]
            # id_token_hint is forwarded so the IdP can honor post_logout_redirect_uri without prompting.
            # Source of truth is the session's stored id_token; we just assert presence + non-empty value.
            assert "id_token_hint=" in logout["logout_url"]
            assert "id_token_hint=&" not in logout["logout_url"]
            assert logout["local_auth_cleared"] is True
            _assert_no_secrets({k: v for k, v in logout.items() if k != "logout_url"})

            status, bad_login_redirect = _request_json("GET", f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=https://evil.example/callback")
            assert status == 400
            assert bad_login_redirect["detail"] == "redirect origin mismatch"
            status, bad_logout_redirect = _request_json("GET", f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri=https://evil.example/")
            assert status == 400
            assert bad_logout_redirect["detail"] == "redirect origin mismatch"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None, jwks=None)


def test_iaf_oidc_rest_token_endpoint_establishes_bff_session_for_spa() -> None:
    with TemporaryDirectory() as tmp:
        _new_database_service(tmp)
        keys = _KeyFixture()
        captured: dict[str, Any] = {}

        def transport(request: HttpRequest) -> HttpResponse:
            if request.method == "POST":
                token = keys.encode(_valid_claims(nonce=captured["nonce"]))
                return HttpResponse(status_code=200, body=json.dumps({"access_token": token, "refresh_token": "refresh-1", "id_token": token, "expires_in": 300, "token_type": "Bearer"}).encode("utf-8"), headers={})
            return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode("utf-8"), headers={})

        configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
        server, thread, port = _run_rest_server()
        try:
            status_login, _, login_raw = _request("GET", f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/")
            assert status_login == 200
            login = json.loads(login_raw)
            captured["nonce"] = login["nonce"]
            status_token, headers_token, body_raw = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/token", {"code": "auth-code", "state": login["state"]})
            assert status_token == 200
            body = json.loads(body_raw)
            # Tokens stay server-side; the BFF response gives only the cookie + CSRF token + actor info.
            assert "access_token" not in body
            assert "refresh_token" not in body
            assert "id_token" not in body
            assert body["authenticated"] is True
            assert body["csrf_token"]
            assert body["actor_snapshot"]["subject"] == "iaf-bound-user"
            set_cookie = headers_token.get("set-cookie") or ""
            assert "zw_brain_session=" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "SameSite=Lax" in set_cookie
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None, jwks=None)


@pytest.mark.parametrize(
    ("token_override", "expected_status", "expected_detail"),
    [
        ({"nonce": "bad"}, 400, "nonce mismatch"),
        ({"aud": ["other-client"]}, 401, "audience mismatch"),
        ({"signature": "bad"}, 401, "jwt verification failed"),
        ({"unsigned": True}, 401, "unsupported jwt algorithm"),
    ],
)
def test_iaf_oidc_rest_token_fails_closed_for_invalid_rs256_boundaries(token_override: dict[str, object], expected_status: int, expected_detail: str) -> None:
    with TemporaryDirectory() as tmp:
        _new_database_service(tmp)
        good_keys = _KeyFixture(kid="same-kid")
        bad_keys = _KeyFixture(kid="same-kid")
        captured: dict[str, Any] = {}

        def transport(request: HttpRequest) -> HttpResponse:
            if request.method == "POST":
                claims = _valid_claims(nonce=captured["nonce"])
                claims.update({k: v for k, v in token_override.items() if k not in {"signature", "unsigned"}})
                if token_override.get("unsigned"):
                    token = jwt.encode(claims, key=None, algorithm="none", headers={"typ": "JWT"})
                elif token_override.get("signature") == "bad":
                    token = bad_keys.encode(claims)
                else:
                    token = good_keys.encode(claims)
                return HttpResponse(status_code=200, body=json.dumps({"access_token": token, "refresh_token": "refresh-1", "id_token": token, "token_type": "Bearer", "expires_in": 300}).encode("utf-8"), headers={})
            return HttpResponse(status_code=200, body=json.dumps(good_keys.jwks).encode("utf-8"), headers={})

        configure_iaf_auth_runtime(transport=transport, jwks=good_keys.jwks)
        server, thread, port = _run_rest_server()
        try:
            status, login = _request_json("GET", f"http://127.0.0.1:{port}/auth/iaf/login?format=json")
            assert status == 200
            captured["nonce"] = login["nonce"]

            status, callback = _request_json("POST", f"http://127.0.0.1:{port}/auth/iaf/token", {"code": "auth-code", "state": login["state"]})
            assert status == expected_status
            assert callback["detail"] == expected_detail
            _assert_no_secrets(callback)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None, jwks=None)


def test_iaf_oidc_rest_token_rejects_bad_state_and_legacy_auth_routes() -> None:
    with TemporaryDirectory() as tmp:
        _new_database_service(tmp)
        configure_iaf_auth_runtime(transport=lambda _request: HttpResponse(status_code=500, body=b"{}", headers={}), jwks={"keys": []})
        server, thread, port = _run_rest_server()
        try:
            status, bad_state = _request_json("POST", f"http://127.0.0.1:{port}/auth/iaf/token", {"code": "auth-code", "state": "bad"})
            assert status == 400
            assert bad_state["detail"] == "state mismatch"
            for route in ["/login", "/oauth2Login", "/SAML2/login", "/cas/login"]:
                status, body = _request_json("GET", f"http://127.0.0.1:{port}{route}")
                assert status == 404
                assert body["error"] == "not_found"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None, jwks=None)
