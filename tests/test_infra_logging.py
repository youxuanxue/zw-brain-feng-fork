# Wave: 0
# Journey: Cross (infrastructure)
# Covers: infra-logging
"""infra-logging .feature 验收：结构化排障日志 + request_id 贯穿。

排障日志与审计总线（D4）严格分界：日志可丢、审计不可丢；本套测试同时钉死
「日志层绝不改变控制流」（段 7a：审计失败必须熔断）这条红线。
"""
from __future__ import annotations

import json
import logging
import sys

import pytest

from zw_brain.shared.logkit import (
    REDACTED,
    bind_request_context,
    get_request_id,
    new_request_id,
    redact,
    reset_request_context,
    set_log_actor,
)
from zw_brain.shared.logkit.config import setup_logging
from zw_brain.shared.logkit.formatter import ContextFilter, JsonLineFormatter


@pytest.fixture
def fresh_logger():
    """隔离 zw_brain logger 配置：测后还原 handlers/level/propagate。"""
    logger = logging.getLogger("zw_brain")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    yield logger
    logger.handlers[:] = saved[0]
    logger.setLevel(saved[1])
    logger.propagate = saved[2]


# ── setup_logging ──────────────────────────────────────────────────────────────


def test_setup_logging_idempotent_and_writes_jsonl(tmp_path, monkeypatch, fresh_logger):
    monkeypatch.setenv("ZW_BRAIN_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("ZW_BRAIN_LOG_LEVEL", "INFO")
    setup_logging("rest", force=True)
    handler_count = len(fresh_logger.handlers)
    setup_logging("rest")  # 二次调用不叠 handler
    assert len(fresh_logger.handlers) == handler_count

    tokens = bind_request_context("trace-jsonl-001", entry="rest")
    try:
        logging.getLogger("zw_brain.test").info("hello jsonl", extra={"event": "probe"})
    finally:
        reset_request_context(tokens)

    lines = (tmp_path / "rest.log").read_text(encoding="utf-8").strip().splitlines()
    rows = [json.loads(line) for line in lines]  # 每行必须可解析
    row = next(r for r in rows if r.get("event") == "probe")
    assert row["request_id"] == "trace-jsonl-001"
    assert row["service"] == "rest"
    assert row["entry"] == "rest"
    assert row["level"] == "INFO"
    assert row["message"] == "hello jsonl"


def test_setup_logging_degrades_when_dir_unwritable(tmp_path, monkeypatch, fresh_logger):
    blocked = tmp_path / "occupied"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("ZW_BRAIN_LOG_DIR", str(blocked / "logs"))
    setup_logging("rest", force=True)  # 不抛——降级 console-only
    from logging.handlers import RotatingFileHandler

    assert not any(isinstance(h, RotatingFileHandler) for h in fresh_logger.handlers)


def test_setup_logging_does_not_touch_root_logger(tmp_path, monkeypatch, fresh_logger):
    monkeypatch.setenv("ZW_BRAIN_LOG_DIR", str(tmp_path))
    root_handlers_before = list(logging.getLogger().handlers)
    setup_logging("cli", force=True)
    assert list(logging.getLogger().handlers) == root_handlers_before
    assert fresh_logger.propagate is False


# ── context / formatter ────────────────────────────────────────────────────────


def test_bind_request_context_generates_and_validates():
    tokens = bind_request_context(None, entry="rest")
    try:
        assert get_request_id().startswith("req-")
    finally:
        reset_request_context(tokens)

    # 非法字符（日志/响应头注入向量）→ 拒收并重新生成
    tokens = bind_request_context("bad\nid", entry="rest")
    try:
        assert "\n" not in get_request_id()
        assert get_request_id().startswith("req-")
    finally:
        reset_request_context(tokens)

    # 合法的客户端 id 原样保留
    tokens = bind_request_context("UI-1718000000-abc", entry="rest")
    try:
        assert get_request_id() == "UI-1718000000-abc"
    finally:
        reset_request_context(tokens)
    assert get_request_id() == ""  # reset 后干净（线程复用不串味）


def _format_one(record_factory) -> dict:
    formatter = JsonLineFormatter("rest")
    record = record_factory()
    ContextFilter().filter(record)
    return json.loads(formatter.format(record))


def test_json_formatter_carries_request_id_actor_and_exc():
    tokens = bind_request_context("trace-fmt-001", entry="rest")
    set_log_actor("alice")
    try:
        try:
            raise ValueError("boom for trace")
        except ValueError:
            logger = logging.getLogger("zw_brain.test.fmt")
            exc_info = sys.exc_info()
            row = _format_one(
                lambda: logger.makeRecord(
                    logger.name, logging.ERROR, __file__, 1, "it failed", (), exc_info
                )
            )
    finally:
        reset_request_context(tokens)
    assert row["request_id"] == "trace-fmt-001"
    assert row["actor"] == "alice"
    assert "ValueError: boom for trace" in row["exc"]
    assert "Traceback" in row["exc"]


def test_new_request_id_distinct_from_business_ids():
    rid = new_request_id()
    assert rid.startswith("req-")
    assert not rid.startswith(("REQ-", "AE-"))


def test_human_formatter_folds_newlines_in_message_and_extras():
    """console 一事件一行：message 与 extras（如前端上报的 stack）的换行都必须折叠，
    否则恶意多行文本可在 console 流上伪造日志行（JSON 文件侧由 json.dumps 转义兜底）。"""
    from zw_brain.shared.logkit.formatter import HumanFormatter

    logger = logging.getLogger("zw_brain.test.human")
    record = logger.makeRecord(
        logger.name, logging.ERROR, __file__, 1, "line1\nFORGED 2099-01-01 INFO fake", (), None
    )
    record.stack = "Error: x\n  at forged:1\n  at forged:2"
    out = HumanFormatter().format(record)
    assert "\n" not in out  # 无 exc_info 时整条必须单行
    assert "FORGED" in out and "forged:1" in out  # 内容保留，只折行


# ── redaction 红线 ─────────────────────────────────────────────────────────────


def test_redaction_masks_secret_token_phone_idcard():
    sample = {
        "api_key": "AK-VERY-SECRET",
        "access_token": "tok-123",
        "password": "p@ss",
        "contact_phone": "13800001111",
        "idcard": "370101199001011234",
        "nested": {"client_secret": "s3cret", "items": [{"bank_card": "6222001234567890"}]},
        "plain": "ok",
        "count": 3,
    }
    out = redact(sample)
    assert out["api_key"] == REDACTED
    assert out["access_token"] == REDACTED
    assert out["password"] == REDACTED
    assert out["contact_phone"] == REDACTED
    assert out["idcard"] == REDACTED
    assert out["nested"]["client_secret"] == REDACTED
    assert out["nested"]["items"][0]["bank_card"] == REDACTED
    assert out["plain"] == "ok"
    assert out["count"] == 3
    assert "AK-VERY-SECRET" not in json.dumps(out)


def test_redaction_truncates_and_caps_depth():
    assert redact("x" * 5000, max_str=100).endswith("...(truncated)")
    deep: dict = {"k": "v"}
    for _ in range(10):
        deep = {"child": deep}
    flattened = json.dumps(redact(deep))
    assert "[MAX-DEPTH]" in flattened


# ── REST：X-Request-Id 回显 + access log + 异常堆栈 ────────────────────────────


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def capture_zw_logs():
    """把捕获 handler 挂在 zw_brain logger 上（不依赖 root 传播，与 setup 配置无关）。"""
    logger = logging.getLogger("zw_brain")
    handler = _ListHandler()
    handler.addFilter(ContextFilter())  # 与真实 handler 同款：把 request context 钉上 record
    saved_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler.records
    logger.removeHandler(handler)
    logger.setLevel(saved_level)


@pytest.fixture
def rest_port():
    from tests._iaf_rest_http import run_server, stop_server

    server, thread, port = run_server()
    yield port
    stop_server(server, thread)


def _get(port: int, path: str, headers: dict[str, str] | None = None):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, dict(resp.getheaders()), body
    finally:
        conn.close()


def test_rest_echoes_x_request_id(rest_port):
    status, headers, _ = _get(rest_port, "/health", {"X-Request-Id": "e2e-trace-001"})
    assert status == 200
    assert headers.get("X-Request-Id") == "e2e-trace-001"


def test_rest_generates_request_id_when_absent(rest_port):
    status, headers, _ = _get(rest_port, "/health")
    assert status == 200
    assert headers.get("X-Request-Id", "").startswith("req-")


def test_rest_rejects_header_injection_in_request_id(rest_port):
    # 非法字符不回显客户端原值——服务端重新生成
    status, headers, _ = _get(rest_port, "/health", {"X-Request-Id": "x" * 200})
    assert status == 200
    assert headers.get("X-Request-Id", "").startswith("req-")


def test_rest_access_log_line(rest_port, capture_zw_logs):
    _get(rest_port, "/health", {"X-Request-Id": "e2e-access-001"})
    row = next(
        r
        for r in capture_zw_logs
        if getattr(r, "event", "") == "http_access" and r.request_id == "e2e-access-001"
    )
    assert row.method == "GET"
    assert row.path == "/health"
    assert row.status == 200
    assert isinstance(row.duration_ms, float)
    assert row.log_entry == "rest"


def test_rest_404_access_log_status(rest_port, capture_zw_logs):
    status, _, _ = _get(rest_port, "/no/such/path", {"X-Request-Id": "e2e-404-001"})
    assert status == 404
    row = next(r for r in capture_zw_logs if getattr(r, "request_id", "") == "e2e-404-001")
    assert row.status == 404


def _stub_handler_for_error() -> tuple:
    """构造仅含 _handle_error 依赖面的 RestHandler（不开 socket）。"""
    from zw_brain.entry.rest.server import RestHandler

    handler = RestHandler.__new__(RestHandler)
    handler.command = "POST"
    handler.path = "/api/skills/probe"
    captured: dict = {}
    handler._json = lambda status, body: captured.update(status=status, body=body)
    return handler, captured


def test_handle_error_5xx_logs_stack_response_unchanged(capture_zw_logs):
    handler, captured = _stub_handler_for_error()
    try:
        raise RuntimeError("kaboom-probe")
    except RuntimeError as exc:
        handler._handle_error(exc)
    # 客户端契约不变：与改造前一致的 500 envelope
    assert captured["status"] == 500
    assert captured["body"] == {"error": "RuntimeError", "detail": "kaboom-probe"}
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "unhandled_error")
    assert row.exc_info is not None  # 完整堆栈进日志
    assert "kaboom-probe" in str(row.exc_info[1])


