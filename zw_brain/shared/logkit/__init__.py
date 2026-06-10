"""Troubleshooting log infrastructure (logkit) — distinct from the audit bus (D4).

Log lines are best-effort observability and may be lost; audit events are the durable
compliance record and must never be replaced by a log call. Nothing in this package
writes to the business database.
"""

from zw_brain.shared.logkit.config import setup_logging
from zw_brain.shared.logkit.context import (
    bind_request_context,
    get_log_actor,
    get_log_entry,
    get_request_id,
    new_request_id,
    reset_request_context,
    set_log_actor,
)
from zw_brain.shared.logkit.redaction import REDACTED, is_sensitive_key, redact

__all__ = [
    "REDACTED",
    "bind_request_context",
    "get_log_actor",
    "get_log_entry",
    "get_request_id",
    "is_sensitive_key",
    "new_request_id",
    "redact",
    "reset_request_context",
    "set_log_actor",
    "setup_logging",
]
