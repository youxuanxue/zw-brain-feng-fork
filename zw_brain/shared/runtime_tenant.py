from __future__ import annotations

import os

DEFAULT_RUNTIME_TENANT = "sd-default"


def get_runtime_tenant_id() -> str:
    return os.environ.get("ZW_BRAIN_TENANT_ID", DEFAULT_RUNTIME_TENANT)


# Module-load snapshot of the active tenant id. Single source of truth replacing
# the per-module ``_DEFAULT_TENANT_ID = get_runtime_tenant_id()`` line that used
# to live in brain.py + each domain service file (6+ copies). Tests that mutate
# ``ZW_BRAIN_TENANT_ID`` and need the new value should call ``get_runtime_tenant_id()``
# directly rather than this constant.
DEFAULT_TENANT_ID = get_runtime_tenant_id()
