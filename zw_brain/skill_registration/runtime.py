from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY_DIR = Path(__file__).with_name("registered")


def load_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        manifests[data["skill_id"]] = data
    return manifests


def get_manifest(skill_id: str) -> dict[str, Any]:
    manifests = load_manifests()
    if skill_id not in manifests:
        raise KeyError(skill_id)
    return manifests[skill_id]
