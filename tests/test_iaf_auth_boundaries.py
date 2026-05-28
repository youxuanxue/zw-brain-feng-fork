"""REST 行为级 IAM/BFF 边界测试（mock IAF transport）。"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    cookie_cleared,
    establish_session,
    http_request,
    run_server,
    stop_server,
)
from zw_brain.shared.auth_session import CSRF_HEADER_NAME, SESSION_COOKIE_NAME


def test_logout_deletes_server_session_and_clears_cookie() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys)
            redirect = f"http://127.0.0.1:{port}/"
            status, headers, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri={redirect}",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            assert body.get("local_auth_cleared") is True
            set_cookie = headers.get("set-cookie", "")
            assert cookie_cleared(set_cookie, SESSION_COOKIE_NAME)

            status, _, session_body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/session",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 401, session_body
            assert isinstance(session_body, dict) and session_body.get("error") == "session_missing"

            status, _, api_body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 401, api_body
        finally:
            stop_server(server, thread)


def test_logout_returns_iaf_logout_url_when_not_bypass() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys)
            redirect = f"http://127.0.0.1:{port}/"
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri={redirect}",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 200, body
            assert isinstance(body, dict)
            logout_url = str(body.get("logout_url") or "")
            assert "openid-connect/logout" in logout_url
            assert "client_id=zw-brain" in logout_url
        finally:
            stop_server(server, thread)


def test_post_skill_without_csrf_returns_403() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys)
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/api/skills/system.snapshot",
                body={"role": "ROLE_ORGAN_OPERATER", "confirmed": True},
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "csrf_token_invalid"
        finally:
            stop_server(server, thread)


def test_invalid_session_cookie_returns_401_on_api() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        server, thread, port = run_server()
        try:
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/api/snapshot?role=ROLE_ORGAN_OPERATER",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}=nonexistent-session-id"},
            )
            assert status == 401, body
            assert isinstance(body, dict)
            assert body.get("error") in {"iaf_auth_error", "iaf_token_health_error"}
        finally:
            stop_server(server, thread)


def test_refresh_with_invalid_csrf_returns_403() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys)
            status, _, body = http_request(
                "POST",
                f"http://127.0.0.1:{port}/auth/iaf/refresh",
                headers={
                    "Cookie": f"{SESSION_COOKIE_NAME}={session_id}",
                    CSRF_HEADER_NAME: "wrong-csrf-token",
                },
            )
            assert status == 403, body
            assert isinstance(body, dict) and body.get("error") == "csrf_token_invalid"
        finally:
            stop_server(server, thread)


def test_session_get_after_logout_returns_401() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            session_id, _ = establish_session(port, keys)
            redirect = f"http://127.0.0.1:{port}/"
            http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/logout?redirect_uri={redirect}",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/auth/iaf/session",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_id}"},
            )
            assert status == 401, body
            assert isinstance(body, dict) and body.get("error") == "session_missing"
        finally:
            stop_server(server, thread)
