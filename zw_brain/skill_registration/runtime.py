from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path(__file__).with_name("registered")
SURFACES = {"webui", "api", "cli", "mcp", "a2a"}
JOURNEYS = {"j1", "j2", "b1", "infra", "external", "national"}
STATUS_LITERALS = {"live", "external"}
STATUS_DEFERRED_RE = re.compile(r"^deferred:wave-[1-4]$")


class SurfaceNotEnabledError(PermissionError):
    pass


def load_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        validate_manifest(data)
        manifests[data["skill_id"]] = data
    return manifests


def get_manifest(skill_id: str) -> dict[str, Any]:
    manifests = load_manifests()
    if skill_id not in manifests:
        raise KeyError(skill_id)
    return manifests[skill_id]


def compatibility(manifest: dict[str, Any]) -> set[str]:
    values = manifest.get("compatibility", [])
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def is_surface_enabled(manifest: dict[str, Any], surface: str) -> bool:
    if surface not in SURFACES:
        raise ValueError(f"unknown surface: {surface}")
    return surface in compatibility(manifest)


def require_surface(skill_id: str, surface: str) -> dict[str, Any]:
    manifest = get_manifest(skill_id)
    if not is_surface_enabled(manifest, surface):
        raise SurfaceNotEnabledError(f"{skill_id} is not exposed on {surface}")
    # Defense-in-depth aligned with export_agent_contract.is_live: non-live skills are
    # already removed from openapi/agent_card/runtime_bindings/mcp projections; this
    # second gate ensures the runtime handler also refuses them even if an old client
    # still has a cached path or someone crafts the URL directly.
    scope = manifest.get("product_scope") or {}
    status = scope.get("status")
    if status != "live":
        raise SurfaceNotEnabledError(f"{skill_id} is not live (status={status!r})")
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    skill_id = manifest.get("skill_id")
    if not skill_id:
        raise ValueError("skill manifest missing skill_id")
    unknown = compatibility(manifest) - SURFACES
    if unknown:
        raise ValueError(f"{skill_id} has unknown compatibility surfaces: {', '.join(sorted(unknown))}")
    runtime_binding = manifest.get("runtime_binding", {})
    method = runtime_binding.get("method")
    if method and method != skill_id:
        raise ValueError(f"{skill_id} runtime_binding.method must equal skill_id")
    product_scope = manifest.get("product_scope")
    if not isinstance(product_scope, dict):
        raise ValueError(f"{skill_id} missing required product_scope field")
    journey = product_scope.get("journey")
    if journey not in JOURNEYS:
        raise ValueError(
            f"{skill_id} product_scope.journey must be one of {sorted(JOURNEYS)}, got {journey!r}"
        )
    status = product_scope.get("status")
    if status not in STATUS_LITERALS and not (
        isinstance(status, str) and STATUS_DEFERRED_RE.match(status)
    ):
        raise ValueError(
            f"{skill_id} product_scope.status must be 'live' / 'external' / 'deferred:wave-[1-4]', got {status!r}"
        )
