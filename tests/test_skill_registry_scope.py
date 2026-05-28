from __future__ import annotations

import pytest

from zw_brain.capability_registry.runtime import (
    JOURNEYS,
    STATUS_DEFERRED_RE,
    STATUS_LITERALS,
    SURFACES,
    SurfaceNotEnabledError,
    is_surface_enabled,
    load_manifests,
    require_surface,
    validate_manifest,
)


def _base_manifest(**overrides):
    manifest = {
        "slug": "test.skill",
        "compatibility": ["api"],
        "runtime_binding": {
            "kind": "brain_service",
            "surface_entry": "zw_brain.command.brain.BrainService.invoke_skill",
            "method": "test.skill",
        },
        "product_scope": {"journey": "j1", "status": "live"},
    }
    manifest.update(overrides)
    return manifest


def test_validate_manifest_rejects_missing_product_scope():
    manifest = _base_manifest()
    manifest.pop("product_scope")
    with pytest.raises(ValueError, match="missing required product_scope"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_illegal_journey():
    manifest = _base_manifest(product_scope={"journey": "j9", "status": "live"})
    with pytest.raises(ValueError, match="product_scope.journey"):
        validate_manifest(manifest)


def test_validate_manifest_rejects_illegal_status():
    manifest = _base_manifest(
        product_scope={"journey": "j1", "status": "deferred:wave-5"}
    )
    with pytest.raises(ValueError, match="product_scope.status"):
        validate_manifest(manifest)


def test_load_manifests_all_registered_contracts_pass_scope_check():
    # load_manifests() calls validate_manifest() internally; if any manifest is invalid it raises.
    # Beyond that guarantee, assert the resulting product_scope of every contract is well-formed,
    # so a manifest that somehow bypassed validation can't silently carry a bad journey/status.
    manifests = load_manifests()
    assert manifests, "registry is empty"
    for skill_id, manifest in manifests.items():
        scope = manifest.get("product_scope")
        assert isinstance(scope, dict), f"{skill_id} missing product_scope"
        assert scope.get("journey") in JOURNEYS, f"{skill_id} bad journey {scope.get('journey')!r}"
        status = scope.get("status")
        assert status in STATUS_LITERALS or STATUS_DEFERRED_RE.match(status or ""), (
            f"{skill_id} bad status {status!r}"
        )


def test_require_surface_refuses_non_live_skills_on_every_surface():
    """Defense-in-depth: every non-live registered skill must be rejected by require_surface
    on every surface its compatibility list claims, mirroring the export-time is_live filter.
    Without this, deferred/external manifests stay reachable via runtime path-based dispatch
    (e.g. POST /api/skills/<id>) even after they vanish from openapi.json / agent_card.json.
    """
    manifests = load_manifests()
    non_live = {
        sid: m
        for sid, m in manifests.items()
        if (m.get("product_scope") or {}).get("status") != "live"
    }
    assert non_live, "expected at least one non-live manifest in the registry"

    leaks: list[tuple[str, str, str]] = []
    for skill_id, manifest in non_live.items():
        status = (manifest.get("product_scope") or {}).get("status")
        for surface in SURFACES:
            if not is_surface_enabled(manifest, surface):
                continue
            try:
                require_surface(skill_id, surface)
            except SurfaceNotEnabledError:
                continue
            leaks.append((skill_id, surface, status))

    assert not leaks, (
        f"{len(leaks)} non-live skill/surface pairs reachable via require_surface "
        f"(first 5: {leaks[:5]})"
    )


def test_require_surface_still_accepts_live_skills():
    """Sanity: the new status gate must not regress live skills on enabled surfaces."""
    manifests = load_manifests()
    live = [
        (sid, m)
        for sid, m in manifests.items()
        if (m.get("product_scope") or {}).get("status") == "live"
    ]
    assert live, "expected at least one live manifest in the registry"
    sample = live[:5]
    for skill_id, manifest in sample:
        for surface in SURFACES:
            if not is_surface_enabled(manifest, surface):
                continue
            require_surface(skill_id, surface)
