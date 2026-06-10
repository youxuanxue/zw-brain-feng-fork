from __future__ import annotations

import re
from typing import Any

from zw_brain.shared.sanitization import _is_sensitive_json_key

REDACTED = "[REDACTED]"

# PII key-name patterns — the logging-side complement to sanitization's secret-key set.
# Unlike ``safe_json`` (which drops sensitive keys before they reach audit/response
# payloads), log redaction keeps the key and masks the value so an operator can still
# see that the field was present.
_PII_KEY_PATTERN = re.compile(
    r"(phone|mobile|telephone|idcard|id_card|certno|cert_no|idno|id_no"
    r"|email|bankcard|bank_card|passport|address)",
    re.IGNORECASE,
)


def is_sensitive_key(key: object) -> bool:
    return _is_sensitive_json_key(key) or bool(_PII_KEY_PATTERN.search(str(key)))


def redact(value: Any, *, max_depth: int = 6, max_str: int = 2000) -> Any:
    if max_depth <= 0:
        return "[MAX-DEPTH]"
    if isinstance(value, dict):
        return {
            str(key): (
                REDACTED
                if is_sensitive_key(key)
                else redact(item, max_depth=max_depth - 1, max_str=max_str)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, max_depth=max_depth - 1, max_str=max_str) for item in value]
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + "...(truncated)"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = repr(value)
    return text if len(text) <= max_str else text[:max_str] + "...(truncated)"
