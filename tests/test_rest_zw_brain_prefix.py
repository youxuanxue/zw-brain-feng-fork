"""反代部署前缀（/zw-brain）路由 + OIDC redirect_uri 同源边界回归。

覆盖 PR #184 的核心能力与其安全边界：
- 路由前缀剥离对带/不带前缀均生效，且不误伤 /zw-brainfoo 这类邻接路径；
- 登录 redirect_uri 同源校验精确比对 scheme+host:port，跨 host 与跨 port 都拒绝（开放重定向防护）。
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from tests._iaf_rest_http import (
    bootstrap_iaf_runtime,
    http_request,
    run_server,
    stop_server,
)
from zw_brain.entry.rest.server import _strip_app_prefix


class TestStripAppPrefix:
    def test_strips_prefixed_path(self) -> None:
        assert _strip_app_prefix("/zw-brain/health") == "/health"
        assert _strip_app_prefix("/zw-brain/api/skills/x") == "/api/skills/x"

    def test_bare_prefix_maps_to_root(self) -> None:
        assert _strip_app_prefix("/zw-brain") == "/"

    def test_passthrough_when_unprefixed(self) -> None:
        assert _strip_app_prefix("/health") == "/health"
        assert _strip_app_prefix("/api/skills/x") == "/api/skills/x"

    def test_does_not_misstrip_adjacent_path(self) -> None:
        # /zw-brainfoo 不是 /zw-brain 的子路径，必须原样保留（旧实现会误剥成 'foo'）。
        assert _strip_app_prefix("/zw-brainfoo") == "/zw-brainfoo"


def test_health_routes_with_and_without_prefix() -> None:
    server, thread, port = run_server()
    try:
        for path in ("/health", "/zw-brain/health"):
            status, _, body = http_request("GET", f"http://127.0.0.1:{port}{path}")
            assert status == 200, (path, body)
            assert body["status"] == "ok"  # type: ignore[index]
            assert body["service"] == "zw-brain-rest"  # type: ignore[index]
    finally:
        stop_server(server, thread)


def test_unknown_adjacent_prefix_is_not_routed() -> None:
    server, thread, port = run_server()
    try:
        status, _, _ = http_request("GET", f"http://127.0.0.1:{port}/zw-brainfoo")
        assert status == 404
    finally:
        stop_server(server, thread)


def test_login_accepts_same_origin_redirect() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        server, thread, port = run_server()
        try:
            redirect = f"http://127.0.0.1:{port}/zw-brain/"
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/zw-brain/auth/iaf/login?redirect_uri={redirect}&format=json",
            )
            assert status == 200, body
            assert "authorization_url" in body  # type: ignore[operator]
        finally:
            stop_server(server, thread)


def test_login_rejects_cross_host_redirect() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        server, thread, port = run_server()
        try:
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/zw-brain/auth/iaf/login"
                "?redirect_uri=http://evil.example/zw-brain/&format=json",
            )
            assert status == 400, body
            assert body["error"] == "iaf_state_error"  # type: ignore[index]
        finally:
            stop_server(server, thread)


def test_login_rejects_same_host_cross_port_redirect() -> None:
    # 安全边界：同 host 不同端口属不同 origin，可能是攻击者可控的旁路服务，必须拒绝。
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        server, thread, port = run_server()
        try:
            other_port = port + 1
            status, _, body = http_request(
                "GET",
                f"http://127.0.0.1:{port}/zw-brain/auth/iaf/login"
                f"?redirect_uri=http://127.0.0.1:{other_port}/zw-brain/&format=json",
            )
            assert status == 400, body
            assert body["error"] == "iaf_state_error"  # type: ignore[index]
        finally:
            stop_server(server, thread)
