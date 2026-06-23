"""REST 静态 WebUI：dist-vite 存在时 8800 应服务生产 bundle，而非 Vite dev 入口."""
from __future__ import annotations

import http.client
import json
import re
import socket
from pathlib import Path
from threading import Thread

import pytest

from zw_brain.entry.rest import server as rest_server
from zw_brain.entry.rest.server import RestHandler, ThreadingRestServer, _web_public_root, _web_root

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "zw-brain-web"
DIST_INDEX = WEB_ROOT / "dist-vite" / "index.html"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(port: int) -> ThreadingRestServer:
    server = ThreadingRestServer(("127.0.0.1", port), RestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.mark.skipif(not DIST_INDEX.is_file(), reason="zw-brain-web/dist-vite missing; run npm run build")
def test_web_public_root_prefers_dist_vite() -> None:
    root = _web_root()
    assert root == WEB_ROOT
    assert _web_public_root(root) == WEB_ROOT / "dist-vite"


@pytest.mark.skipif(not DIST_INDEX.is_file(), reason="zw-brain-web/dist-vite missing; run npm run build")
def test_rest_serves_built_index_and_js_under_prefix() -> None:
    # vite base=/zw-brain/（反代部署前缀）后，built index 引用 /zw-brain/assets/*.js。
    # 规范入口是 /zw-brain/；裸 / 仍服务 index（后端 back-compat）但资产路径已带前缀。
    port = _free_port()
    server = _run_server(port)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/zw-brain/")
        response = conn.getresponse()
        html = response.read().decode("utf-8")
        assert response.status == 200
        assert "/src/main.ts" not in html
        match = re.search(r'src="(/zw-brain/assets/[^"]+\.js)"', html)
        assert match, "built index should reference hashed /zw-brain/assets/*.js"
        js_path = match.group(1)
        conn.request("GET", js_path)
        js_resp = conn.getresponse()
        assert js_resp.status == 200
        assert int(js_resp.getheader("Content-Length", "1")) > 1000
        js_resp.read()
    finally:
        server.shutdown()


def test_health_degraded_503_when_shell_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # 回归：当 SPA shell（index.html）缺失时，/health 必须诚实报 503 + status=degraded +
    # webui:false，而不是旧的 false-green 200/"ok"（import 期 pin 的 WEB_PUBLIC_ROOT 让
    # 健康检查对运行时缺失视而不见）。这里直接打桩 live 探测函数模拟「shell 不可读」。
    monkeypatch.setattr(rest_server, "_webui_index_readable", lambda: False)
    port = _free_port()
    server = _run_server(port)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/health")
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        assert response.status == 503, body
        assert body["status"] == "degraded", body
        assert body["webui"] is False, body
        assert body["service"] == "zw-brain-rest", body
    finally:
        server.shutdown()


def test_router_hash_history_uses_vite_base_prefix() -> None:
    # 反代前缀部署：hash 路由的 base 必须取 import.meta.env.BASE_URL（/zw-brain/），
    # 否则 createWebHashHistory() 退回 '/'，SPA 跳转后丢掉 /zw-brain/ 段
    # （localhost:8800/#/login），真实 nginx 只路由 /zw-brain/* 时裸路径 404。
    router_src = (WEB_ROOT / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    assert "createWebHashHistory(import.meta.env.BASE_URL)" in router_src, (
        "router 必须把 vite BASE_URL 注入 hash history base，禁裸 createWebHashHistory()"
    )


def test_validate_webui_shell_refuses_boot_in_prod_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 启动期 fail-closed 安全分支（R-001 回归）：prod 部署模式下 shell 缺失必须拒启（SystemExit），
    # 不能带着「浏览器白屏」的 404 服务静默上线。
    monkeypatch.setattr(rest_server, "_webui_index_readable", lambda: False)
    monkeypatch.setattr(rest_server, "_is_prod_deploy_mode", lambda: True)
    with pytest.raises(SystemExit):
        rest_server._validate_webui_shell()


def test_validate_webui_shell_logs_but_boots_in_dev_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 非 prod（dev/test/纯 API）：shell 缺失只大声告警、不拒启——API 无 bundle 仍可用。
    monkeypatch.setattr(rest_server, "_webui_index_readable", lambda: False)
    monkeypatch.setattr(rest_server, "_is_prod_deploy_mode", lambda: False)
    rest_server._validate_webui_shell()  # 不抛即通过


def test_validate_webui_shell_noop_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # shell 在位：无论部署模式都静默放行（即便误判 prod 也不应拒启）。
    monkeypatch.setattr(rest_server, "_webui_index_readable", lambda: True)
    monkeypatch.setattr(rest_server, "_is_prod_deploy_mode", lambda: True)
    rest_server._validate_webui_shell()  # 不抛即通过


def test_rest_main_ensures_schema_before_anchor_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class FakeServer:
        def __init__(self, *_args, **_kwargs) -> None:
            events.append("server-init")

        def serve_forever(self) -> None:
            events.append("serve")

        def server_close(self) -> None:
            events.append("close")

    monkeypatch.setattr(rest_server, "setup_logging", lambda _surface: None)
    monkeypatch.setattr(rest_server, "validate_session_store_for_deploy", lambda: None)
    monkeypatch.setattr(rest_server, "get_dev_iam_bypass_enabled", lambda: False)
    monkeypatch.setattr(rest_server, "get_iaf_insecure_tls_enabled", lambda: False)
    monkeypatch.setattr(rest_server, "_validate_webui_shell", lambda: None)
    monkeypatch.setattr(rest_server, "log_iaf_runtime_warnings", lambda: None)
    monkeypatch.setattr(rest_server, "ensure_runtime_schema", lambda: events.append("schema"))
    monkeypatch.setattr(rest_server, "get_rest_host", lambda: "127.0.0.1")
    monkeypatch.setattr(rest_server, "get_rest_port", lambda: 0)
    monkeypatch.setattr(rest_server, "ThreadingRestServer", FakeServer)
    monkeypatch.setattr("zw_brain.background_tasks.start_anchor_worker", lambda: events.append("anchor-start"))
    monkeypatch.setattr("zw_brain.background_tasks.stop_anchor_worker", lambda: events.append("anchor-stop"))

    rest_server.main()

    assert events == ["schema", "anchor-start", "server-init", "serve", "anchor-stop", "close"]