def test_handle_error_expected_rejection_logs_info_no_stack(capture_zw_logs):
    from zw_brain.command.brain import NotFoundError

    handler, captured = _stub_handler_for_error()
    handler._handle_error(NotFoundError("missing thing"))
    assert captured["status"] == 422
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "request_rejected")
    assert row.levelno == logging.INFO
    assert row.exc_info is None
    assert not any(getattr(r, "event", "") == "unhandled_error" for r in capture_zw_logs)


# ── pipeline：capability 调用日志 + 段 7a（日志不改变控制流）──────────────────


def _fake_pctx(skill_id: str = "probe.capability", *, is_write: bool = False):
    from types import SimpleNamespace

    from zw_brain.command.pipeline import PipelineContext

    skill = SimpleNamespace(skill_id=skill_id, role="ROLE_ORGAN_OPERATER", confirmed=False)
    pctx = PipelineContext(skill=skill, payload={}, is_write=is_write)
    pctx.audit_id = "AE-test-0001"
    pctx.actor = "alice"
    return pctx


def test_capability_log_middleware_records_ok(capture_zw_logs):
    from zw_brain.command.pipeline import CapabilityLogMiddleware

    result = CapabilityLogMiddleware()(_fake_pctx(), lambda p: {"ok": True})
    assert result == {"ok": True}
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "capability_call")
    assert row.skill_id == "probe.capability"
    assert row.outcome == "ok"
    assert row.actor == "alice"
    assert row.audit_id == "AE-test-0001"
    assert isinstance(row.duration_ms, float)


