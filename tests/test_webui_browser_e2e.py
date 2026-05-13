from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from http.server import HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

import pytest

import zw_brain.command.runtime as runtime
from tests.test_legacy_migration_batch import _write_core_dumps
from tests.test_rest_runtime import request_json
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_acceptance_migration
from zw_brain.command.runtime import reset_service
from zw_brain.entry.rest.server import RestHandler

CHROME_APP = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@dataclass
class BrowserE2E:
    process: subprocess.Popen[bytes]
    user_data_dir: tempfile.TemporaryDirectory[str]
    websocket: socket.socket
    request_id: int = 0

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_id += 1
        payload = {"id": self.request_id, "method": method}
        if params is not None:
            payload["params"] = params
        _send_ws_message(self.websocket, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        deadline = time.time() + 10
        while time.time() < deadline:
            message = _read_ws_message(self.websocket)
            if message.get("id") == self.request_id:
                if "error" in message:
                    raise AssertionError(message["error"])
                return message.get("result", {})
        raise TimeoutError(method)

    def eval(self, expression: str, *, await_promise: bool = False) -> Any:
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        value = result["result"]
        if value.get("subtype") == "error":
            raise AssertionError(value.get("description") or value.get("value"))
        return value.get("value")

    def close(self) -> None:
        try:
            self.websocket.close()
        finally:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.user_data_dir.cleanup()


def _chrome_binary() -> str | None:
    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    if CHROME_APP.exists():
        return str(CHROME_APP)
    return None


def _send_ws_message(sock: socket.socket, payload: bytes) -> None:
    mask = os.urandom(4)
    masked_payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    length = len(payload)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    elif length < 65536:
        header = bytes([0x81, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([0x81, 0x80 | 127]) + length.to_bytes(8, "big")
    sock.sendall(header + mask + masked_payload)


def _decode_ws_frame(sock: socket.socket) -> bytes:
    first = sock.recv(2)
    if len(first) < 2:
        raise ConnectionError("websocket closed")
    length = first[1] & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    masked = bool(first[1] & 0x80)
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return payload


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    remaining = n
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("websocket closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_ws_message(sock: socket.socket) -> dict[str, Any]:
    while True:
        raw = _decode_ws_frame(sock)
        if raw in {b"", b"\x00"}:
            continue
        return json.loads(raw.decode("utf-8"))


def _websocket_connect(ws_url: str) -> socket.socket:
    assert ws_url.startswith("ws://")
    host_path = ws_url[len("ws://") :]
    host_port, path = host_path.split("/", 1)
    host, port_text = host_port.split(":", 1)
    ws_nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    sock = socket.create_connection((host, int(port_text)), timeout=5)
    request = (
        f"GET /{path} HTTP/1.1\r\n"
        f"Host: {host_port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_nonce}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
    assert response.startswith(b"HTTP/1.1 101"), response.decode("utf-8", "replace")
    return sock


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _open_browser(url: str) -> BrowserE2E:
    chrome = _chrome_binary()
    if chrome is None:
        pytest.skip("Google Chrome/Chromium is not installed")
    debug_port = _free_port()
    user_data_dir = tempfile.TemporaryDirectory()
    process = subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={user_data_dir.name}",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    opener = build_opener(ProxyHandler({}))
    pages_url = f"http://127.0.0.1:{debug_port}/json/list"
    deadline = time.time() + 10
    page: dict[str, Any] | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            user_data_dir.cleanup()
            raise RuntimeError("Chrome exited before DevTools became available")
        try:
            with opener.open(pages_url, timeout=1) as resp:
                pages = json.loads(resp.read().decode("utf-8"))
                page = next((item for item in pages if item.get("type") == "page" and item.get("webSocketDebuggerUrl")), None)
                if page is not None:
                    break
        except URLError:
            time.sleep(0.1)
    if page is None:
        process.terminate()
        user_data_dir.cleanup()
        raise TimeoutError("Chrome page DevTools endpoint did not start")
    ws = _websocket_connect(page["webSocketDebuggerUrl"])
    browser = BrowserE2E(process=process, user_data_dir=user_data_dir, websocket=ws)
    browser.send("Runtime.enable")
    browser.send("Page.enable")
    return browser


def _prepare_imported_offline_db(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dumps_dir = root / "dumps"
    db_path = root / "customer.db"
    _write_core_dumps(dumps_dir)
    report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, strict=True))
    assert report["status"] == "succeeded"
    for entry in dumps_dir.iterdir():
        entry.unlink()
    dumps_dir.rmdir()
    offline_source = root / "legacy-source-offline"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.setenv("ZW_BRAIN_LEGACY_DUMPS_DIR", str(offline_source))
    monkeypatch.setenv("ZW_BRAIN_WEBUI_ALLOW_ROLE_SWITCH", "1")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    reset_service()
    return offline_source


def _start_rest_server() -> tuple[HTTPServer, Thread, str]:
    server = HTTPServer(("127.0.0.1", 0), RestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _wait_for(browser: BrowserE2E, expression: str, timeout: float = 8) -> Any:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = browser.eval(expression, await_promise=True)
        if last:
            return last
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {expression!r}; last={last!r}")


def _click_text(browser: BrowserE2E, text: str) -> None:
    ok = browser.eval(
        f"""
        (() => {{
          const wanted = {json.dumps(text, ensure_ascii=False)};
          const el = [...document.querySelectorAll('button,a')].find(node => node.textContent.trim().includes(wanted));
          if (!el) return false;
          el.click();
          return true;
        }})()
        """
    )
    assert ok, text


def _set_role(browser: BrowserE2E, role: str) -> None:
    ok = browser.eval(
        f"""
        (async () => {{
          const switcher = document.getElementById('role-switch');
          if (!switcher) return false;
          switcher.value = {json.dumps(role)};
          switcher.dispatchEvent(new Event('change', {{ bubbles: true }}));
          await new Promise(resolve => setTimeout(resolve, 250));
          return window.STATE && window.STATE.role === {json.dumps(role)};
        }})()
        """,
        await_promise=True,
    )
    assert ok, role


def _visible_text(browser: BrowserE2E) -> str:
    return browser.eval("document.body.innerText")


def _assert_body_contains(browser: BrowserE2E, *items: str) -> None:
    text = _visible_text(browser)
    for item in items:
        assert item in text


def _get(base_url: str, skill_id: str, **params: object) -> tuple[int, dict | str]:
    return request_json("GET", f"{base_url}/api/skills/{skill_id}?{urlencode(params)}")


def test_customer_main_journey_real_browser_on_imported_offline_db(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        offline_source = _prepare_imported_offline_db(Path(tmp), monkeypatch)
        server, thread, base_url = _start_rest_server()
        browser: BrowserE2E | None = None
        try:
            status, detail = _get(base_url, "catalog.resource_view", resource_id="BASE-POP-001", role="r1")
            assert status == 200
            assert isinstance(detail, dict)
            assert detail["fieldBindingSummary"]["diagnosis"] == "ok"
            assert detail["fieldBindings"][0]["explain"]["source_column"] == "field-name"
            assert not offline_source.exists()

            browser = _open_browser(f"{base_url}/#/p2-discovery/resource/BASE-POP-001")
            _wait_for(browser, "document.body && document.body.innerText.includes('人口基本信息') && document.body.innerText.includes('字段绑定解释')")
            _assert_body_contains(browser, "人口基本信息", "字段绑定解释", "诊断：ok", "field-name", "回放：")

            _click_text(browser, "发起标准复用申请")
            _wait_for(browser, "location.hash.startsWith('#/p3-request-flow/request/') && document.body.innerText.includes('待审批')")
            request_id = browser.eval("location.hash.split('/').pop()")
            assert request_id.startswith("REQ-")
            task_id = request_id.replace("REQ-", "DLV-", 1)
            _assert_body_contains(browser, request_id, "状态时间线", "审计编号")

            _set_role(browser, "r2")
            browser.eval(f"location.hash = '#/p3-request-flow/review/{request_id}'")
            _wait_for(browser, "document.body.innerText.includes('通过并下发补录')")
            _click_text(browser, "通过并下发补录")
            _wait_for(browser, "document.body.innerText.includes('待补录')")
            _assert_body_contains(browser, "待补录", "准入判断")

            _set_role(browser, "r3")
            browser.eval(f"location.hash = '#/p3-request-flow/request/{request_id}'")
            _wait_for(browser, "document.body.innerText.includes('提交差异补录')")
            _click_text(browser, "提交差异补录")
            _wait_for(browser, "document.body.innerText.includes('待汇总确认')")
            _assert_body_contains(browser, "已补录", "待汇总确认")

            _set_role(browser, "r5")
            browser.eval(f"location.hash = '#/p3-request-flow/review/{request_id}'")
            _wait_for(browser, "document.body.innerText.includes('确认自动汇总')")
            _click_text(browser, "确认自动汇总")
            _wait_for(browser, "document.body.innerText.includes('已汇总')")
            _assert_body_contains(browser, "已汇总", "汇总确认动作")

            _set_role(browser, "r6")
            browser.eval(f"location.hash = '#/p4-delivery-exchange/task/{task_id}'")
            _wait_for(browser, "document.body.innerText.includes('对账交付回执')")
            _click_text(browser, "对账交付回执")
            _wait_for(browser, "document.body.innerText.includes('确认回流共享')")
            _click_text(browser, "确认回流共享")
            _wait_for(browser, "document.body.innerText.includes('回流确认已生效') || document.body.innerText.includes('已确认')")
            _assert_body_contains(browser, "交付回执", "已确认", "回流共享说明")

            _set_role(browser, "r8")
            browser.eval("location.hash = '#/p6-compliance-ops'")
            _wait_for(browser, "document.body.innerText.includes('审计回放') && document.body.innerText.includes('application.resource.submit.after')")
            text = _visible_text(browser)
            for marker in [
                "application.resource.submit.after",
                "application.resource.review.after",
                "supplement.submit.after",
                "summary.confirm.after",
                "delivery.reconcile_receipt.after",
                "backflow.confirm.after",
            ]:
                assert marker in text
        finally:
            if browser is not None:
                browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            runtime._service = None
            reset_service()
