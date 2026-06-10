from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from zw_brain.shared.logkit.context import get_log_actor, get_log_entry, get_request_id
from zw_brain.shared.logkit.redaction import redact

# Structured fields callers may attach via ``extra=``; anything else on the record stays
# out of the JSON line so ad-hoc attributes cannot leak un-redacted payloads.
EXTRA_FIELDS: tuple[str, ...] = (
    "event",
    "method",
    "path",
    "status",
    "duration_ms",
    "skill_id",
    "is_write",
    "outcome",
    "audit_id",
    "kind",
    "component",
    "url",
    "client_request_id",
    "remote",
    "stack",
    "user_agent",
)


class ContextFilter(logging.Filter):
    """Stamp the request context onto every record so formatters can read it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.log_entry = get_log_entry()
        record.log_actor = get_log_actor()
        return True


class JsonLineFormatter(logging.Formatter):
    """One redacted JSON object per line — the machine-readable (file) format."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service,
            "entry": getattr(record, "log_entry", "") or "",
            "request_id": getattr(record, "request_id", "") or "-",
            "actor": getattr(record, "log_actor", "") or "",
            "message": record.getMessage(),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc"] = "".join(traceback.format_exception(*record.exc_info))
        # json.dumps escapes newlines, so a hostile message cannot forge extra log lines.
        return json.dumps(redact(payload), ensure_ascii=False, default=str)


def _fold(value: object) -> str:
    """One event per console line: fold newlines so hostile text can't forge log lines."""
    return str(value).replace("\r", "").replace("\n", " ⏎ ")


class HumanFormatter(logging.Formatter):
    """Console format for humans; message and extras are newline-folded (injection guard)."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "") or get_request_id() or "-"
        head = (
            f"{self.formatTime(record)} {record.levelname:<7} "
            f"[{request_id}] {record.name} — {_fold(record.getMessage())}"
        )
        extras = " ".join(
            f"{field}={_fold(getattr(record, field))}"
            for field in EXTRA_FIELDS
            if hasattr(record, field)
        )
        if extras:
            head += " | " + extras
        if record.exc_info:
            head += "\n" + self.formatException(record.exc_info)
        return head
