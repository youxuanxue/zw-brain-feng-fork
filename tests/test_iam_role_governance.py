"""D62 角色分派与角色治理回归 —— zw-brain 自建授权（IAM 只认证）。

钉死：
- 仓储单边写：assign/revoke/set_actor_status 幂等、按 (actor,org,role) 收口。
- A0 堵停用洞：disabled actor 再登录 fail-closed（ActorDisabledError），不复活、不新插 active 行；
  resolve_trusted_role 对 disabled 快照拒绝。iam_account_missing 仍可正常认领。
- 能力端到端：actor.list / role.assign / role.revoke / status.set / access_matrix 经 invoke_skill
  全链路（策略门 + 审计）；角色门 ROLE_SYSTEM 独占，其它角色 403。
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._iaf_rest_http import (
    KeyFixture,
    bootstrap_iaf_runtime,
    http_request,
    mint_bearer,
    run_server,
    stop_server,
)
from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService, BrainServiceError
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.policy import DomainAccessDeniedError
from zw_brain.domain.repositories.governance_projection import (
    ActorDisabledError,
    GovernanceProjectionRepository,
)
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.session_context import resolve_trusted_role
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


def _service(tmp: str) -> BrainService:
    os.environ["ZW_BRAIN_DB_PATH"] = str(Path(tmp) / "zw_brain.db")
    ensure_runtime_schema()
    database_store = DatabaseStore()
    audit_bus.configure_sink(database_store.append_audit_event)
    return BrainService(state_store=StateStore(database_store=database_store))


def _seed_org(repo, org_code="ORG-A"):
    # R-005: assign_actor_role now validates org_code against org_projection; seed the org.
    repo.upsert_org({"org_code": org_code, "org_name": org_code}, tenant_id=TENANT)


def _seed_actor(repo, *, external, account, status="active", org_code="ORG-A", as_iaf=True):
    _seed_org(repo, org_code)
    profile = {"account": account, "preferred_username": account}
    if as_iaf:
        source_ref = "iaf:claims"
        profile["iaf_sub"] = external
    else:
        source_ref = f"dsp-bsp:pub_user:{external}"
        profile["legacy_actor_ref"] = external
    return repo.upsert_actor(
        {
            "external_actor_id": external,
            "display_name": account,
            "org_code": org_code,
            "role_codes": [],
            "status": status,
            "source_ref": source_ref,
            "profile_json": profile,
        },
        tenant_id=TENANT,
    )


# ── 仓储单边写 ────────────────────────────────────────────────────────────
def test_assign_then_revoke_binding_idempotent() -> None:
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-1", account="zhangsan")

        b = repo.assign_actor_role(external_actor_id="iaf-1", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT, granted_by="ops")
        assert b.binding_status == "active"
        # 幂等：再 assign 不重复建行
        repo.assign_actor_role(external_actor_id="iaf-1", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT, granted_by="ops")
        active = [x for x in repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-1") if x.binding_status == "active"]
        assert len(active) == 1

        assert repo.revoke_actor_role(external_actor_id="iaf-1", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT) is True
        active = [x for x in repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-1") if x.binding_status == "active"]
        assert active == []
        # 再 revoke 幂等返回 False
        assert repo.revoke_actor_role(external_actor_id="iaf-1", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT) is False


def test_set_actor_status_disable_enable_keeps_bindings() -> None:
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-2", account="lisi")
        repo.assign_actor_role(external_actor_id="iaf-2", org_code="ORG-A", role_code="ROLE_ORGAN_MANAGER", tenant_id=TENANT, granted_by="ops")

        repo.set_actor_status(external_actor_id="iaf-2", status="disabled", tenant_id=TENANT)
        assert repo.get_actor("iaf-2", tenant_id=TENANT).status == "disabled"
        # 绑定保留，启用即恢复
        assert [x.role_code for x in repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-2", binding_status="active")] == ["ROLE_ORGAN_MANAGER"]
        repo.set_actor_status(external_actor_id="iaf-2", status="active", tenant_id=TENANT)
        assert repo.get_actor("iaf-2", tenant_id=TENANT).status == "active"


# ── A0 堵停用洞 ──────────────────────────────────────────────────────────
def test_disabled_existing_sub_relogin_fails_closed() -> None:
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-existing", account="wangwu", status="disabled", as_iaf=True)
        with pytest.raises(ActorDisabledError):
            repo.claim_legacy_actor_by_iaf(iaf_sub="iaf-existing", match_claims={"sub": "iaf-existing"}, tenant_id=TENANT)
        # 仍是 disabled，未被复活成 active
        assert repo.get_actor("iaf-existing", tenant_id=TENANT).status == "disabled"


def test_disabled_legacy_match_does_not_mint_fresh_active() -> None:
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="LEGACY-1", account="zhaoliu", status="disabled", as_iaf=False)
        before = len(repo.list_actors(tenant_id=TENANT))
        with pytest.raises(ActorDisabledError):
            repo.claim_legacy_actor_by_iaf(
                iaf_sub="iaf-new",
                match_claims={"preferred_username": "zhaoliu"},
                claims_profile={"username": "zhaoliu"},
                tenant_id=TENANT,
            )
        # 没有新插一行 active
        assert len(repo.list_actors(tenant_id=TENANT)) == before


def test_iam_account_missing_still_claims() -> None:
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="LEGACY-2", account="sunqi", status="iam_account_missing", as_iaf=False)
        record, outcome = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iaf-sun",
            match_claims={"preferred_username": "sunqi"},
            claims_profile={"username": "sunqi"},
            tenant_id=TENANT,
        )
        assert outcome == "rekeyed_legacy"
        assert record.status == "active"


def test_resolve_trusted_role_rejects_disabled_snapshot() -> None:
    with pytest.raises(DomainAccessDeniedError):
        resolve_trusted_role(
            {},
            actor_snapshot={
                "status": "disabled",
                "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER"}],
            },
        )


# ── 能力端到端 + 角色门 ──────────────────────────────────────────────────
def test_assign_list_revoke_e2e_with_audit_and_role_gate() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-9", account="qianba")

        # 非平台运维员被拒（角色门）—— brain 将 policy 的 DomainAccessDeniedError 包成 AccessDeniedError
        with pytest.raises(AccessDeniedError):
            invoke_trusted(
                service,
                "governance.actor.role.assign",
                {"external_actor_id": "iaf-9", "org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "confirmed": True},
                role="ROLE_ORGAN_OPERATER",
            )

        # 平台运维员分派成功，带 audit_id
        assigned = invoke_trusted(
            service,
            "governance.actor.role.assign",
            {"external_actor_id": "iaf-9", "org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "confirmed": True},
            role="ROLE_SYSTEM",
        )
        assert assigned["result"]["ok"] is True
        assert assigned["audit_id"]

        # 列表反映新角色（来自 binding，非 token）
        listed = service.invoke_skill("governance.actor.list", {"role": "ROLE_SYSTEM"})
        item = next(it for it in listed["items"] if it["external_actor_id"] == "iaf-9")
        assert "ROLE_ORGAN_OPERATER" in item["role_codes"]

        # 撤销
        revoked = invoke_trusted(
            service,
            "governance.actor.role.revoke",
            {"external_actor_id": "iaf-9", "org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "confirmed": True},
            role="ROLE_SYSTEM",
        )
        assert revoked["result"]["revoked"] is True
        listed2 = service.invoke_skill("governance.actor.list", {"role": "ROLE_SYSTEM"})
        item2 = next(it for it in listed2["items"] if it["external_actor_id"] == "iaf-9")
        assert "ROLE_ORGAN_OPERATER" not in item2["role_codes"]


def test_assign_to_disabled_actor_rejected_e2e() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-dis", account="zhoujiu", status="disabled")
        with pytest.raises(BrainServiceError):
            invoke_trusted(
                service,
                "governance.actor.role.assign",
                {"external_actor_id": "iaf-dis", "org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "confirmed": True},
                role="ROLE_SYSTEM",
            )


def test_backfill_creates_missing_bindings_from_role_codes() -> None:
    """D62 A4: an actor whose roles only live in role_codes_json (pre-D62 token-derived
    snapshot, no binding) gets active bindings backfilled so the binding-authoritative
    gates keep granting them after the cutover. Idempotent."""
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        # iaf:claims upsert with role_codes but (per A1b) no binding sync → roles only in snapshot
        repo.upsert_actor(
            {
                "external_actor_id": "iaf-bf",
                "display_name": "bf",
                "org_code": "ORG-A",
                "role_codes": ["ROLE_BUSIAUDIT"],
                "status": "active",
                "source_ref": "iaf:claims",
                "profile_json": {"iaf_sub": "iaf-bf"},
            },
            tenant_id=TENANT,
        )
        assert repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-bf", binding_status="active") == []

        from scripts.backfill_actor_bindings import main as backfill

        assert backfill(["--tenant-id", TENANT, "--apply"]) == 0
        roles = [b.role_code for b in repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-bf", binding_status="active")]
        assert roles == ["ROLE_BUSIAUDIT"]
        # idempotent re-run
        assert backfill(["--tenant-id", TENANT, "--apply"]) == 0
        roles2 = [b.role_code for b in repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iaf-bf", binding_status="active")]
        assert roles2 == ["ROLE_BUSIAUDIT"]


def test_status_set_and_access_matrix_e2e() -> None:
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-st", account="status-user")

        disabled = invoke_trusted(
            service,
            "governance.actor.status.set",
            {"external_actor_id": "iaf-st", "status": "disabled", "confirmed": True},
            role="ROLE_SYSTEM",
        )
        assert disabled["result"]["status"] == "disabled"
        assert repo.get_actor("iaf-st", tenant_id=TENANT).status == "disabled"

        matrix = service.invoke_skill("governance.access_matrix", {"role": "ROLE_SYSTEM"})
        role_codes = {r["role_code"] for r in matrix["roles"]}
        assert "ROLE_SYSTEM" in role_codes
        # 矩阵从 policy 派生：ROLE_SYSTEM 至少持有身份治理能力
        sys_caps = next(r["capabilities"] for r in matrix["roles"] if r["role_code"] == "ROLE_SYSTEM")
        assert any(c.startswith("governance.actor.role") for c in sys_caps)


# ── xj-review #303 fix-loop regressions ──────────────────────────────────────
def test_revoke_updates_role_codes_mirror_R002() -> None:
    """R-002: role_codes_json mirror must reflect POST-mutation active bindings (flush-before-read).
    revoke removes the role from the mirror; re-activate (assign of a disabled binding) restores it."""
    with TemporaryDirectory() as tmp:
        _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-m", account="mirror")
        repo.assign_actor_role(external_actor_id="iaf-m", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT, granted_by="t")
        repo.assign_actor_role(external_actor_id="iaf-m", org_code="ORG-A", role_code="ROLE_BUSIAUDIT", tenant_id=TENANT, granted_by="t")
        assert sorted(repo.get_actor("iaf-m", tenant_id=TENANT).role_codes_json) == ["ROLE_BUSIAUDIT", "ROLE_ORGAN_OPERATER"]
        repo.revoke_actor_role(external_actor_id="iaf-m", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT)
        # revoked role must be GONE from the mirror (the bug left it in)
        assert repo.get_actor("iaf-m", tenant_id=TENANT).role_codes_json == ["ROLE_BUSIAUDIT"]
        # re-activate the disabled binding → role restored in the mirror
        repo.assign_actor_role(external_actor_id="iaf-m", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT, granted_by="t")
        assert sorted(repo.get_actor("iaf-m", tenant_id=TENANT).role_codes_json) == ["ROLE_BUSIAUDIT", "ROLE_ORGAN_OPERATER"]


def test_assign_rejects_system_roles_R003() -> None:
    """R-003: backend only assigns the fixed product catalog (BUSINESS_ROLE_CODES); internal
    SYSTEM_ROLE_CODES (admin/system) are rejected even though they're in ACTOR_NAMES."""
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-sys", account="sysrole")
        for bad in ("admin", "system"):
            with pytest.raises(BrainServiceError):
                invoke_trusted(
                    service, "governance.actor.role.assign",
                    {"external_actor_id": "iaf-sys", "org_code": "ORG-A", "role_code": bad, "confirmed": True},
                    role="ROLE_SYSTEM",
                )


