from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import create_engine

import zw_brain.command.runtime as runtime
from zw_brain.domain.models import Base
from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer, configure_iaf_auth_runtime
from zw_brain.shared.iaf_oidc import HttpRequest, HttpResponse
from zw_brain.shared.migrate import ensure_runtime_schema

_TEST_KID = "rest-runtime-test-key"
_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PUBLIC_JWK = json.loads(RSAAlgorithm.to_jwk(_TEST_PRIVATE_KEY.public_key()))
_TEST_PUBLIC_JWK.update({"kid": _TEST_KID, "alg": "RS256", "use": "sig"})
_TEST_JWKS = {"keys": [_TEST_PUBLIC_JWK]}


def _build_test_access_token(**overrides: Any) -> str:
    claims = {
        "iss": "https://iaf.example/auth/realms/picp",
        "aud": ["zw-brain"],
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
        "sub": "rest-test-user",
        "preferred_username": "rest_test",
        "project_id": "sd-default",
        "realm_access": {"roles": ["ROLE_BUSIAUDIT"]},
        "resource_access": {"zw-brain": {"roles": ["ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_ORGAN_OPERATER", "ROLE_ORGAN_OPERATER", "ROLE_ORGAN_MANAGER", "ROLE_ORGAN_MANAGER", "ROLE_BUSIAUDIT", "ROLE_SECURITY_AUDIT"]}},
    }
    claims.update(overrides)
    return jwt.encode(claims, _TEST_PRIVATE_KEY, algorithm="RS256", headers={"kid": _TEST_KID, "typ": "JWT"})


_API_TOKEN = f"Bearer {_build_test_access_token()}"


def _auth_transport(request: HttpRequest) -> HttpResponse:
    if request.url.endswith("/v1/token-healthz") and request.headers.get("Authorization") == _API_TOKEN:
        return HttpResponse(status_code=200, body=b"{}", headers={})
    if request.url.endswith("/protocol/openid-connect/certs"):
        return HttpResponse(status_code=200, body=json.dumps(_TEST_JWKS).encode("utf-8"), headers={})
    return HttpResponse(status_code=401, body=b"{}", headers={})


def request_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    headers = {"Accept": "application/json"}
    if "/api/" in url:
        headers["Authorization"] = _API_TOKEN
    return request_json_with_headers(method, url, body, headers=headers)


def request_json_with_headers(
    method: str,
    url: str,
    body: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    configure_transport: bool = True,
    development_iam_bypass: bool = False,
) -> tuple[int, dict | str]:
    data = None
    headers = dict(headers or {"Accept": "application/json"})
    if development_iam_bypass:
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS"] = "1"
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS_ACK"] = "development-only"
    elif "/api/" in url:
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS", None)
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)
    if "/api/" in url and not development_iam_bypass:
        os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
        os.environ["ZW_BRAIN_IAF_CLIENT_ID"] = "zw-brain"
        if configure_transport:
            configure_iaf_auth_runtime(transport=_auth_transport)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            if content_type.startswith("application/json"):
                return resp.status, json.loads(raw)
            return resp.status, raw
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def test_rest_runtime_health_survives_slow_client_connection() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        slow_socket = socket.create_connection(("127.0.0.1", port), timeout=2)
        try:
            slow_socket.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n")

            status, health = request_json("GET", f"http://127.0.0.1:{port}/health")

            assert status == 200
            assert health == {"status": "ok", "service": "zw-brain-rest"}
        finally:
            slow_socket.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_api_requires_bearer_and_fails_closed_on_healthz() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
        os.environ["ZW_BRAIN_IAF_CLIENT_ID"] = "zw-brain"
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS", None)
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, missing = request_json_with_headers("GET", f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER", headers={"Accept": "application/json"})
            assert status == 401
            assert missing["error"] == "iaf_token_health_error"

            def unavailable(_request: HttpRequest) -> HttpResponse:
                return HttpResponse(status_code=503, body=b"{}", headers={})

            configure_iaf_auth_runtime(transport=unavailable)
            status, unavailable_body = request_json_with_headers(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Accept": "application/json", "Authorization": _API_TOKEN},
                configure_transport=False,
            )
            assert status == 503
            assert unavailable_body["error"] == "iaf_token_health_error"

            configure_iaf_auth_runtime(transport=_auth_transport)
            status, snapshot = request_json_with_headers(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Accept": "application/json", "Authorization": _API_TOKEN},
            )
            assert status == 200
            assert isinstance(snapshot, dict)
            assert "workbench" in snapshot
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None)



