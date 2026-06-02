"""REST 静态 WebUI：dist-vite 存在时 8800 应服务生产 bundle，而非 Vite dev 入口."""
from __future__ import annotations

import http.client
import re
import socket
from pathlib import Path
from threading import Thread

import pytest

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


def test_router_hash_history_uses_vite_base_prefix() -> None:
    # 反代前缀部署：hash 路由的 base 必须取 import.meta.env.BASE_URL（/zw-brain/），
    # 否则 createWebHashHistory() 退回 '/'，SPA 跳转后丢掉 /zw-brain/ 段
    # （localhost:8800/#/login），真实 nginx 只路由 /zw-brain/* 时裸路径 404。
    router_src = (WEB_ROOT / "src" / "router" / "index.ts").read_text(encoding="utf-8")
    assert "createWebHashHistory(import.meta.env.BASE_URL)" in router_src, (
        "router 必须把 vite BASE_URL 注入 hash history base，禁裸 createWebHashHistory()"
    )