def test_assign_rejects_unknown_org_R005() -> None:
    """R-005: assign refuses a dangling org_code (no FK on the column; handler guards)."""
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-o", account="orgcheck")
        with pytest.raises(BrainServiceError):
            invoke_trusted(
                service, "governance.actor.role.assign",
                {"external_actor_id": "iaf-o", "target_org_code": "NO-SUCH-ORG", "role_code": "ROLE_BUSIAUDIT", "confirmed": True},
                role="ROLE_SYSTEM",
            )


def test_read_caps_deny_non_system_role_R009() -> None:
    """R-009: governance.actor.list / access_matrix are ROLE_SYSTEM-only — non-SYSTEM denied."""
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        for cap in ("governance.actor.list", "governance.access_matrix"):
            with pytest.raises((AccessDeniedError, DomainAccessDeniedError)):
                service.invoke_skill(cap, {"role": "ROLE_ORGAN_OPERATER"})


def test_browser_session_live_disable_R001() -> None:
    """R-001: enrich_actor_snapshot_for_session refreshes LIVE actor.status, so a mid-session
    disable is honored by the browser BFF gate (resolve_trusted_role rejects disabled)."""
    with TemporaryDirectory() as tmp:
        service = _service(tmp)
        repo = GovernanceProjectionRepository()
        _seed_actor(repo, external="iaf-live", account="live")
        repo.assign_actor_role(external_actor_id="iaf-live", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id=TENANT, granted_by="t")
        base = {"subject": "iaf-live", "tenant_id": TENANT, "org_code": "ORG-A", "status": "active"}
        # active → enrich keeps active, role resolvable
        snap = service.enrich_actor_snapshot_for_session(dict(base))
        assert snap["status"] == "active"
        assert resolve_trusted_role({}, actor_snapshot=snap) == "ROLE_ORGAN_OPERATER"
        # disable mid-session → re-enrich reflects disabled → gate denies
        repo.set_actor_status(external_actor_id="iaf-live", status="disabled", tenant_id=TENANT)
        snap2 = service.enrich_actor_snapshot_for_session(dict(base))
        assert snap2["status"] == "disabled"
        with pytest.raises(DomainAccessDeniedError):
            resolve_trusted_role({}, actor_snapshot=snap2)