def test_rest_runtime_api_rejects_tampered_jwt_signature_even_when_healthz_passes() -> None:
    # Closes the R-001 gap: business endpoints must locally RS256-verify the access token. A lenient
    # healthz endpoint alone can return 200 for an attacker-crafted token, so we assert that the
    # server rejects (401) when the signature is wrong even though healthz accepted the bearer.
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ["ZW_BRAIN_IAF_AUTH_SERVER_URL"] = "https://iaf.example/auth"
        os.environ["ZW_BRAIN_IAF_CLIENT_ID"] = "zw-brain"
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS", None)
        os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tampered_claims = {
            "iss": "https://iaf.example/auth/realms/picp",
            "aud": ["zw-brain"],
            "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
            "sub": "attacker",
            "preferred_username": "attacker",
            "project_id": "sd-default",
            "resource_access": {"zw-brain": {"roles": ["ROLE_BUSIAUDIT"]}},
        }
        tampered_token = jwt.encode(tampered_claims, attacker_key, algorithm="RS256", headers={"kid": _TEST_KID, "typ": "JWT"})
        bearer = f"Bearer {tampered_token}"

        def lenient_transport(request: HttpRequest) -> HttpResponse:
            if request.url.endswith("/v1/token-healthz"):
                return HttpResponse(status_code=200, body=b"{}", headers={})
            if request.url.endswith("/protocol/openid-connect/certs"):
                return HttpResponse(status_code=200, body=json.dumps(_TEST_JWKS).encode("utf-8"), headers={})
            return HttpResponse(status_code=404, body=b"{}", headers={})

        configure_iaf_auth_runtime(transport=lenient_transport)
        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = request_json_with_headers(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Accept": "application/json", "Authorization": bearer},
                configure_transport=False,
            )
            assert status == 401, f"expected 401 for tampered signature, got {status} {body!r}"
            assert body["error"] == "iaf_auth_error"
            assert "jwt verification failed" in body["detail"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None)


