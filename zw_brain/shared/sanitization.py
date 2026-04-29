from __future__ import annotations

import copy
from typing import Any

SENSITIVE_JSON_KEYS = {"secret", "password", "token", "credential", "app_secret", "superior_app_secret"}


def safe_json(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {key: item for key, item in copy.deepcopy(value).items() if key.lower() not in SENSITIVE_JSON_KEYS}
