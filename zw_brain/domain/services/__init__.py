"""Domain services — Action D: 7 bounded contexts split out of BrainService.

The seven services (``CatalogService`` / ``TopicPackageService`` /
``DeliveryService`` / ``ApplicationService`` / ``RequestService`` /
``ProviderService`` / ``GovernanceService``) hold the method bodies that
previously lived as private methods on ``BrainService``. Each service is a
frozen dataclass that takes a ``BrainService`` reference; handler call sites
go through ``deps.services.<svc>.<method>(...)`` (constructed in
``HandlerDeps.from_brain``). ``BrainService`` retains a one-line delegate
shim per migrated method for back-compat — preflight segment 47
(``scripts/check_brain_no_domain_method.py``) enforces the shim shape.

What stays on BrainService (post-Action D)
------------------------------------------
- ``invoke_skill`` / ``manifests`` / ``snapshot`` — public surface
- ``_build_skill_context`` / ``_get_handler_deps`` / ``_dispatch_skill``
- ``enrich_actor_snapshot_for_session`` — session enrichment
- PR #86 delegate shims (``get_resource`` / ``get_request`` /
  ``create_request`` / ...) — kept until handler-test sweep retires them
- Cross-cutting pipeline ops (``_mutate`` / ``_invoke_traced_read`` /
  ``_emit_audit`` / ``_enqueue_anchor`` / ``_persist`` / ``_sync_*`` /
  ``_append_audit_feed``). These deeply couple to ``self._snapshot`` and
  ``self._ui_state`` mutable singletons; extracting them into a sibling
  ``zw_brain/command/pipeline_ops.py`` requires lifting the state model
  out of BrainService first (move ``_snapshot`` from instance attr to
  ``state_store.snapshot``, retarget every reader). That is **Action E
  scope**, not Action D — Action D's contract was the domain-method split
  enforced by segment 47, which is delivered. SkillPipeline middleware
  (Action B) already isolates handler call sites from these methods, so
  the back-channel is the BrainService-internal one only.

Why services, not free functions
--------------------------------
Free functions would have the same shape (take brain, take repos, return
dict) but lose two affordances:

1. Cohesion grouping — 10 catalog methods on a class are easier to scan
   than 10 module-level functions ("did I update all catalog methods
   consistently?" is a class scan).
2. Repo injection — once handlers migrate, services will receive ``Repos``
   via constructor and drop the brain backref. A class is the natural
   shape for that change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from zw_brain.domain.services.application_service import ApplicationService
from zw_brain.domain.services.catalog_service import CatalogService
from zw_brain.domain.services.delivery_service import DeliveryService
from zw_brain.domain.services.governance_service import GovernanceService
from zw_brain.domain.services.provider_service import ProviderService
from zw_brain.domain.services.request_service import RequestService
from zw_brain.domain.services.topic_package_service import TopicPackageService

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService


@dataclass(frozen=True)
class DomainServices:
    """Container exposing the 7 domain services as ``deps.services.<name>``.

    Constructed once per HandlerDeps build (``HandlerDeps.from_brain``).
    Frozen dataclass: container shape is stable for the BrainService lifetime.
    """

    catalog: CatalogService
    topic_package: TopicPackageService
    delivery: DeliveryService
    application: ApplicationService
    request: RequestService
    provider: ProviderService
    governance: GovernanceService

    @classmethod
    def from_brain(cls, brain: BrainService) -> DomainServices:
        """Build the 7 services bound to a BrainService.

        Each service receives the brain reference verbatim for now; in Action
        D follow-ups services receive ``Repos`` directly and drop the brain
        backref.
        """
        return cls(
            catalog=CatalogService(brain=brain),
            topic_package=TopicPackageService(brain=brain),
            delivery=DeliveryService(brain=brain),
            application=ApplicationService(brain=brain),
            request=RequestService(brain=brain),
            provider=ProviderService(brain=brain),
            governance=GovernanceService(brain=brain),
        )


__all__ = [
    "ApplicationService",
    "CatalogService",
    "DeliveryService",
    "DomainServices",
    "GovernanceService",
    "ProviderService",
    "RequestService",
    "TopicPackageService",
]
