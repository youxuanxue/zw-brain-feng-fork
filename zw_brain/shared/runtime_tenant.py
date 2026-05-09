from __future__ import annotations

import os

DEFAULT_RUNTIME_TENANT = "sd-default"


def get_runtime_tenant_id() -> str:
    return os.environ.get("ZW_BRAIN_TENANT_ID", DEFAULT_RUNTIME_TENANT)
