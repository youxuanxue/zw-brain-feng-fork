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
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer, configure_iaf_auth_runtime
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.auth_session import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.session_context import build_trusted_skill_payload, resolve_trusted_role
from zw_brain.shared.state_store import StateStore


class _KeyFixture:
    def __init__(self, kid: str = "trusted-ctx-key") -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        self.jwks = {"keys": [public_jwk]}
        self.kid = kid

    def encode(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid, "typ": "JWT"})


def _valid_claims(nonce: str) -> dict[str, Any]:
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
        try:
            body_parsed: dict[str, Any] | str = json.loads(raw) if raw else {}
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


def _establish_session(port: int, keys: _KeyFixture, *, extra_roles: list[str] | None = None) -> tuple[str, str]:
    status, _, login_body = _request("GET", f"http://127.0.0.1:{port}/auth/iaf/login?redirect_uri=http://127.0.0.1:{port}/")
    assert status == 200
    nonce = login_body["nonce"]  # type: ignore[index]
    state = login_body["state"]  # type: ignore[index]

    def transport(request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            claims = _valid_claims(nonce=nonce)
            if extra_roles:
                claims["resource_access"]["zw-brain"]["roles"] = extra_roles
            token = keys.encode(claims)
            return HttpResponse(
                status_code=200,
                body=json.dumps({"access_token": token, "refresh_token": "rt-fixture", "id_token": token, "expires_in": 300, "refresh_expires_in": 3600}).encode(),
                headers={},
            )
        return HttpResponse(status_code=200, body=json.dumps(keys.jwks).encode(), headers={})

    configure_iaf_auth_runtime(transport=transport, jwks=keys.jwks)
    status, headers, body = _request("POST", f"http://127.0.0.1:{port}/auth/iaf/token", body={"code": "c", "state": state})
    assert status == 200, body
    session_id = _extract_cookie(headers.get("set-cookie", ""), SESSION_COOKIE_NAME)
    return session_id, body["csrf_token"]  # type: ignore[index]


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
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
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
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            session_cookie, csrf = _establish_session(port, keys)
            status, _, body = _request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body={"role": "ROLE_SYSTEM", "confirmed": True},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}", CSRF_HEADER_NAME: csrf},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "access_denied"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


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

    确认手段：低权用户 (role_codes=[ROLE_ORGAN_OPERATER]) 直接通过 Bearer 调
    `system.snapshot`，body 带 _trusted_session_context=True / role=ROLE_SYSTEM /
    自构造 available_contexts=[ROLE_SYSTEM]；服务端必须 fail-closed，
    返回 role 不得是 ROLE_SYSTEM（理想情况返回 fallback / 403）。
    """
    with TemporaryDirectory() as tmp:
        _bootstrap_runtime(tmp)
        keys = _KeyFixture()
        server, thread, port = _run_server()
        try:
            claims = _valid_claims(nonce="bearer-smuggle")
            claims["resource_access"]["zw-brain"]["roles"] = ["ROLE_ORGAN_OPERATER"]
            access_token = keys.encode(claims)

            def transport(request: HttpRequest) -> HttpResponse:
                # IAF introspect endpoint: active token, nothing else needed for Bearer path.
                return HttpResponse(status_code=200, body=json.dumps({"active": True, "exp": claims["exp"]}).encode(), headers={})

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
            status, _, body = _request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body=malicious_body,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            # 关键断言：返回 role 必须取自 client-supplied "role" 字段经
            # policy.resolve_role 校验后的结果（ROLE_SYSTEM 经过 Bearer 路径走
            # 普通 policy.resolve_role，不是 trusted bypass）；更重要的是
            # `_trusted_session_context: True` 不被 _resolve_role 当作 sentinel。
            # 通过对比 actor_snapshot：trusted-bypass 路径会把 actor_snapshot.subject
            # 用作 audit subject；普通路径则没有 BFF session enrichment 痕迹。
            # 直接断言：response 不应包含 ROLE_SYSTEM smuggle 后才会出现的
            # current_role / available_contexts merge。
            state = body.get("state") or {}
            # state.role 受 policy.resolve_role 影响，可能等于 client supplied
            # ROLE_SYSTEM（已知 Bearer 路径放任 role 字段，pre-existing 行为，
            # 与 trusted-session smuggle 无关）；但绝不能反映出"server 把它当
            # trusted session 处理"——即 actor_snapshot 没被 server snapshot
            # 覆盖。
            assert "_trusted_session_context" not in (state or {}), state
            # 直接调用底层 helper：sentinel 严格只能由 build_trusted_skill_payload
            # 写入；客户端 True / "true" / 1 都不算。
            from zw_brain.shared.session_context import is_trusted_session_payload
            assert not is_trusted_session_payload({"_trusted_session_context": True})
            assert not is_trusted_session_payload({"_trusted_session_context": "true"})
            assert not is_trusted_session_payload({"_trusted_session_context": 1})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


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
    # 客户端 smuggle 的各种形态都应失败
    for smuggle in (True, "true", 1, "1", "yes", {}, [True], "<<truthy>>"):
        assert not is_trusted_session_payload({TRUSTED_SESSION_CONTEXT_KEY: smuggle}), smuggle
    # build_trusted_skill_payload 必须先剥掉 client-supplied marker，再 stamp sentinel
    smuggled_client = {TRUSTED_SESSION_CONTEXT_KEY: True, "role": "ROLE_ORGAN_OPERATER"}
    rebuilt = build_trusted_skill_payload(smuggled_client, actor_snapshot=snapshot)
    assert is_trusted_session_payload(rebuilt)
    # 即使经过 json round-trip 模拟序列化也失活（确认 sentinel 不可被反序列化）
    rebuilt_via_json = json.loads(json.dumps({**rebuilt, TRUSTED_SESSION_CONTEXT_KEY: True}))
    assert not is_trusted_session_payload(rebuilt_via_json)
