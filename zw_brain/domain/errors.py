"""Domain-layer error hierarchy + request-batch context (R-016 retrofit).

These types previously lived in ``zw_brain.command.brain`` and were imported
back into domain services via lazy ``from zw_brain.command.brain import ...``
statements (a workaround for the circular dependency ``brain → services →
brain``). Lifting them into the domain layer where they belong eliminates the
25 lazy imports and the layer violation.

Layer note: this module sits at ``zw_brain.domain.errors`` and depends only
on the standard library. Both ``command/brain.py`` and ``domain/services/*``
import from here directly. ``command.brain`` re-exports for backward
compatibility with handler / test call sites that still spell
``from zw_brain.command.brain import NotFoundError``.

Mirrors the historical class hierarchy 1:1 so behaviour is identical:

    BrainServiceError (RuntimeError)
        ├── UnknownSkillError
        ├── AccessDeniedError
        ├── ConfirmationRequiredError
        ├── InvalidStateError
        ├── NotFoundError
        └── InvalidTokenError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class BrainServiceError(RuntimeError):
    pass


class UnknownSkillError(BrainServiceError):
    pass


class AccessDeniedError(BrainServiceError):
    pass


class ConfirmationRequiredError(BrainServiceError):
    pass


class InvalidStateError(BrainServiceError):
    pass


class NotFoundError(BrainServiceError):
    pass


class InvalidTokenError(BrainServiceError):
    pass


@dataclass
class _RequestBatchContext:
    """Prefetched indices for list_requests N+1 elimination (D-9).

    Why: list_requests previously called delivery_repo.list_tasks() /
    application_repo.list_records() / legacy_mapping_repo.list_mappings() /
    resource_api_repo.list_assets() / metadata_evidence_repo.list_schema_*()
    once per item (deep N+1 through get_resource → _enrich_catalog_detail),
    ~37s on the customer browser replay. This context bundles prefetched
    indices that helpers consult instead of re-fetching.
    """

    delivery_by_appcode: dict[str, Any] = field(default_factory=dict)
    application_records: list[Any] = field(default_factory=list)
    legacy_mappings_by_ref: dict[tuple[str, str], list[Any]] = field(default_factory=dict)
    quality_by_target: dict[tuple[str, str], list[Any]] = field(default_factory=dict)
    resource_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Enrichment-layer prefetches (consumed by _enrich_catalog_detail / _mapping_diagnostics).
    resource_assets_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    schema_mappings_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    schema_snapshots_by_resource: dict[str, list[Any]] = field(default_factory=dict)
    catalog_items_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    catalog_items_by_item_code: dict[str, Any] = field(default_factory=dict)
