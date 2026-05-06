from __future__ import annotations

import pytest

from zw_brain.domain.policy import (
    DomainAccessDeniedError,
    actor_for_role,
    enforce_manifest_policy,
    permissions_for_role,
    resolve_role,
)


def test_resolve_role_rejects_unknown_role() -> None:
    with pytest.raises(DomainAccessDeniedError):
        resolve_role("rx", "r1")


def test_actor_for_role_maps_government_actor_urn() -> None:
    assert actor_for_role("r1") == "user:gov:r1:周处长"


def test_permissions_for_role_returns_declared_capabilities() -> None:
    assert "request.create.execute" in permissions_for_role("r1")
    assert "approval.review_decide.execute" not in permissions_for_role("r1")


def test_enforce_manifest_policy_rejects_missing_permission() -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["approval.review_decide.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("approval.review_decide", manifest, "r1", {"confirmed": True})


def test_enforce_manifest_policy_rejects_cross_tenant_payload() -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["request.create.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("request.create", manifest, "r1", {"confirmed": True, "tenant_id": "external"})


@pytest.mark.parametrize("tenant_id", ["", 0, False])
def test_enforce_manifest_policy_rejects_falsy_tenant_payload(tenant_id: object) -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["request.create.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("request.create", manifest, "r1", {"confirmed": True, "tenant_id": tenant_id})


def test_enforce_manifest_policy_allows_unscoped_read_without_role_payload() -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": ["data.search.execute"],
    }
    enforce_manifest_policy("data.search", manifest, "r1", {})
