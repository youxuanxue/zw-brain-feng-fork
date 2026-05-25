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
def test_rest_serves_built_index_and_js_at_root() -> None:
    port = _free_port()
    server = _run_server(port)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        response = conn.getresponse()
        html = response.read().decode("utf-8")
        assert response.status == 200
        assert "/src/main.ts" not in html
        match = re.search(r'src="(/assets/[^"]+\.js)"', html)
        assert match, "built index should reference hashed /assets/*.js"
        js_path = match.group(1)
        conn.request("GET", js_path)
        js_resp = conn.getresponse()
        assert js_resp.status == 200
        assert int(js_resp.getheader("Content-Length", "1")) > 1000
        js_resp.read()
    finally:
        server.shutdown()

