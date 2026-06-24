"""OpenAPI exposure guard for production deployments."""

from __future__ import annotations

from tempfile import TemporaryDirectory

from tests._iaf_rest_http import KeyFixture, http_request, mint_bearer, run_server, stop_server
from tests._iaf_runtime_cleanup import bootstrap_iaf_runtime_clean


def test_openapi_public_in_non_prod() -> None:
    server, thread, port = run_server()
    try:
        status, _, body = http_request("GET", f"http://127.0.0.1:{port}/openapi.json")
        assert status == 200, body
        assert isinstance(body, dict)
        assert body["openapi"] == "3.1.0"
    finally:
        stop_server(server, thread)


def test_openapi_requires_authentication_in_prod(monkeypatch) -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime_clean(tmp):
        monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "prod")
        server, thread, port = run_server()
        try:
            status, _, body = http_request("GET", f"http://127.0.0.1:{port}/openapi.json")
            assert status == 401, body
        finally:
            stop_server(server, thread)


def test_openapi_requires_platform_operator_in_prod(monkeypatch) -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime_clean(tmp):
        monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "prod")
        keys = KeyFixture()
        token = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"], sub="openapi-non-system")
        server, thread, port = run_server()
        try:
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/openapi.json",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 403, body
            assert isinstance(body, dict)
            assert body["error"] == "platform_operator_required"
        finally:
            stop_server(server, thread)


def test_openapi_allows_platform_operator_in_prod(monkeypatch) -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime_clean(tmp):
        monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "prod")
        keys = KeyFixture()
        token = mint_bearer(keys, roles=["ROLE_SYSTEM"], sub="openapi-system")
        server, thread, port = run_server()
        try:
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/openapi.json",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            assert body["openapi"] == "3.1.0"
        finally:
            stop_server(server, thread)