def test_capability_log_middleware_logs_error_and_reraises(capture_zw_logs):
    from zw_brain.command.pipeline import CapabilityLogMiddleware

    def boom(_p):
        raise ValueError("handler exploded")

    with pytest.raises(ValueError, match="handler exploded"):  # 原异常类型与消息不变
        CapabilityLogMiddleware()(_fake_pctx(is_write=True), boom)
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "capability_call")
    assert row.outcome == "error:ValueError"
    assert row.is_write is True


def test_audit_failure_still_raises_with_logging_installed(capture_zw_logs):
    """段 7a 回归锚：审计写失败的熔断 raise 穿过日志中间件，绝不被降级成日志。"""
    from zw_brain.command.pipeline import CapabilityLogMiddleware
    from zw_brain.shared.audit import AuditWriteError

    def audit_emit_blows(_p):
        raise AuditWriteError("durable audit sink is down")

    with pytest.raises(AuditWriteError, match="durable audit sink is down"):
        CapabilityLogMiddleware()(_fake_pctx(is_write=True), audit_emit_blows)
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "capability_call")
    assert row.outcome == "error:AuditWriteError"  # 只旁观记录，控制流照常熔断


def test_middleware_order_guard_passes():
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "check_pipeline_middleware_order.py"
    proc = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CapabilityLogMiddleware" in proc.stdout


