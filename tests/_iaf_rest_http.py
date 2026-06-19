"""Shared HTTP helpers for mock-IAF REST integration tests."""

from __future__ import annotations

import http.client
import json
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Thread
from typing import Any
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import zw_brain.command.runtime as runtime
from zw_brain.command.brain import BrainService
from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer, configure_iaf_auth_runtime
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.auth_session import SESSION_COOKIE_NAME
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

_IAF_ENV_KEYS = (
    "ZW_BRAIN_IAF_AUTH_SERVER_URL",
    "ZW_BRAIN_IAF_ISSUER",
    "ZW_BRAIN_IAF_AUDIENCE",
    "ZW_BRAIN_IAF_CLIENT_ID",
    "ZW_BRAIN_DEV_IAM_BYPASS",
    "ZW_BRAIN_DEV_IAM_BYPASS_ACK",
)


class KeyFixture:
    def __init__(self, kid: str = "trusted-ctx-key") -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}
        self.kid = kid

    def encode(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid, "typ": "JWT"})


def valid_claims(nonce: str) -> dict[str, Any]:
    return {
        "sub": "trusted-user",
        "iss": "https://iaf.example/auth/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "nonce": nonce,
        "preferred_username": "trusted_user",
        "project_id": "sd-default",
        "org_code": "ORG-A",
        "realm_access": {"roles": ["ROLE_ORGAN_OPERATER"]},
        "resource_access": {"zw-brain": {"roles": ["ROLE_ORGAN_OPERATER"]}},
    }


@contextmanager
def bootstrap_iaf_runtime(tmp: str) -> Iterator[None]:
    # DB 供给由根 conftest 的 _isolate_db_env fixture 集中负责：每个测试已被指向一个
    # 独立的 per-test PostgreSQL 克隆库（ZW_BRAIN_DATABASE_URL）。这里不再写
    # ZW_BRAIN_DB_PATH（PG-only 下该变量已失效），只在那条已配置好的克隆库上拉起
    # runtime + audit sink。测试进程与后台 REST 线程共用同一 PG 库，committed 写跨连接
    # 天然可见（比旧的 SQLite 临时文件更稳，无文件句柄/WAL 可见性问题）。
    # 仍不用 monkeypatch（调用方未走 pytest fixture），在出口手工还原 IAF env / runtime
    # / engine cache。tmp 参数保留以兼容既有调用点（PG 下不再用于选库）。
    saved_env = {key: os.environ.get(key) for key in _IAF_ENV_KEYS}
    saved_service = runtime._service
    os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
    os.environ["ZW_BRAIN_IAF_ISSUER"] = "https://iaf.example/auth/realms/picp"
    os.environ["ZW_BRAIN_IAF_AUDIENCE"] = "zw-brain"
    os.environ["ZW_BRAIN_IAF_CLIENT_ID"] = "zw-brain"
    os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS", None)
    os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)
    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    try:
        ensure_runtime_schema()
        database_store = DatabaseStore()
        audit_bus.configure_sink(database_store.append_audit_event)
        runtime._service = BrainService(state_store=StateStore(database_store=database_store))
        yield
    finally:
        runtime._service = saved_service
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_server() -> tuple[ThreadingRestServer, Thread, int]:
    port = free_port()
    server = ThreadingRestServer(("127.0.0.1", port), RestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def http_request(
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
        try:
            body_parsed: dict[str, Any] | str = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body_parsed = raw
        return response.status, resp_headers, body_parsed
    finally:
        conn.close()


def extract_cookie(set_cookie: str, name: str) -> str:
    for chunk in set_cookie.split(","):
        for part in chunk.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part.split("=", 1)[1]
    return ""


def cookie_cleared(set_cookie: str, name: str) -> bool:
    lowered = set_cookie.lower()
    return f"{name.lower()}=" in lowered and "max-age=0" in lowered


def seed_identity_bindings(
    sub: str, roles: list[str], *, org_code: str = "ORG-A", tenant_id: str = "sd-default"
) -> None:
    """D62 A2: product roles are zw-brain's authoritative actor_org_role_binding, NOT the IAM
    token. So a test identity that "holds role X" must hold it as a BINDING. This seeds an
    active actor + (org, role) bindings for the given sub so the binding-authoritative bearer
    and cookie gates grant exactly those roles. (The minted token still carries the same roles
    for signature/identity, but they are ignored for product authz.)"""
    from zw_brain.domain.policy import filter_product_role_codes
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository

    repo = GovernanceProjectionRepository()
    repo.upsert_actor(
        {
            "external_actor_id": sub,
            "display_name": sub,
            "org_code": org_code,
            "role_codes": [],
            "status": "active",
            "source_ref": "iaf:claims",
            "profile_json": {"iaf_sub": sub},
        },
        tenant_id=tenant_id,
    )
    for role_code in filter_product_role_codes(list(roles)):
        repo.assign_actor_role(
            external_actor_id=sub, org_code=org_code, role_code=role_code,
            tenant_id=tenant_id, granted_by="test-harness",
        )


def establish_session(port: int, keys: KeyFixture, *, extra_roles: list[str] | None = None) -> tuple[str, str]:
    status, _, login_body = http_request(
        "GET",
        f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/",
    )
    assert status == 200
    nonce = login_body["nonce"]  # type: ignore[index]
    state = login_body["state"]  # type: ignore[index]

    def transport(request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            claims = valid_claims(nonce=nonce)
            if extra_roles:
                claims["resource_access"]["zw-brain"]["roles"] = extra_roles
            token = keys.encode(claims)
            return HttpResponse(
                status_code=200,
                body=json.dumps(
                    {
                        "access_token": token,
                        "refresh_token": "rt-fixture",
                        "id_token": token,
                        "expires_in": 300,
                        "refresh_expires_in": 3600,
                    }
                ).encode(),
                headers={},
            )
        return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode(), headers={})

    configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
    status, headers, body = http_request(
        "POST",
        f"http://127.0.0.1:{port}/auth/iaf/token",
        body={"code": "c", "state": state},
    )
    assert status == 200, body
    session_id = extract_cookie(headers.get("set-cookie", ""), SESSION_COOKIE_NAME)
    # D62 A2: bind the cookie identity's product roles as authoritative bindings (the token
    # roles are identity-only now). Re-enrich on the next skill call picks these up.
    seed_identity_bindings("trusted-user", extra_roles or ["ROLE_ORGAN_OPERATER"])
    return session_id, body["csrf_token"]  # type: ignore[index]


def mint_bearer(keys: KeyFixture, *, roles: list[str], sub: str = "bearer-user") -> str:
    """Mint a standalone RS256 access token (no cookie session) for the Bearer path.

    Wires the IAF runtime transport to serve this fixture's JWKS so the server's
    per-request RS256 verification (Path 3 in `_with_authenticated_request`) succeeds.
    Used by C1 tests to exercise the no-cookie bearer surface with a chosen role set.
    """
    def transport(request: HttpRequest) -> HttpResponse:
        # Bearer path only needs JWKS for signature verification (no token endpoint).
        return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode(), headers={})

    configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
    claims = {
        "sub": sub,
        "iss": "https://iaf.example/auth/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "preferred_username": sub,
        "project_id": "sd-default",
        "org_code": "ORG-A",
        "realm_access": {"roles": list(roles)},
        "resource_access": {"zw-brain": {"roles": list(roles)}},
    }
    # D62 A2: the bearer identity "holds" its roles as authoritative bindings, not via the
    # token. Seed them so the binding-based bearer gate grants exactly these product roles.
    seed_identity_bindings(sub, list(roles))
    return keys.encode(claims)


def stop_server(server: ThreadingRestServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