def test_rest_runtime_dev_iam_bypass_allows_api_without_iaf_or_bearer() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        os.environ.pop("ZW_BRAIN_IAF_AUTH_SERVER_URL", None)
        os.environ.pop("ZW_BRAIN_IAF_CLIENT_ID", None)
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS"] = "1"
        os.environ["ZW_BRAIN_DEV_IAM_BYPASS_ACK"] = "development-only"
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)
        transport_called = False

        def fail_if_called(_request: HttpRequest) -> HttpResponse:
            nonlocal transport_called
            transport_called = True
            return HttpResponse(status_code=503, body=b"{}", headers={})

        configure_iaf_auth_runtime(transport=fail_if_called)
        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, auth_config = request_json_with_headers("GET", f"http://127.0.0.1:{port}/auth/iaf/config", headers={"Accept": "application/json"})
            assert status == 200
            assert auth_config["configured"] is False
            assert auth_config["development_iam_bypass_enabled"] is True
            # Frontend now reads the synthetic identity from the server, not from a local hardcoded list.
            bypass_user = auth_config["development_iam_bypass_user"]
            assert bypass_user["subject"] == "dev-iam-bypass"
            assert bypass_user["username"] == "dev_iam_bypass"
            # 2026-05-19 retrofit：bypass 角色对齐 role_codes.ALL_ROLE_CODES（6 业务角色 + admin + system）
            from zw_brain.domain import role_codes
            assert set(bypass_user["role_codes"]) == set(role_codes.ALL_ROLE_CODES)

            status, snapshot = request_json_with_headers(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Accept": "application/json"},
                development_iam_bypass=True,
            )
            assert status == 200
            assert isinstance(snapshot, dict)
            assert snapshot["webui"]["iafIam"]["developmentBypassEnabled"] is True

            status, logout = request_json_with_headers("GET", f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri=/", headers={"Accept": "application/json"})
            assert status == 200
            assert logout["logout_url"] == f"http://127.0.0.1:{port}/"
            assert logout["local_auth_cleared"] is True
            assert transport_called is False
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            configure_iaf_auth_runtime(transport=None)
            os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS", None)
            os.environ.pop("ZW_BRAIN_DEV_IAM_BYPASS_ACK", None)


def test_rest_runtime_exposes_openapi_and_capability_endpoints() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, health = request_json("GET", f"http://127.0.0.1:{port}/health")
            assert status == 200
            assert health == {"status": "ok", "service": "zw-brain-rest"}

            with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/openapi.json") as resp:
                assert resp.status == 200
                openapi = json.loads(resp.read().decode("utf-8"))
            assert "/api/skills/request.create" in openapi["paths"]
            assert "/api/skills/data.search" in openapi["paths"]

            status, result = request_json(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/data.search?query=%E6%B3%95%E4%BA%BA&page=1&role=ROLE_ORGAN_OPERATER",
            )
            assert status == 200
            assert result["results"]

            status, confirmation = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {"resource_id": "res-market-activity", "role": "ROLE_ORGAN_OPERATER", "confirmed": False},
            )
            assert status == 409
            assert confirmation["error"] == "confirmation_required"
            assert confirmation["skill_id"] == "request.create"

            status, created = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {
                    "resource_id": "res-market-activity",
                    "query": "我要发起市场主体活跃度复用申请",
                    "role": "ROLE_ORGAN_OPERATER",
                    "confirmed": True,
                },
            )
            assert status == 200
            request_id = created["result"]["request_id"]

            status, request_view = request_json(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/request.view?request_id={request_id}&role=ROLE_ORGAN_OPERATER",
            )
            assert status == 200
            assert request_view["id"] == request_id
            assert request_view["status"] == "pending"

            status, duplicate = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/request.create",
                {"resource_id": "res-market-activity", "role": "ROLE_ORGAN_OPERATER", "confirmed": True},
            )
            assert status == 409
            assert duplicate["error"] == "invalid_state"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_webui_canonical_catalog_metadata_actions_execute() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, request_created = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/application.resource.submit",
                {
                    "resource_id": "res-market-activity",
                    "query": "我要发起市场主体活跃度复用申请",
                    "role": "ROLE_ORGAN_OPERATER",
                    "confirmed": True,
                },
            )
            assert status == 200
            assert request_created["result"]["status"] == "pending"

            status, catalog_published = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/catalog.entry.publish",
                {"catalog_code": "cat-business", "role": "ROLE_BUSIAUDIT", "confirmed": True},
            )
            assert status == 200
            assert catalog_published["result"]["lifecycle_status"] == "active"

            status, resource_published = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/resource.asset.publish",
                {"resource_code": "res-company-visit", "role": "ROLE_BUSIAUDIT", "confirmed": True},
            )
            assert status == 200
            assert resource_published["result"]["lifecycle_status"] == "active"

            status, grant = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/delivery.access.grant",
                {"task_id": "DLV-2026-04-24-0008", "role": "ROLE_ORGAN_MANAGER", "confirmed": True},
            )
            assert status == 200
            assert grant["result"]["status"] == "completed"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_returns_422_for_missing_domain_entity() -> None:
    """Business missing refs use HTTP 422 (entity_not_found), distinct from route 404."""
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/application.resource.submit",
                {"resource_id": "does-not-exist-anywhere", "role": "ROLE_ORGAN_OPERATER", "confirmed": True},
            )
            assert status == 422
            assert body["error"] == "entity_not_found"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_get_skill_returns_422_for_missing_domain_entity() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, body = request_json(
                "GET",
                f"http://127.0.0.1:{port}/api/skills/request.view?request_id=REQ-never-exists&role=ROLE_ORGAN_OPERATER",
            )
            assert status == 422
            assert body["error"] == "entity_not_found"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_serves_main_webui_shell_and_enforces_access_denied() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        server = ThreadingRestServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, html = request_json("GET", f"http://127.0.0.1:{port}/index.html")
            assert status == 200
            assert "<title>政务数据大脑</title>" in html
            assert 'class="gov-logo-mark"' in html
            assert "<svg" in html and "zwLogoGrad" in html
            assert "/assets/zw-brain-mark.svg" in html
            assert "<div id=\"app\"" in html
            assert "政务客户交付态" not in html
            assert "8 个主应用页面 + 1 个独立只读大屏" not in html

            status, denied = request_json(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/approval.review_decide",
                {"request_id": "REQ-2026-04-25-0011", "decision": "approve", "role": "ROLE_ORGAN_OPERATER", "confirmed": True},
            )
            assert status == 403
            assert denied["error"] == "access_denied"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None


def test_rest_runtime_serves_product_mark_svg() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "zw_brain.db"
        os.environ["ZW_BRAIN_DB_PATH"] = str(db_path)
        runtime._service = None
        ensure_runtime_schema()
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(bind=engine)

        from http.server import HTTPServer
        from threading import Thread

        server = HTTPServer(("127.0.0.1", 0), RestHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            opener = build_opener(ProxyHandler({}))
            req = Request(f"http://127.0.0.1:{port}/assets/zw-brain-mark.svg", method="GET")
            with opener.open(req) as resp:
                assert resp.status == 200
                assert "image/svg+xml" in resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8")
            assert "<svg" in body
            assert "zwLogoGrad" in body
            assert "#006be6" in body
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
