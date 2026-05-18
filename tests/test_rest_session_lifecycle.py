from __future__ import annotations

import http.client
import json
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from urllib.parse import urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import zw_brain.command.runtime as runtime
from zw_brain.command.brain import BrainService
from zw_brain.entry.rest.server import (
    RestHandler,
    ThreadingRestServer,
    configure_iaf_auth_runtime,
    get_auth_session_store,
)
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.auth_session import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore


class _KeyFixture:
    def __init__(self, kid: str = "session-test-key") -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}
        self.kid = kid

    def encode(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid, "typ": "JWT"})


def _valid_claims(nonce: str) -> dict[str, Any]:
    return {
        "sub": "session-user",
        "iss": "https://iaf.example/auth/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "nonce": nonce,
        "preferred_username": "session_user",
        "project_id": "sd-default",
        "realm_access": {"roles": ["r7"]},
        "resource_access": {"zw-brain": {"roles": ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]}},
    }


def _bootstrap_runtime(tmp: str) -> None:
    os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
    os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
    os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/auth/realms/picp"
    os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
    os.environ["ZW_BRAIN_IAF_CLIENT_ID"] = "zw-brain"
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    runtime._service = None
    runtime._service = BrainService(state_store=StateStore(database_store=database_store))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server() -> tuple[ThreadingRestServer, Thread, int]:
    port = _free_port()
    server = ThreadingRestServer(("127.0.0.1", port), RestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any] | str]:
    parsed = urlparse(url)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request_headers = {"Accept": "application/json", "Host": parsed.netloc}
    request_headers.update(headers or {})
    if payload is not None and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=5)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request(method, path, body=payload, headers=request_headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        resp_headers = {key.lower(): value for key, value in response.getheaders()}
        body_parsed: dict[str, Any] | str
        try:
            body_parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body_parsed = raw
        return response.status, resp_headers, body_parsed
    finally:
        conn.close()


def _extract_cookie(set_cookie: str, name: str) -> str:
    for chunk in set_cookie.split(","):
        for part in chunk.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part.split("=", 1)[1]
    return ""


def _establish_session(port: int, keys: _KeyFixture) -> tuple[str, str]:
    """Run the OAuth login flow against the running server and return (session_cookie, csrf_token)."""
    status, _, login_body = _request("GET", f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/")
    assert status == 200
    nonce = login_body["nonce"]  # type: ignore[index]
    state = login_body["state"]  # type: ignore[index]

    def transport(request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            token = keys.encode(_valid_claims(nonce=nonce))
            return HttpResponse(
                status_code=200,
                body=json.dumps({"access_token": token, "refresh_token": "refresh-1", "id_token": token, "expires_in": 300, "refresh_expires_in": 3600, "token_type": "Bearer"}).encode("utf-8"),
                headers={},
            )
        return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode("utf-8"), headers={})

    configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
    status, headers, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/token", body={"code": "auth-code", "state": state})
    assert status == 200, body
    set_cookie = headers.get("set-cookie", "")
    session_id = _extract_cookie(set_cookie, SESSION_COOKIE_NAME)
    assert session_id
    return session_id, body["csrf_token"]  # type: ignore[index]


@pytest.fixture(autouse=True)
def _reset_runtime_between_tests():
    yield
    configure_iaf_auth_runtime(transport=None, jwks=None)
    runtime._service = None
    for key in (
        "ZW_BRAIN_DEV_IAM_BYPASS",
        "ZW_BRAIN_DEV_IAM_BYPASS_ACK",
        "ZW_BRAIN_IAF_AUTH_SERVER_URL",
        "ZW_BRAIN_IAF_ISSUER",
        "ZW_BRAIN_IAF_AUDIENCE",
        "ZW_BRAIN_IAF_CLIENT_ID",
    ):
        os.environ.pop(key, None)


def test_token_callback_sets_httponly_cookie_and_omits_tokens_from_body() -> None:
    # Direct assertions on Set-Cookie attributes + the response body — no piggybacking off the
    # cross-file fixture; reviewer should not need to chase another file to confirm the contract.
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            status_login, _, login_raw = _request("GET", f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/")
            assert status_login == 200
            login = login_raw if isinstance(login_raw, dict) else json.loads(login_raw)  # type: ignore[arg-type]
            nonce = login["nonce"]
            state = login["state"]

            def transport(request: HttpRequest) -> HttpResponse:
                if request.method == "POST":
                    token = keys.encode(_valid_claims(nonce=nonce))
                    return HttpResponse(
                        status_code=200,
                        body=json.dumps({"access_token": token, "refresh_token": "refresh-1", "id_token": token, "expires_in": 300, "refresh_expires_in": 3600, "token_type": "Bearer"}).encode("utf-8"),
                        headers={},
                    )
                return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode("utf-8"), headers={})

            configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
            status, headers, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/token", body={"code": "auth-code", "state": state})
            assert status == 200, body
            assert isinstance(body, dict)
            # Body MUST omit all three IAM tokens.
            assert "access_token" not in body
            assert "refresh_token" not in body
            assert "id_token" not in body
            assert body["authenticated"] is True
            assert body["csrf_token"]
            # Set-Cookie MUST carry the session id with HttpOnly and SameSite=Lax.
            set_cookie = headers.get("set-cookie", "")
            assert f"{SESSION_COOKIE_NAME}=" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "SameSite=Lax" in set_cookie
            assert "Path=/" in set_cookie
            assert "Max-Age=" in set_cookie
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_cookie_session_authenticates_snapshot() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, _ = _establish_session(port, keys)
            status, _, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=r1",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_missing_cookie_returns_401_when_no_bearer() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        configure_iaf_auth_runtime(transport=lambda request: HttpResponse(status_code=401, body=b"{}", headers={}))
        server, thread, port = _run_server()
        try:
            status, _, _ = _request("GET", f"http://127.0.0.1:{port}/api/snapshot?role=r1")
            assert status in (400, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_post_without_csrf_token_returns_403() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, _csrf = _establish_session(port, keys)
            # Deliberately omit the CSRF header on a cookie-authenticated POST.
            status, _, body = _request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body={"role": "r1"},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "csrf_token_invalid"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_post_with_wrong_csrf_returns_403() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, _csrf = _establish_session(port, keys)
            status, _, body = _request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body={"role": "r1"},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}", CSRF_HEADER_NAME: "totally-wrong"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "csrf_token_invalid"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_logout_clears_session_and_cookie() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, _ = _establish_session(port, keys)
            assert get_auth_session_store().get(session_cookie) is not None
            status, headers, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri=http://127.0.0.1:{port}/",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
            )
            assert status == 200
            assert isinstance(body, dict) and body["local_auth_cleared"] is True
            set_cookie = headers.get("set-cookie", "")
            assert "Max-Age=0" in set_cookie
            assert get_auth_session_store().get(session_cookie) is None
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_logout_uses_session_id_token_hint_when_cookie_present() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, _ = _establish_session(port, keys)
            session = get_auth_session_store().get(session_cookie)
            assert session is not None and session.id_token
            status, _, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri=http://127.0.0.1:{port}/",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
            )
            assert status == 200
            # The logout_url must carry id_token_hint pulled from the session, not from the query string.
            assert isinstance(body, dict)
            assert "id_token_hint=" in body["logout_url"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_bearer_fallback_still_works_for_direct_api_clients() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        access_token = keys.encode(_valid_claims(nonce="bearer-test"))

        def transport(request: HttpRequest) -> HttpResponse:
            if request.url.endswith("/v1/token-healthz") and request.headers.get("Authorization") == f"Bearer {access_token}":
                return HttpResponse(status_code=200, body=b"{}", headers={})
            if request.url.endswith("/protocol/openid-connect/certs"):
                return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode("utf-8"), headers={})
            return HttpResponse(status_code=401, body=b"{}", headers={})

        configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
        server, thread, port = _run_server()
        try:
            status, _, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=r1",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_dev_bypass_login_creates_session_when_bypass_enabled() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS"] = "1"
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS_ACK"] = "development-only"
        server, thread, port = _run_server()
        try:
            status, headers, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/dev-bypass-login")
            assert status == 200, body
            assert isinstance(body, dict)
            assert body["development_iam_bypass"] is True
            assert body["csrf_token"]
            set_cookie = headers.get("set-cookie", "")
            assert "zw_brain_session=" in set_cookie
            assert "HttpOnly" in set_cookie
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_dev_bypass_login_rejected_when_bypass_disabled() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        # No ZW_BRAIN_DEV_IAM_BYPASS set → bypass disabled.
        server, thread, port = _run_server()
        try:
            status, _, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/dev-bypass-login")
            assert status == 404
            assert isinstance(body, dict) and body["error"] == "not_found"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_session_endpoint_returns_public_payload_when_cookie_present() -> None:
    # R-001 fix: a new tab with the BFF cookie but empty sessionStorage must be able to recover
    # csrf_token from /auth/iaf/session without creating a duplicate server session.
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, csrf = _establish_session(port, keys)
            store_before = get_auth_session_store().get(session_cookie)
            assert store_before is not None
            status, _, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/session",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
            )
            assert status == 200
            assert isinstance(body, dict)
            assert body["authenticated"] is True
            assert body["csrf_token"] == csrf
            # The endpoint is side-effect-free: same cookie still resolves to the same session.
            assert get_auth_session_store().get(session_cookie) is store_before
            assert "access_token" not in body
            assert "refresh_token" not in body
            assert "id_token" not in body
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_session_endpoint_returns_401_without_cookie() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        server, thread, port = _run_server()
        try:
            status, _, body = _request("GET", f"http://127.0.0.1:{port}/auth/iaf/session")
            assert status == 401
            assert isinstance(body, dict) and body["error"] == "session_missing"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_session_endpoint_returns_401_for_unknown_cookie() -> None:
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        server, thread, port = _run_server()
        try:
            status, _, body = _request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/session",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}=does-not-exist"},
            )
            assert status == 401
            assert isinstance(body, dict) and body["error"] == "session_missing"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_dev_bypass_single_factor_still_blocked() -> None:
    # PR #45's R-002 hardening must continue to apply: setting only ZW_BRAIN_DEV_IAM_BYPASS=1 without
    # the _ACK companion must NOT enable bypass even via the new dev-bypass-login endpoint.
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS"] = "1"
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)
        server, thread, port = _run_server()
        try:
            status, _, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/dev-bypass-login")
            assert status == 404
            assert isinstance(body, dict) and body["error"] == "not_found"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
