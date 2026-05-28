"""Handler dependency container — Action A of god-object decoupling.

Background
----------
Before this commit handlers used the signature ``handler(brain, skill_id,
payload)`` and reverse-accessed BrainService private members ~887 times
(``brain._ui_state``, ``brain._mutate``, ``brain._append_audit_feed``,
``brain._snapshot``, ``brain._state_store``, 6 repo factories, plus dozens
of helper methods). This made handlers untestable in isolation and pinned
every cross-cutting concern (audit, anchor, persist, sync) to a single
god-object class.

This module introduces two value objects:

- ``SkillContext`` — per-call immutable identity + manifest snapshot
  (``skill_id`` / ``role`` / ``actor`` / ``confirmed`` / ``manifest``).
  Replaces handler reads of ``brain._ui_state["role"]`` +
  ``brain._actor_for_role(role)`` + ``get_manifest(skill_id)``.

- ``HandlerDeps`` — process-wide dependency container holding:
  - ``repos`` (6 concrete repository handles)
  - ``state_store`` / ``audit_bus`` / ``queue`` (infra surfaces)
  - ``write(ctx, payload, mutation)`` / ``append_audit_feed(...)`` (thin
    wrappers over BrainService cross-cutting methods, soon to be lifted
    into a real ``SkillPipeline`` in Action B)
  - ``brain_legacy`` — an explicit escape hatch holding the as-yet-unmigrated
    BrainService surface. ``scripts/check_handler_no_brain_backref.py``
    whitelists exactly which ``deps.brain_legacy.X`` accesses are allowed;
    growing the whitelist requires a documented debt entry.

Why a single-PR Plan A
----------------------
Migrating 58 handler modules + ~887 reverse-access points + the
``_mutate`` closure pipeline in one PR is high risk. Plan A (this PR)
scope:

1. Introduce ``HandlerDeps`` / ``SkillContext`` + handler signature
   ``(deps, ctx, payload)`` — mechanical refactor.
2. Eliminate ~300+ reverse accesses where the new container has a
   1-to-1 replacement: ``ctx.role`` / ``ctx.actor`` / ``deps.repos.*`` /
   ``deps.state_store`` / ``deps.write(...)`` / ``deps.append_audit_feed(...)``.
3. Leave ``snapshot`` reads/writes, lookup helpers (``_request_by_id`` etc.),
   and aggregate-projection methods (``_application_record_to_request``)
   on ``deps.brain_legacy`` — these need Action B (pipeline) + Action C
   (CQRS read model) to retire properly.

Out of scope for this PR (deferred to Action B / Action C):
- ``_mutate`` body refactored into a real middleware pipeline.
- ``snapshot`` reads moved behind a typed view interface.
- ``_emit_audit`` / ``_enqueue_anchor`` lifted out of BrainService.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService
    from zw_brain.command.pipeline import SkillPipeline
    from zw_brain.command.views import ReadViews
    from zw_brain.domain.repositories.delivery import DeliveryRepository
    from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.domain.repositories.topic_package import TopicPackageRepository
    from zw_brain.domain.services import DomainServices
    from zw_brain.shared.state_store import StateStore


@dataclass(frozen=True)
class Repos:
    """Concrete repo handles — eliminates 6 ``brain._X_repo()`` factories +
    Action C extends with 8 more repos to retire 59 ``brain._state_store.database_store.X``
    direct accesses in handler bodies.

    Constructed once per HandlerDeps build (``HandlerDeps.from_brain``);
    handlers never construct repos directly. Fields are intentionally typed
    as the concrete repository so handler code path discovery is direct
    (``deps.repos.delivery.list_tasks(...)``); fallback (no database_store)
    is materialised at construction time, not lazily per call.
    """

    # Action A — original 6
    objection: Any  # ObjectionRepository — concrete type avoids import cycle
    external_adapter: ExternalAdapterRepository
    governance_projection: GovernanceProjectionRepository
    topic_package: TopicPackageRepository
    capability_package: Any  # CapabilityPackageRepository — same as objection
    delivery: DeliveryRepository
    # Action C — 8 additional repos so handlers no longer reach into
    # ``brain._state_store.database_store.X`` to find them.
    catalog: Any           # CatalogRepository
    application: Any       # ApplicationRepository
    approval: Any          # ApprovalRepository
    gateway_runtime: Any   # GatewayRuntimeRepository
    legacy_mapping: Any    # LegacyObjectMappingRepository
    metadata_evidence: Any # MetadataEvidenceRepository
    resource_api: Any      # ResourceApiRepository
    service_invocation: Any # ServiceInvocationMetricRepository


@dataclass(frozen=True)
class SkillContext:
    """Per-call immutable context — identity + manifest snapshot.

    Replaces handler reads of:
    - ``brain._ui_state["role"]``  → ``ctx.role``
    - ``brain._actor_for_role(role)`` (called per-handler) → ``ctx.actor``
    - ``get_manifest(skill_id)`` (re-fetched in handlers) → ``ctx.manifest``
    - ``payload.get("confirmed")`` (parsed inconsistently) → ``ctx.confirmed``

    The ``manifest`` snapshot is captured once at ``invoke_skill`` entry and
    carried verbatim through dispatch — handlers no longer re-fetch it (which
    is what made manifest version drift hard to reason about in PR #79).
    """

    skill_id: str
    role: str
    actor: str
    confirmed: bool
    manifest: dict[str, Any]

    @property
    def is_write(self) -> bool:
        return bool(self.manifest.get("side_effects"))

    @property
    def audit_required(self) -> bool:
        return bool(self.manifest.get("audit_required"))


@dataclass(frozen=True)
class HandlerDeps:
    """Process-wide dependency container for skill handlers.

    Handler signature transition:
        OLD: handler(brain: BrainService, skill_id: str, payload: dict)
        NEW: handler(deps: HandlerDeps, ctx: SkillContext, payload: dict)

    ``brain_legacy`` is the explicit escape hatch for migration: handlers
    accessing as-yet-unmigrated BrainService surface (``snapshot`` reads,
    in-memory lookup helpers, aggregate-projection methods) use
    ``deps.brain_legacy.X`` — preflight 段 40 whitelists exactly which
    ``X`` are allowed; expanding the whitelist requires a debt entry.

    Cross-cutting wrappers (``write`` / ``append_audit_feed``) are thin
    delegations to BrainService methods today; they exist on HandlerDeps
    so handler call-sites are stable when Action B lifts the implementation
    into a real ``SkillPipeline`` (handler code won't change again).
    """

    repos: Repos
    state_store: StateStore
    audit_bus: Any  # zw_brain.shared.audit module
    queue: Any  # zw_brain.shared.queue module
    pipeline: SkillPipeline  # Action B — see zw_brain/command/pipeline.py
    view: ReadViews  # Action C — see zw_brain/command/views.py
    services: DomainServices  # Action D — see zw_brain/domain/services/__init__.py
    brain_legacy: BrainService  # preflight 段 40 whitelisted escape hatch

    # ------------------------------------------------------------------
    # Cross-cutting facade — handler-facing canonical write/read entries.
    #
    # ``write`` / ``read`` route through SkillPipeline (Action B). Handlers
    # don't access ``deps.pipeline.X`` directly — preflight segment 43
    # forbids that, so we have one canonical entry shape (``deps.write``).
    #
    # ``append_audit_feed`` still delegates to BrainService — no pipeline
    # equivalent today; Action D may lift it into a domain service.
    # ------------------------------------------------------------------

    def write(
        self,
        ctx: SkillContext,
        payload: dict[str, Any],
        mutation: Callable[[str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run a write-path mutation through the SkillPipeline middleware chain.

        Replaces ``brain._mutate(skill_id, role, confirmed, payload, mutation)``.

        The ``mutation`` callable receives ``(audit_id, actor)`` and must
        return the result dict — same closure contract as before, so handler
        bodies migrate mechanically. The chain (Policy → Identity → AuditEmit
        → CapabilityCall → Persist → Anchor) is documented in
        ``zw_brain/command/pipeline.py`` and verified by preflight segment 42.
        """
        return self.pipeline.write(ctx, payload, mutation)

    def read(
        self,
        ctx: SkillContext,
        payload: dict[str, Any],
        fn: Callable[[str, str], Any],
    ) -> Any:
        """Run a traced read through the SkillPipeline (no Persist, no Anchor).

        Replaces ``brain._invoke_traced_read(skill_id, role, payload, fn)``
        for ``audit_required and not side_effects`` skills. ``fn(audit_id,
        actor)`` returns the handler's raw result (any shape — not wrapped
        in the write envelope).
        """
        return self.pipeline.read(ctx, payload, fn)

    def append_audit_feed(
        self, event_type: str, target: str, result: str, actor: str
    ) -> None:
        """Replaces ``brain._append_audit_feed(event_type, target, result, actor)``."""
        self.brain_legacy._append_audit_feed(event_type, target, result, actor)

    # ------------------------------------------------------------------
    # Factory — constructed once per BrainService at runtime entry.
    # ------------------------------------------------------------------

    @classmethod
    def from_brain(cls, brain: BrainService) -> HandlerDeps:
        """Build a HandlerDeps bound to the given BrainService.

        Materializes repos eagerly: when ``database_store`` is configured,
        all 6 repos come from the store; otherwise fall back to fresh
        in-memory instances (legacy parity for tests / CLI without a DB).
        """
        # Local imports break circular dependency (deps → brain → handlers → deps).
        import zw_brain.shared.audit as audit_bus
        from zw_brain.command.pipeline import build_default_pipeline
        from zw_brain.command.views import ReadViews
        from zw_brain.domain.services import DomainServices
        from zw_brain.shared import queue

        store = brain._state_store
        db_store = store.database_store
        if db_store is not None:
            repos = Repos(
                # Action A — original 6
                objection=db_store.objection_repo,
                external_adapter=db_store.external_adapter_repo,
                governance_projection=db_store.governance_projection_repo,
                topic_package=db_store.topic_package_repo,
                capability_package=db_store.capability_package_repo,
                delivery=db_store.delivery_repo,
                # Action C — 8 additional repos
                catalog=db_store.catalog_repo,
                application=db_store.application_repo,
                approval=db_store.approval_repo,
                gateway_runtime=db_store.gateway_runtime_repo,
                legacy_mapping=db_store.legacy_mapping_repo,
                metadata_evidence=db_store.metadata_evidence_repo,
                resource_api=db_store.resource_api_repo,
                service_invocation=db_store.service_invocation_repo,
            )
        else:
            from zw_brain.domain.repositories.application import ApplicationRepository
            from zw_brain.domain.repositories.approval import ApprovalRepository
            from zw_brain.domain.repositories.capability_package import CapabilityPackageRepository
            from zw_brain.domain.repositories.catalog import CatalogRepository
            from zw_brain.domain.repositories.delivery import DeliveryRepository
            from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
            from zw_brain.domain.repositories.gateway_runtime import GatewayRuntimeRepository
            from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
            from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
            from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository
            from zw_brain.domain.repositories.objection import ObjectionRepository
            from zw_brain.domain.repositories.resource_api import ResourceApiRepository
            from zw_brain.domain.repositories.service_invocation import ServiceInvocationMetricRepository
            from zw_brain.domain.repositories.topic_package import TopicPackageRepository

            repos = Repos(
                objection=ObjectionRepository(),
                external_adapter=ExternalAdapterRepository(),
                governance_projection=GovernanceProjectionRepository(),
                topic_package=TopicPackageRepository(),
                capability_package=CapabilityPackageRepository(),
                delivery=DeliveryRepository(),
                catalog=CatalogRepository(),
                application=ApplicationRepository(),
                approval=ApprovalRepository(),
                gateway_runtime=GatewayRuntimeRepository(),
                legacy_mapping=LegacyObjectMappingRepository(),
                metadata_evidence=MetadataEvidenceRepository(),
                resource_api=ResourceApiRepository(),
                service_invocation=ServiceInvocationMetricRepository(),
            )
        return cls(
            repos=repos,
            state_store=store,
            audit_bus=audit_bus,
            queue=queue,
            pipeline=build_default_pipeline(brain),
            view=ReadViews.from_brain(brain),
            services=DomainServices.from_brain(brain),
            brain_legacy=brain,
        )
