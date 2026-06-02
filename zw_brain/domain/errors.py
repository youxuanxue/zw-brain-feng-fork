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


class QuotaExceededError(BrainServiceError):
    """Raised when a per-tenant / per-credential call quota is exhausted.

    Carries ``retry_after`` (seconds) so a structured, machine-actionable error
    can be projected to consumer surfaces (MCP / REST) instead of a 500 black box
    (mcp-hardening S4). ``scope`` names what was throttled (e.g. ``"mcp_tool_call"``).
    """

    def __init__(self, message: str, *, retry_after: int = 60, scope: str = "") -> None:
        super().__init__(message)
        self.retry_after = int(retry_after)
        self.scope = scope


class TrustLevelInsufficientError(AccessDeniedError):
    """Raised when a caller's trust level is too low for a responsibility-bearing write.

    mcp-hardening S6: an external agent at ``trust_level=untrusted`` reaching a
    side-effecting / human-confirmation capability through MCP is denied here.
    Subclasses ``AccessDeniedError`` so existing 403 mapping holds, but carries
    the structured ``reason`` ('trust_level_insufficient') + the offending level
    so the MCP layer can project a typed error and the audit layer can stamp it.
    """

    reason = "trust_level_insufficient"

    def __init__(self, message: str, *, trust_level: str = "untrusted", required: str = "verified") -> None:
        super().__init__(message)
        self.trust_level = trust_level
        self.required = required


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


@dataclass
class _TopicPackageBatchContext:
    """Prefetched indices for topic.package.query list-projection N+1 elimination.

    Why: ``list_projection`` → ``projection_summary`` → ``catalog_projection_items``
    + ``authorization_summary`` previously re-scanned the *whole*
    resource_asset + delivery_task tables, plus issued per-catalog-item
    list_items / list_schema_mappings / list_schema_snapshots / get_entry, *once
    per package* (~1.4 s / 1252 sessions for ~90 packages). This context bundles
    one-pass prefetched indices that the projection helpers consult instead of
    re-fetching — the same shape of fix already applied to list_requests /
    list_delivery_tasks (D-9, request_service.build_batch_context).

    Built once by ``TopicPackageService.build_list_batch_context`` and threaded
    through ``list_projection`` for the whole page; ``None`` means "no context,
    fall back to per-call queries" (single-package detail path keeps its old
    behaviour, which is already cheap).
    """

    # topic-package side
    items_by_package: dict[str, list[Any]] = field(default_factory=dict)
    visibility_by_package: dict[str, list[Any]] = field(default_factory=dict)
    # catalog / resource side (shared across all packages on the page)
    assets_by_catalog: dict[str, list[Any]] = field(default_factory=dict)
    deliveries: list[Any] = field(default_factory=list)
    catalog_entry_status_by_code: dict[str, str | None] = field(default_factory=dict)
    catalog_item_count_by_catalog: dict[str, int] = field(default_factory=dict)
    schema_mapping_count_by_catalog: dict[str, int] = field(default_factory=dict)
    schema_snapshot_count_by_resource: dict[str, int] = field(default_factory=dict)
