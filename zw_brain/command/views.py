"""ReadViews — Action C read-path facade replacing handler ``brain._snapshot[X]``
and ``brain._state_store.X`` reverse-access.

Background
----------
Before Action C, handlers read application state from three Sources of Truth:

1. ``brain._snapshot[X]`` (in-memory dict)            — 50 reverse access points
2. ``brain._state_store.database_store.X.method()``   — 59 reverse access points
3. ``brain._<entity>_by_id(...)`` lookup helpers     — 38 reverse access points

These three SoTs are kept in sync by ``BrainService._sync_state_views()`` after
every write; reads pick whichever the handler happened to know about. Handlers
encode that knowledge as private-method accesses on ``brain``, which means:

- Tests can't mock reads without mocking BrainService internals.
- Adding a new read-path filter (e.g. per-tenant scope, per-role mask)
  requires editing BrainService god-class.
- Reverse-access growth is invisible — no boundary mechanically enforced.

This module introduces a single typed read facade:

    ``deps.view.<entity>.<method>(...)``

handlers go through the facade instead of reaching into BrainService internals.
The implementation today still reads ``brain._snapshot`` and ``database_store``
under the hood — Action C is read-path consolidation, not storage redesign.
Storage layer changes (retiring _snapshot dict, single-SoT writes) are Action D.

Two return-semantics flavors (explicit by method name)
------------------------------------------------------
The facade has two kinds of methods, with deliberately different return
semantics that callers must understand:

A. **Bulk / aggregate reads** — ``list_all()``, ``get()``, ``get_for_role()``,
   ``list_articles()``, ``get_resources()``, ``list_todos()``, ``get_discovery()``.

   These return a ``copy.deepcopy(...)`` of the underlying snapshot slice. The
   caller may mutate the result without affecting the live snapshot; in-place
   mutation will NOT propagate through ``PersistMiddleware``. Use these for
   read-only display surfaces.

B. **Per-entity live lookups** — ``find_by_id(...)`` (on RequestsView /
   PackagesView / DeliveryView), ``find_by_request_id(...)`` (DeliveryView).

   These return a **live reference** into ``brain._snapshot[...]`` (no
   deepcopy). The caller MAY mutate the returned dict in place, and the
   mutation will be visible to the next write-path ``_sync_state_views``
   tick (this is intentional — the 36 ``mutation(audit_id, actor)``
   closures in handlers depend on it).

   ``find_by_id`` (RequestsView / PackagesView / DeliveryView) raises
   ``NotFoundError`` when the entity is absent (delegating to
   ``BrainService._<entity>_by_id``); ``find_by_request_id`` returns
   ``None`` on miss. See per-method annotations.

   Two related lookups deliberately return **deepcopy / fresh dict** and
   therefore live under §A naming convention instead:
   ``DisputesView.get_dispute_by_id`` and
   ``ResourcesView.get_api_resource``. They appear next to the live
   ``find_by_id`` methods structurally but the ``get_*`` name signals
   that mutation does NOT propagate.

The naming convention is "the method itself describes its semantics":
``list_all`` / ``get*`` ⇒ deepcopy; ``find_*`` ⇒ live reference. A future
clarifier rename (``X_ref_by_id``) is Action D scope when ``BrainService``
read helpers retire.

What stays the same
-------------------
- ``BrainService._sync_state_views`` still runs after every mutation (PersistMiddleware).
- ``_snapshot`` dict is still loaded at startup from ``brain_state.json``.
- ``database_store`` is still the authoritative SQL persistence.

What changes
------------
- Handlers and helpers stop importing or referencing ``brain._snapshot`` /
  ``brain._state_store`` / ``brain._<entity>_by_id`` directly.
- All read access goes through ``ReadViews`` typed methods.
- Preflight segment 45 mechanically guards the boundary.

Adding a new read view
----------------------
1. Add a method to the existing ``<Entity>View`` class (or create a new view
   class if the entity wasn't in the original 14 snapshot keys).
2. ``ReadViews.from_brain`` exposes the view as ``deps.view.<entity>``.
3. Handler call sites use ``deps.view.<entity>.<method>(...)``.
4. preflight 段 45 verifies no new ``brain._snapshot`` / ``brain._state_store``
   reads have crept in.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


# ───────────────────────────────────────────────────────────────────────────
# Snapshot-backed views (read from brain._snapshot[X] today; Action D
# retires _snapshot dict and reads database_store directly. Caller-facing
# API stays stable across that work.)
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SnapshotView:
    """Generic snapshot key reader — handlers use specialized subclasses below."""
    brain: Any  # BrainService — typed Any to avoid import cycle

    def _read(self, key: str, default: Any = None) -> Any:
        return self.brain._snapshot.get(key, default)


@dataclass(frozen=True)
class WorkbenchView(SnapshotView):
    """工作台视图 (P1 dashboard) — per-role todos."""
    def get_for_role(self, role: str) -> dict[str, Any]:
        workbench = self._read("workbench", {})
        return copy.deepcopy(workbench.get(role, {"todos": []}))

    def list_todos(self, role: str) -> list[dict[str, Any]]:
        return self.get_for_role(role).get("todos", [])


@dataclass(frozen=True)
class DiscoveryView(SnapshotView):
    """资源发现视图 (P2 discovery)."""
    def get_resources(self) -> list[dict[str, Any]]:
        """Return a deepcopy of the resource list under ``discovery`` (read-only)."""
        return copy.deepcopy(self._read("discovery", {}).get("resources", []))

    def get_discovery(self) -> dict[str, Any]:
        """Return a deepcopy of the full ``discovery`` snapshot slice (read-only)."""
        return copy.deepcopy(self._read("discovery", {}))

    def get_recall_dictionary(self) -> dict[str, Any]:
        """Return a deepcopy of the NL recall dictionary (read-only)."""
        return copy.deepcopy(self._read("discovery", {}).get("recallDictionary", {}))

    def find_by_id(self, resource_id: str) -> dict[str, Any]:
        """Return the live snapshot reference for a discovery resource (mutable — see module docstring §B).

        Raises ``NotFoundError`` if no resource matches.

        Action H commit 3: lookup lifted from ``BrainService._resource_by_id``;
        callers route through ``deps.view.discovery.find_by_id(...)``.
        """
        from zw_brain.domain.errors import NotFoundError  # noqa: PLC0415
        for item in self.brain._snapshot["discovery"]["resources"]:
            if item["id"] == resource_id:
                return item
        raise NotFoundError(resource_id)


@dataclass(frozen=True)
class RequestsView(SnapshotView):
    """申请单视图 (P3 application)."""
    def list_all(self) -> list[dict[str, Any]]:
        """Return a deepcopy of all requests (read-only — see module docstring §A)."""
        return copy.deepcopy(self._read("requests", []))

    def find_by_id(self, request_id: str) -> dict[str, Any]:
        """Return the live snapshot reference for a request (mutable — see module docstring §B).

        Raises ``NotFoundError`` if no request matches.
        """
        return self.brain._get_handler_deps().services.request.by_id(request_id)


@dataclass(frozen=True)
class ApprovalsView(SnapshotView):
    """审批视图 (P3 review)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("approvals", []))


