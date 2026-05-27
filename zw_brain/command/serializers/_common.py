"""Shared infra for serializers — default mask role + the ``_mask`` shim.

Mirrors the original ``zw_brain.command.brain._mask`` / ``_DEFAULT_MASK_ROLE``
defined at module top of brain.py (see [2026-05-06] sensitive-field policy
comment). Kept identical here to make the extraction byte-for-byte equivalent.

``DEFAULT_MASK_ROLE`` is the single source for serializers that need a custom
``field_policy`` (e.g. ``metadata.mask_schema_mapping_payload``) and therefore
cannot just call ``mask()``. Don't re-read ``ZW_BRAIN_MASK_ROLE`` elsewhere in
this package — import this constant.
"""
from __future__ import annotations

import os
from typing import Any

from zw_brain.shared.sensitive_mask import apply_field_masks

DEFAULT_MASK_ROLE = os.environ.get("ZW_BRAIN_MASK_ROLE", "external")


def mask(payload: Any) -> Any:
    """Apply default-role mask to a serializer's outgoing payload."""
    return apply_field_masks(payload, role=DEFAULT_MASK_ROLE)
