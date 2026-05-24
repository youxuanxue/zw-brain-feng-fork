"""B1 registry handlers — 1 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zw_brain.command.brain import BrainService



# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _export_registry_artifacts(brain) -> dict[str, Any]:
    manifests = brain.manifests()
    packages = brain.list_packages()
    return {"items": list(manifests.values()), "packages": packages, "total": len(manifests), "summary": {"skill_count": len(manifests), "package_count": len(packages)}}


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_registry_artifact_export(brain: BrainService, skill_id: str, payload: dict[str, Any]) -> Any:
    return _export_registry_artifacts(brain)