@dataclass(frozen=True)
class DeliveryView(SnapshotView):
    """交付任务视图 (P4 delivery)."""
    def list_all(self) -> list[dict[str, Any]]:
        """Return a deepcopy of all delivery tasks (read-only — see module docstring §A)."""
        return copy.deepcopy(self._read("delivery_tasks", []))

    def find_by_id(self, task_id: str) -> dict[str, Any]:
        """Return the live snapshot reference for a delivery task (mutable — see module docstring §B).

        Raises ``NotFoundError`` if no task matches.
        """
        return self.brain._get_handler_deps().services.delivery.by_id(task_id)

    def find_by_request_id(self, request_id: str) -> dict[str, Any] | None:
        """Return the live snapshot reference for the delivery task of a given request,
        or ``None`` if no delivery is bound to that request (see module docstring §B).
        """
        return self.brain._get_handler_deps().services.delivery.by_request_id(request_id)


@dataclass(frozen=True)
class ResourcesView(SnapshotView):
    """提供方资源视图 (P5 provider)."""
    def list_all(self) -> list[dict[str, Any]]:
        """Return a deepcopy of all provider resources (read-only — see module docstring §A)."""
        return copy.deepcopy(self._read("resources", []))

    def list_api_resources(self) -> list[dict[str, Any]]:
        """Return a deepcopy of all API resources from the snapshot in-memory fallback path.

        Note: this reads ``brain._snapshot["api_resources"]`` (in-memory mirror).
        DB-backed lookups go through ``deps.repos.resource_api`` or
        ``find_api_resource``; this method is the bulk read used by discovery /
        search aggregators that need every API resource regardless of source.
        """
        return copy.deepcopy(self._read("api_resources", []))

    def get_api_resource(self, resource_id: str) -> dict[str, Any] | None:
        """Return a deepcopy / fresh-dict view of an API resource, or ``None`` if absent.

        Name follows the §A "get_*" → deepcopy convention. ``provider.find_api_resource``
        deepcopies the in-memory fallback path and returns a freshly-serialized dict
        for DB-backed lookups, so mutations on the returned dict do NOT propagate to
        the live snapshot. Use ``deps.repos.resource_api`` if a live SQL-backed
        write path is required.
        """
        return self.brain._get_handler_deps().services.provider.find_api_resource(resource_id)


@dataclass(frozen=True)
class ProviderView(SnapshotView):
    """提供方主视图 (P5 dashboard)."""
    def get(self) -> dict[str, Any]:
        return copy.deepcopy(self._read("provider", {}))


