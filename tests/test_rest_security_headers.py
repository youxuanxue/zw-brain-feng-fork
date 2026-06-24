"""漏扫 0609 Layer 1：REST/A2A HTTP 面去版本化 banner + 安全响应头。

验证 stdlib http.server 不再泄漏 `Python/x.y.z`，且每个响应（含错误页）都带安全头，
HSTS 仅在 HTTPS（X-Forwarded-Proto=https）下出现。
"""
from __future__ import annotations

import http.client
import socket
from threading import Thread

import pytest

from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer
from zw_brain.shared.http_security import SERVER_BANNER, security_headers

# 与请求 scheme 无关、必须始终出现的安全头。
_ALWAYS_ON = (
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Content-Security-Policy",
    "Permissions-Policy",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def rest_server():
    port = _free_port()
    server = ThreadingRestServer(("127.0.0.1", port), RestHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()


# ── 单元：helper 单一事实源 ──────────────────────────────────────────────────

@pytest.mark.no_db
def test_security_headers_hsts_only_on_https() -> None:
    plain = dict(security_headers(is_https=False))
    https = dict(security_headers(is_https=True))
    assert "Strict-Transport-Security" not in plain
    assert https["Strict-Transport-Security"].startswith("max-age=")
    # 始终注入的头在两种场景都在
    for name in _ALWAYS_ON:
        assert name in plain and name in https


@pytest.mark.no_db
def test_csp_is_strict_not_security_theater() -> None:
    """CSP 必须真严格：script-src 'self' 且不含 unsafe-inline/unsafe-eval（否则形同虚设）。"""
    csp = dict(security_headers(is_https=False))["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "'unsafe-eval'" not in csp
    # script-src 段不得掺 'unsafe-inline'（style-src 因 Vue :style 才允许，单独校验）
    script_directive = next(d for d in csp.split(";") if d.strip().startswith("script-src"))
    assert "'unsafe-inline'" not in script_directive


# ── 集成：真实 REST 服务 ─────────────────────────────────────────────────────

@pytest.mark.no_db
def test_server_banner_has_no_python_version(rest_server: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", rest_server, timeout=5)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    resp.read()
    server = resp.getheader("Server")
    assert server == SERVER_BANNER
    assert "Python/" not in (server or "")  # 不泄漏运行时版本


@pytest.mark.no_db
def test_security_headers_present_on_json_response(rest_server: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", rest_server, timeout=5)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    resp.read()
    for name in _ALWAYS_ON:
        assert resp.getheader(name), f"missing {name}"
    # 明文 HTTP 不应发 HSTS
    assert resp.getheader("Strict-Transport-Security") is None


@pytest.mark.no_db
def test_hsts_present_behind_tls_proxy(rest_server: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", rest_server, timeout=5)
    conn.request("GET", "/health", headers={"X-Forwarded-Proto": "https"})
    resp = conn.getresponse()
    resp.read()
    assert resp.getheader("Strict-Transport-Security")


@pytest.mark.no_db
def test_error_responses_are_also_hardened(rest_server: int) -> None:
    """404（及 stdlib 错误页）也必须去版本化 + 带安全头，不能漏网。"""
    conn = http.client.HTTPConnection("127.0.0.1", rest_server, timeout=5)
    conn.request("GET", "/definitely-not-a-route")
    resp = conn.getresponse()
    resp.read()
    assert resp.status == 404
    assert resp.getheader("Server") == SERVER_BANNER
    assert resp.getheader("Content-Security-Policy")


# ── A2A handler 同样去版本化 banner ──────────────────────────────────────────

@pytest.mark.no_db
def test_a2a_handler_suppresses_version_banner() -> None:
    from zw_brain.entry.a2a.server import _A2AHandler

    # version_string 不依赖实例状态，免初始化直接验证 override 生效。
    handler = object.__new__(_A2AHandler)
    assert handler.version_string() == SERVER_BANNER
