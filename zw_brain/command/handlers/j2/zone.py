"""J2 zone handlers — 3 cap migrated from BrainService (F1 turn 4).

Method bodies physically migrated; `self.` → `brain.` substitution applied. Per-cap handler
functions registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService

from zw_brain.command.brain import NotFoundError

# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _list_zones(brain) -> list[dict[str, Any]]:
    zones = copy.deepcopy(brain._snapshot["zones"])
    resource_id = brain._provider_primary_resource_id()
    resource = brain.get_resource(resource_id) if resource_id else {}
    for zone in zones:
        if zone["id"] == "business":
            zone["repository"] = {
                "resourceCatalogCode": resource.get("repository", {}).get("catalogCode"),
                "resourceLifecycleStatus": resource.get("repository", {}).get("lifecycleStatus"),
            }
    return zones

def _get_zone(brain, zone_id: str) -> dict[str, Any]:
    for item in brain.list_zones():
        if item["id"] == zone_id:
            return copy.deepcopy(item)
    raise NotFoundError(zone_id)

def _publish_zone_topic_projection(brain, zone_id: str, role: str, confirmed: bool) -> dict[str, Any]:
    zone = brain._zone_by_id(zone_id)

    def mutation(audit_id: str, actor: str) -> dict[str, Any]:
        zone["status"] = "已发布"
        zone["projectionLocked"] = True
        if "模板版本：v1.3，默认入口已同步" not in zone.get("trust", []):
            zone.setdefault("trust", []).append("模板版本：v1.3，默认入口已同步")
        zone.setdefault("nextActions", [])
        if "继续作为默认复用入口" not in zone["nextActions"]:
            zone["nextActions"].insert(0, "继续作为默认复用入口")
        brain._append_audit_feed("zone.publish-topic-projection", zone_id, "ok", actor)
        return {"zone_id": zone_id, "status": zone["status"]}

    return brain._mutate("zone.publish_topic_projection", role, confirmed, {"zone_id": zone_id}, mutation)


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_zone_list(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return {"items": _list_zones(brain)}

def handler_zone_view(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _get_zone(brain, str(payload["zone_id"]))

def handler_zone_publish_topic_projection(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _publish_zone_topic_projection(brain, str(payload["zone_id"]), str(payload.get("role", brain._ui_state["role"])), bool(payload.get("confirmed")))

