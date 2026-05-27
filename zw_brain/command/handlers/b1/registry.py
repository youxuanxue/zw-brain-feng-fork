"""B1 registry handlers — 1 cap migrated from BrainService (F1 turn 5).

Method bodies physically migrated (`self.` → `brain.`); per-cap handler functions
registered in `zw_brain.command.dispatch.DISPATCH_TABLE`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zw_brain.command.deps import HandlerDeps, SkillContext

if TYPE_CHECKING:
    pass



# ──────────────────────────────────────────────────────────────────────────
# Migrated method bodies
# ──────────────────────────────────────────────────────────────────────────

def _export_registry_artifacts(brain, deps, ctx) -> dict[str, Any]:
    manifests = brain.manifests()
    packages = brain.list_packages()
    return {"items": list(manifests.values()), "packages": packages, "total": len(manifests), "summary": {"skill_count": len(manifests), "package_count": len(packages)}}


# ──────────────────────────────────────────────────────────────────────────
# Handler entrypoints
# ──────────────────────────────────────────────────────────────────────────

def handler_registry_artifact_export(deps: HandlerDeps, ctx: SkillContext, payload: dict[str, Any]) -> Any:
    brain = deps.brain_legacy if deps is not None else None  # Action A: backward-compat alias; lifted in Action B together with SkillPipeline.
    skill_id = ctx.skill_id
    return _export_registry_artifacts(brain, deps, ctx)