# ── 前端错误上报端点 /api/client-logs ─────────────────────────────────────────


def _post_client_log(port: int, body: bytes, headers: dict[str, str] | None = None):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(
            "POST",
            "/api/client-logs",
            body=body,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


@pytest.fixture(autouse=False)
def fresh_rate_window():
    from zw_brain.entry.rest.client_logs import reset_client_log_rate_window

    reset_client_log_rate_window()
    yield
    reset_client_log_rate_window()


def test_client_logs_endpoint_writes_log_not_db(rest_port, capture_zw_logs, fresh_rate_window):
    payload = json.dumps(
        {
            "kind": "unhandledrejection",
            "message": "fe-probe boom",
            "stack": "Error: fe-probe boom\n  at App.vue:42",
            "url": "http://127.0.0.1:8800/#/workbench",
            "request_id": "UI-20260610-abc123",
        }
    ).encode("utf-8")
    status, _ = _post_client_log(rest_port, payload)
    assert status == 200
    row = next(r for r in capture_zw_logs if getattr(r, "event", "") == "client_error")
    assert row.kind == "unhandledrejection"
    assert "fe-probe boom" in row.getMessage()
    assert row.request_id == "UI-20260610-abc123"  # 前后端同 id 串联
    assert row.log_entry == "client"

    # 段 25 防线：上报模块不得触碰任何业务库写入口
    import inspect

    import zw_brain.entry.rest.client_logs as client_logs_mod

    source = inspect.getsource(client_logs_mod)
    for forbidden in ("DatabaseStore", "state_store", "sqlalchemy", "shared.db", "sqlite"):
        assert forbidden not in source, f"client_logs must not touch DB: {forbidden}"


def test_client_logs_endpoint_caps_and_rate_limits(rest_port, fresh_rate_window, monkeypatch):
    # 超体积 → 413（不读体直接拒）
    status, _ = _post_client_log(rest_port, b"x" * (17 * 1024))
    assert status == 413
    # 非 dict / 坏 JSON → 400
    status, _ = _post_client_log(rest_port, b"[1,2,3]")
    assert status == 400
    status, _ = _post_client_log(rest_port, b"{not-json")
    assert status == 400
    # 超频 → 429
    monkeypatch.setenv("ZW_BRAIN_CLIENT_LOG_MAX_PER_MINUTE", "2")
    ok = json.dumps({"kind": "error", "message": "m"}).encode("utf-8")
    assert _post_client_log(rest_port, ok)[0] == 200
    assert _post_client_log(rest_port, ok)[0] == 200
    assert _post_client_log(rest_port, ok)[0] == 429


def test_client_logs_redacts_sensitive_fields(rest_port, capture_zw_logs, fresh_rate_window):
    payload = json.dumps(
        {
            "kind": "error",
            "message": "boom",
            "stack": "at line 1",
            "request_id": "UI-redact-001",
            "api_key": "AK-LEAKED-SECRET",  # 白名单外字段直接丢弃
        }
    ).encode("utf-8")
    assert _post_client_log(rest_port, payload)[0] == 200
    row = next(r for r in capture_zw_logs if getattr(r, "request_id", "") == "UI-redact-001")
    formatted = JsonLineFormatter("rest").format(row)
    assert "AK-LEAKED-SECRET" not in formatted
