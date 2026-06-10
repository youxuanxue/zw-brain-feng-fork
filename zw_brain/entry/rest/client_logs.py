"""POST /api/client-logs — WebUI 全局错误上报落排障日志（绝不写业务库）.

前端 useErrorReporting.ts 把未捕获异常 / unhandled rejection / Vue errorHandler
捕获的错误投递到这里，经字段白名单 + 截断 + redact 后落 ``zw_brain.client``
logger（与 REST 同进程 → 进 rest.log），用上报体里的 request_id 与服务端日志
串联。端点无鉴权（boot/登录前的失败正是最需要上报的），防刷三件套：体积上限、
进程内滑窗限流、字段白名单截断；最坏情形也只是日志轮转，不会失控。
"""
from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import Any

from zw_brain.shared.logkit import bind_request_context, redact, reset_request_context

_CLIENT_LOGGER = logging.getLogger("zw_brain.client")

MAX_BODY_BYTES = 16 * 1024

# 字段白名单：名字 → 最大长度。白名单之外的字段一律丢弃。
_FIELD_LIMITS: dict[str, int] = {
    "kind": 32,
    "message": 1000,
    "stack": 4000,
    "url": 500,
    "component": 200,
    "request_id": 64,
    "occurred_at": 40,
}
_ALLOWED_KINDS = {"error", "unhandledrejection", "vue"}

_RATE_LOCK = Lock()
_RATE_WINDOW: list[float] = []  # 最近 60s 内已接收上报的时间戳


def _max_per_minute() -> int:
    raw = (os.environ.get("ZW_BRAIN_CLIENT_LOG_MAX_PER_MINUTE") or "").strip()
    try:
        return int(raw) if raw else 60
    except ValueError:
        return 60


def _rate_limited() -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        cutoff = now - 60.0
        _RATE_WINDOW[:] = [t for t in _RATE_WINDOW if t > cutoff]
        if len(_RATE_WINDOW) >= _max_per_minute():
            return True
        _RATE_WINDOW.append(now)
        return False


def reset_client_log_rate_window() -> None:
    """测试钩子：清空滑窗，让限流场景可确定性驱动。"""
    with _RATE_LOCK:
        _RATE_WINDOW.clear()


def handle_client_log_payload(
    raw: bytes, *, remote: str = "", user_agent: str = ""
) -> tuple[int, dict[str, Any]]:
    """校验 + 限流 + redact + 落日志。返回 (status, response_body)。

    内部任何意外失败都吞掉并回 204 —— 错误上报端点自身绝不能成为新的 500 来源
    （否则前端 reporter 上报失败再触发上报，形成回环）。
    """
    try:
        if len(raw) > MAX_BODY_BYTES:
            return 413, {"error": "payload_too_large"}
        try:
            payload = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return 400, {"error": "invalid_json"}
        if not isinstance(payload, dict):
            return 400, {"error": "invalid_json"}
        if _rate_limited():
            return 429, {"error": "rate_limited"}

        fields: dict[str, Any] = {}
        for key, limit in _FIELD_LIMITS.items():
            value = payload.get(key)
            if value is None:
                continue
            text = str(value)
            fields[key] = text if len(text) <= limit else text[:limit] + "...(truncated)"
        kind = fields.get("kind") or "error"
        if kind not in _ALLOWED_KINDS:
            kind = "error"

        # 上报体自带的 request_id 即前端事发时的 API 调用 id —— bind 进日志上下文，
        # 让这行 client_error 与服务端同 id 的 access/capability 行直接 grep 串联。
        tokens = bind_request_context(fields.get("request_id"), entry="client")
        try:
            clean = redact(fields)
            _CLIENT_LOGGER.error(
                "client %s: %s",
                kind,
                clean.get("message", ""),
                extra={
                    "event": "client_error",
                    "kind": kind,
                    "url": clean.get("url", ""),
                    "component": clean.get("component", ""),
                    "client_request_id": clean.get("request_id", ""),
                    "remote": remote,
                    "user_agent": user_agent[:200],
                    "stack": clean.get("stack", ""),
                },
            )
        finally:
            reset_request_context(tokens)
        return 200, {"ok": True}
    except Exception:  # noqa: BLE001 — 上报端点绝不回环 500
        return 204, {}