def test_token_roles_ignored_binding_is_authority_R006() -> None:
    """R-006: product authz roles come from actor_org_role_binding, NOT the IAM token.
    (a) token carries a role but NO active binding → denied; (b) token role X, binding role Y → Y wins."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            repo = GovernanceProjectionRepository()
            # (a) token says ROLE_SECURITY_AUDIT; revoke the harness-seeded binding → no active binding
            token = mint_bearer(keys, roles=["ROLE_SECURITY_AUDIT"])
            repo.revoke_actor_role(external_actor_id="bearer-user", org_code="ORG-A", role_code="ROLE_SECURITY_AUDIT", tenant_id="sd-default")
            status, _, _ = http_request("GET", f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                                        headers={"Authorization": f"Bearer {token}"})
            assert status == 403, "token role must NOT grant access without a binding"
            # (b) divergence: token=operator, binding=auditor → auditor (binding) wins → audit read allowed
            token2 = mint_bearer(keys, roles=["ROLE_ORGAN_OPERATER"], sub="bearer-div")
            repo.revoke_actor_role(external_actor_id="bearer-div", org_code="ORG-A", role_code="ROLE_ORGAN_OPERATER", tenant_id="sd-default")
            repo.assign_actor_role(external_actor_id="bearer-div", org_code="ORG-A", role_code="ROLE_SECURITY_AUDIT", tenant_id="sd-default", granted_by="t")
            status2, _, _ = http_request("GET", f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                                         headers={"Authorization": f"Bearer {token2}"})
            assert status2 == 200, "binding role (auditor) must win over token role (operator)"
        finally:
            stop_server(server, thread)


def test_disabled_actor_denied_at_bearer_gate_R007() -> None:
    """R-007: a logged-in actor disabled mid-session is denied on the live bearer gate
    (bindings stay intact by design; the status short-circuit drops roles)."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        keys = KeyFixture()
        server, thread, port = run_server()
        try:
            repo = GovernanceProjectionRepository()
            token = mint_bearer(keys, roles=["ROLE_SECURITY_AUDIT"])  # seeds active auditor binding
            ok, _, _ = http_request("GET", f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                                    headers={"Authorization": f"Bearer {token}"})
            assert ok == 200
            repo.set_actor_status(external_actor_id="bearer-user", status="disabled", tenant_id="sd-default")
            denied, _, _ = http_request("GET", f"http://127.0.0.1:{port}/api/skills/audit.event.query",
                                        headers={"Authorization": f"Bearer {token}"})
            assert denied == 403, "disabled actor must be denied on the bearer gate despite intact bindings"
        finally:
            stop_server(server, thread)
