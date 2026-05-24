"""J1 provider handlers — 1 cap migrated from BrainService (F1 turn 6, J1 收官)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

import copy

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _get_provider_view(brain) -> dict[str, Any]:
    provider = copy.deepcopy(brain._snapshot["provider"])
    # National Direct Access (业务运营员 跨大区上报通道) demo data lives only in
    # seed_snapshot.json and is not persisted. Older DB rows predate this
    # field, so we hydrate it from the seed clone whenever the loaded
    # snapshot is missing it.
    if "directAccess" not in provider:
        from zw_brain.domain.seed import clone_seed_snapshot
        seed = clone_seed_snapshot()
        direct = seed.get("provider", {}).get("directAccess")
        if direct is not None:
            provider["directAccess"] = direct
    store = brain._state_store.database_store
    if store is None:
        return provider
    packages = brain.list_packages()
    delivery = brain._provider_focus_delivery()
    resource_id = brain._provider_primary_resource_id()
    resource = brain.get_resource(resource_id) if resource_id else {}
    provider["overview"][2]["value"] = str(len(delivery.get("backflow", {}).get("candidateFields", [])))
    if provider.get("resources"):
        provider["resources"][0]["status"] = resource.get("status", provider["resources"][0].get("status"))
        provider["resources"][0]["updatedAt"] = resource.get("updatedAt", provider["resources"][0].get("updatedAt"))
    provider["repository"] = {
        "packageCount": len(packages),
        "resourceCatalogCode": resource.get("repository", {}).get("catalogCode"),
        "deliveryReceiptCount": len(delivery.get("receipts", [])),
    }
    return provider


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_provider_view(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _get_provider_view(brain)

