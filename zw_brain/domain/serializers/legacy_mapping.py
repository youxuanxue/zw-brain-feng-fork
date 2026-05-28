"""Legacy mapping projection helpers — Action H commit 2 lift.

``legacy_mapping_refs`` extracts (legacy_system / legacy_object_type /
legacy_object_ref / canonical_type / canonical_ref / source_ref /
mapping_status) rows for a given canonical reference, with optional
``_RequestBatchContext`` short-circuit (pre-fetched mappings keyed by
``(canonical_type, canonical_ref)``).

Lifted from ``BrainService._legacy_mapping_refs`` — used by approval and
delivery handlers to build the ``legacyMappings`` projection on response
payloads. Pure read-side; no snapshot mutation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zw_brain.shared.runtime_tenant import DEFAULT_TENANT_ID as _DEFAULT_TENANT_ID

if TYPE_CHECKING:
    from zw_brain.domain.errors import _RequestBatchContext


def legacy_mapping_refs(
    store: Any,
    canonical_type: str,
    canonical_ref: str | list[str],
    *,
    context: _RequestBatchContext | None = None,
) -> list[dict[str, Any]]:
    """Return legacyMappings projection rows for ``(canonical_type, canonical_ref)``.

    When ``context`` is provided, prefers the batched in-memory map
    (``context.legacy_mappings_by_ref``) over a DB roundtrip.

    Replaces ``BrainService._legacy_mapping_refs``.
    """
    refs = canonical_ref if isinstance(canonical_ref, list) else [canonical_ref]
    rows: list[dict[str, Any]] = []
    for ref in refs:
        if context is not None:
            items = context.legacy_mappings_by_ref.get((canonical_type, str(ref)), [])
        else:
            items = store.legacy_mapping_repo.list_mappings(
                canonical_type=canonical_type,
                canonical_ref=str(ref),
                tenant_id=_DEFAULT_TENANT_ID,
            )
        for item in items:
            rows.append(
                {
                    "legacy_system": item.legacy_system,
                    "legacy_object_type": item.legacy_object_type,
                    "legacy_object_ref": item.legacy_object_ref,
                    "canonical_type": item.canonical_type,
                    "canonical_ref": item.canonical_ref,
                    "source_ref": item.source_ref,
                    "mapping_status": item.mapping_status,
                }
            )
    return rows