@dataclass(frozen=True)
class DisputesView(SnapshotView):
    """异议视图 (P6 disputes)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("disputes", []))

    def get_dispute_by_id(self, dispute_id: str) -> dict[str, Any] | None:
        """Return a deepcopy of the dispute matching ``dispute_id`` (read-only — see module docstring §A).

        Name follows the §A "get_*" → deepcopy convention; mutations on the
        returned dict do NOT propagate to ``brain._snapshot["disputes"]``.
        """
        for item in self._read("disputes", []):
            if item.get("id") == dispute_id:
                return copy.deepcopy(item)
        return None


@dataclass(frozen=True)
class AuditEventsView(SnapshotView):
    """审计事件视图 (B1 audit center)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("audit_events", []))


@dataclass(frozen=True)
class ZonesView(SnapshotView):
    """共享专区视图 (P7 zones)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("zones", []))

    def find_by_id(self, zone_id: str) -> dict[str, Any]:
        """Return the live snapshot reference for a zone (mutable — see module docstring §B).

        Raises ``NotFoundError`` if no zone matches.

        Action H commit 3: lookup lifted from ``BrainService._zone_by_id``;
        callers route through ``deps.view.zones.find_by_id(...)``.
        """
        from zw_brain.domain.errors import NotFoundError  # noqa: PLC0415
        for item in self.brain._snapshot["zones"]:
            if item["id"] == zone_id:
                return item
        raise NotFoundError(zone_id)


@dataclass(frozen=True)
class PackagesView(SnapshotView):
    """能力包视图 (P8 capability packages)."""
    def list_all(self) -> list[dict[str, Any]]:
        """Return a deepcopy of all capability packages (read-only — see module docstring §A)."""
        return copy.deepcopy(self._read("capability_packages", []))

    def find_by_id(self, package_id: str) -> dict[str, Any]:
        """Return the live snapshot reference for a capability package (mutable — see module docstring §B).

        Raises ``NotFoundError`` if no package matches.

        Action E: lookup inlined here (the ``capability_packages`` snapshot key
        does not have a dedicated domain service yet; if a service emerges,
        retire this inline scan in its favour).
        """
        from zw_brain.domain.errors import NotFoundError  # noqa: PLC0415
        for item in self.brain._snapshot["capability_packages"]:
            if item["id"] == package_id:
                return item
        raise NotFoundError(package_id)


@dataclass(frozen=True)
class TicketsView(SnapshotView):
    """工单视图 (B1 ops tickets)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("tickets", []))


@dataclass(frozen=True)
class KnowledgeView(SnapshotView):
    """知识库视图 (P2 knowledge articles)."""
    def list_articles(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("knowledge_articles", []))


@dataclass(frozen=True)
class AlertsView(SnapshotView):
    """告警视图 (B1 alerts)."""
    def list_all(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._read("alerts", []))


@dataclass(frozen=True)
class AuditAiView(SnapshotView):
    """审计 AI 摘要视图 (B1 AI summary)."""
    def get(self) -> dict[str, Any]:
        return copy.deepcopy(self._read("audit_ai", {}))


# ───────────────────────────────────────────────────────────────────────────
# ReadViews — facade exposed as deps.view
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReadViews:
    """Read-path facade exposed as ``deps.view``.

    Constructed once per HandlerDeps build (``HandlerDeps.from_brain``).
    Adds one view per snapshot top-level key (14 keys verified at Action C
    commit 1 — provider/disputes/discovery/workbench/tickets/requests/
    knowledge_articles/zones/delivery_tasks/capability_packages/audit_events/
    audit_ai/approvals/alerts/resources).
    """

    workbench: WorkbenchView
    discovery: DiscoveryView
    requests: RequestsView
    approvals: ApprovalsView
    delivery: DeliveryView
    resources: ResourcesView
    provider: ProviderView
    disputes: DisputesView
    audit_events: AuditEventsView
    zones: ZonesView
    packages: PackagesView
    tickets: TicketsView
    knowledge: KnowledgeView
    alerts: AlertsView
    audit_ai: AuditAiView

    @classmethod
    def from_brain(cls, brain: BrainService) -> ReadViews:
        """Build ReadViews wired to a BrainService.

        All 14 views currently read ``brain._snapshot`` / ``brain._<entity>_by_id``
        directly. When Action D moves reads off the in-memory snapshot, individual
        view classes will gain repo parameters; the single-caller (``HandlerDeps``)
        signature is cheap to change then.
        """
        return cls(
            workbench=WorkbenchView(brain=brain),
            discovery=DiscoveryView(brain=brain),
            requests=RequestsView(brain=brain),
            approvals=ApprovalsView(brain=brain),
            delivery=DeliveryView(brain=brain),
            resources=ResourcesView(brain=brain),
            provider=ProviderView(brain=brain),
            disputes=DisputesView(brain=brain),
            audit_events=AuditEventsView(brain=brain),
            zones=ZonesView(brain=brain),
            packages=PackagesView(brain=brain),
            tickets=TicketsView(brain=brain),
            knowledge=KnowledgeView(brain=brain),
            alerts=AlertsView(brain=brain),
            audit_ai=AuditAiView(brain=brain),
        )
