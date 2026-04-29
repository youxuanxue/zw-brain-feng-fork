from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path(__file__).with_name("registered")
SURFACES = {"webui", "api", "cli", "mcp", "a2a"}


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
