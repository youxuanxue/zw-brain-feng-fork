"""A2A over-socket wire-test helpers — 起真实 _A2AHandler daemon 跑端到端线级测试。

镜像 tests/_iaf_rest_http.py：ephemeral port + ThreadingHTTPServer + http.client 真请求。
补 A2A（5 消费面之一）此前零 over-socket 覆盖（唯一测试走进程内 invoke()）。
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from http.server import ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import urlparse

from zw_brain.entry.a2a.server import _A2AHandler, _build_binding_index


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_a2a_server() -> tuple[ThreadingHTTPServer, Thread, int]:
    """起 A2A daemon（与 serve_http 同构：装 binding_index + log_file）。"""
    port = free_port()
    _A2AHandler.binding_index = _build_binding_index()
    server = ThreadingHTTPServer(("127.0.0.1", port), _A2AHandler)
    # handler.log_message 写 server.log_file —— serve_http 里设的，线级测试须同样设否则每请求崩。
    server.log_file = open(os.devnull, "w", encoding="utf-8")  # type: ignore[attr-defined]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def a2a_request(
    method: str, url: str, *, body: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | str]:
    parsed = urlparse(url)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80, timeout=10)
    try:
        path = parsed.path or "/"
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        try:
            data: dict[str, Any] | str = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = raw
        return resp.status, data
    finally:
        conn.close()


def stop_a2a_server(server: ThreadingHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    try:
        server.log_file.close()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
