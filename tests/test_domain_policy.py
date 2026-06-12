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
        resolve_role("rx", "ROLE_ORGAN_OPERATER")


def test_actor_for_role_maps_government_actor_urn() -> None:
    assert actor_for_role("ROLE_ORGAN_OPERATER") == "user:gov:ROLE_ORGAN_OPERATER:部门操作员"


def test_permissions_for_role_returns_declared_capabilities() -> None:
    assert "request.create.execute" in permissions_for_role("ROLE_ORGAN_OPERATER")
    assert "approval.review_decide.execute" not in permissions_for_role("ROLE_ORGAN_OPERATER")


def test_enforce_manifest_policy_rejects_missing_permission() -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["approval.review_decide.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("approval.review_decide", manifest, "ROLE_ORGAN_OPERATER", {"confirmed": True})


def test_enforce_manifest_policy_rejects_cross_tenant_payload() -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["request.create.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("request.create", manifest, "ROLE_ORGAN_OPERATER", {"confirmed": True, "tenant_id": "external"})


@pytest.mark.parametrize("tenant_id", ["", 0, False])
def test_enforce_manifest_policy_rejects_falsy_tenant_payload(tenant_id: object) -> None:
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": ["db_write"],
        "human_confirmation_required": True,
        "permissions": ["request.create.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("request.create", manifest, "ROLE_ORGAN_OPERATER", {"confirmed": True, "tenant_id": tenant_id})


def test_enforce_manifest_policy_allows_authorized_read_without_role_payload() -> None:
    # C1: a permissioned read-only cap passes with an EMPTY payload (no "role" key) ONLY
    # because the RESOLVED role is authorized for it — not because the check is skipped.
    # ROLE_ORGAN_OPERATER holds data.search.execute, so it passes.
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": ["data.search.execute"],
    }
    enforce_manifest_policy("data.search", manifest, "ROLE_ORGAN_OPERATER", {})


def test_enforce_manifest_policy_denies_underprivileged_read_without_role_payload() -> None:
    # C1 negative: the same empty-payload (no "role" key) read is DENIED when the resolved
    # role lacks the permission. Previously the `"role" not in payload` escape skipped the
    # check entirely, letting low-privilege callers read SECURITY_AUDIT-only capabilities.
    manifest = {
        "tenant_scope": "global",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": ["audit.event.query.execute"],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("audit.event.query", manifest, "ROLE_ORGAN_OPERATER", {})


def test_reverse_draft_suggest_dead_read_revoked_for_busiaudit() -> None:
    # D57⑧ 收尾（#259 未尽清单第 3 项）：suggest（智能预填）唯一消费面是反向编目向导
    # （路由仅 OPERATER/MANAGER）；BUSIAUDIT 退出 draft 阶段审核后该读权成死权 → 回收钉死。
    perm = "catalog.entry.reverse_draft.suggest.execute"
    assert perm in permissions_for_role("ROLE_ORGAN_OPERATER")
    assert perm in permissions_for_role("ROLE_ORGAN_MANAGER")
    assert perm not in permissions_for_role("ROLE_BUSIAUDIT")
    manifest = {
        "tenant_scope": "tenant",
        "side_effects": [],
        "human_confirmation_required": False,
        "permissions": [perm],
    }
    with pytest.raises(DomainAccessDeniedError):
        enforce_manifest_policy("catalog.entry.reverse_draft.suggest", manifest, "ROLE_BUSIAUDIT", {})
    # 正向双面：向导双角色仍可用（防止回收误伤活权）。
    enforce_manifest_policy("catalog.entry.reverse_draft.suggest", manifest, "ROLE_ORGAN_OPERATER", {})
    enforce_manifest_policy("catalog.entry.reverse_draft.suggest", manifest, "ROLE_ORGAN_MANAGER", {})
