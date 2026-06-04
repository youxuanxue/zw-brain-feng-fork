"""存量用户首次 IAM 登录的「单行身份认领」回归 —— backs infra-iam-session.feature。

修复前缺陷：存量行（pub_user.ID 键、iam_account_missing）首登被 upsert_actor 按 sub 另插一行，
形成两套用户数据。修复后登录/重导入统一走 GovernanceProjectionRepository.claim_legacy_actor_by_iaf：
辅助字段唯一命中即就地 rekey 存量行（同 PK、保 profile、搬 binding+mapping），多命中 fail-closed，
不认领 disabled 行，二次登录幂等。本测试在隔离临时库上逐条钉死这些不变量。
"""
from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import select

from tests._iaf_rest_http import bootstrap_iaf_runtime
from zw_brain.domain.models import LegacyObjectMappingRecord
from zw_brain.domain.repositories.governance_projection import (
    ActorMatchError,
    GovernanceProjectionRepository,
)
from zw_brain.shared.db import create_session_factory

TENANT = "sd-default"


def _mapping_canonical_refs(*, external_object_ref: str) -> list[str]:
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        rows = session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.tenant_id == TENANT,
                LegacyObjectMappingRecord.canonical_type == "ActorProjectionRecord",
                LegacyObjectMappingRecord.legacy_object_ref == external_object_ref,
            )
        ).scalars()
        return sorted(str(r.canonical_ref) for r in rows)


def _seed_legacy_actor(
    repo: GovernanceProjectionRepository,
    *,
    external: str,
    account: str,
    status: str = "iam_account_missing",
    org_code: str | None = None,
    phone: str | None = None,
    email: str | None = None,
):
    profile = {"account": account, "preferred_username": account, "legacy_actor_ref": external}
    if phone:
        profile["phone"] = phone
    if email:
        profile["email"] = email
    return repo.upsert_actor(
        {
            "external_actor_id": external,
            "display_name": account,
            "org_code": org_code,
            "role_codes": [],
            "status": status,
            "source_ref": f"dsp-bsp:pub_user:{external}",
            "profile_json": profile,
        },
        tenant_id=TENANT,
    )


def _seed_bindings(repo: GovernanceProjectionRepository, actor, specs: list[tuple[str, str]]) -> None:
    # sync_actor_bindings is replace-semantics — seed the whole set in ONE call.
    repo.sync_actor_bindings(actor, [{"org_code": o, "role_code": r} for o, r in specs], batch_no="seed")


def _seed_mapping(repo: GovernanceProjectionRepository, external: str) -> None:
    repo.upsert_legacy_object_mapping(
        {
            "legacy_system": "dsp-bsp",
            "legacy_object_type": "pub_user",
            "legacy_object_ref": external,
            "canonical_type": "ActorProjectionRecord",
            "canonical_ref": external,
            "source_ref": f"dsp-bsp:pub_user:{external}",
        },
        tenant_id=TENANT,
    )


def test_first_login_claims_legacy_row_by_account_keeps_single_row() -> None:
    """辅助 account 匹配命中存量行 → 就地 rekey，行数不变、PK 不变、bindings+mapping 跟着搬。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        legacy = _seed_legacy_actor(repo, external="USER1", account="zhangsan", org_code="ORG-A")
        _seed_bindings(repo, legacy, [("ORG-A", "ROLE_ORGAN_OPERATER")])
        _seed_mapping(repo, "USER1")
        assert len(repo.list_actors(tenant_id=TENANT)) == 1

        record, outcome = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-1",
            match_claims={"preferred_username": "zhangsan"},
            claims_profile={"username": "zhangsan", "email": "z@example.gov"},
            token_role_codes=[],
            tenant_id=TENANT,
        )

        assert outcome == "rekeyed_legacy"
        assert record.id == legacy.id  # same physical row
        assert record.external_actor_id == "iam-sub-1"
        assert record.status == "active"
        # single row — no parallel twin
        actors = repo.list_actors(tenant_id=TENANT)
        assert len(actors) == 1
        # legacy profile preserved + claims merged
        assert record.profile_json["account"] == "zhangsan"
        assert record.profile_json["legacy_actor_ref"] == "USER1"
        assert record.profile_json["iaf_sub"] == "iam-sub-1"
        assert record.profile_json["binding_status"] == "bound"
        assert record.profile_json.get("email") == "z@example.gov"
        # bindings rekeyed to the sub, still active; old key empty
        moved = repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iam-sub-1", binding_status="active")
        assert [(b.org_code, b.role_code) for b in moved] == [("ORG-A", "ROLE_ORGAN_OPERATER")]
        assert repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="USER1") == []
        # legacy_object_mapping.canonical_ref follows the rekey (no drift)
        assert _mapping_canonical_refs(external_object_ref="USER1") == ["iam-sub-1"]


def test_login_does_not_disable_imported_bindings() -> None:
    """登录认领只搬移 binding，绝不 disable 导入的多组织绑定（wave-0 D-2 deferral）。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        legacy = _seed_legacy_actor(repo, external="USER2", account="lisi", org_code="ORG-A")
        _seed_bindings(repo, legacy, [("ORG-A", "ROLE_ORGAN_OPERATER"), ("ORG-B", "ROLE_ORGAN_MANAGER")])

        repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-2",
            match_claims={"preferred_username": "lisi"},
            claims_profile={"username": "lisi"},
            token_role_codes=[],  # token carried no product roles
            tenant_id=TENANT,
        )

        active = repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iam-sub-2", binding_status="active")
        assert {(b.org_code, b.role_code) for b in active} == {
            ("ORG-A", "ROLE_ORGAN_OPERATER"),
            ("ORG-B", "ROLE_ORGAN_MANAGER"),
        }
        # nothing disabled
        assert all(b.binding_status == "active" for b in active)


def test_ambiguous_auxiliary_match_fails_closed_without_writing() -> None:
    """同一 account 命中多条可认领存量行 → ActorMatchError，不新建/不改任何行。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        _seed_legacy_actor(repo, external="USER3A", account="dup")
        _seed_legacy_actor(repo, external="USER3B", account="dup")
        before = {a.external_actor_id for a in repo.list_actors(tenant_id=TENANT)}

        with pytest.raises(ActorMatchError):
            repo.claim_legacy_actor_by_iaf(
                iaf_sub="iam-sub-3",
                match_claims={"preferred_username": "dup"},
                claims_profile={"username": "dup"},
                tenant_id=TENANT,
            )

        after = {a.external_actor_id for a in repo.list_actors(tenant_id=TENANT)}
        assert after == before  # no new row, no rekey


def test_disabled_legacy_row_is_not_claimed() -> None:
    """disabled 存量行不被认领（不继承其角色）→ 登录落为全新 sub 键行，disabled 行原样保留。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        disabled = _seed_legacy_actor(repo, external="USER4", account="banned", status="disabled")

        record, outcome = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-4",
            match_claims={"preferred_username": "banned"},
            claims_profile={"username": "banned"},
            tenant_id=TENANT,
        )

        assert outcome == "inserted_fresh"
        assert record.external_actor_id == "iam-sub-4"
        # disabled legacy row untouched
        kept = repo._get_actor("USER4", tenant_id=TENANT)
        assert kept is not None and kept.id == disabled.id and kept.status == "disabled"
        # two distinct rows now (the disabled legacy + the fresh login identity)
        assert len(repo.list_actors(tenant_id=TENANT)) == 2


def test_second_login_same_sub_is_idempotent() -> None:
    """同 sub 二次登录：sub 已自有行 → 原地刷新，不新增行。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        legacy = _seed_legacy_actor(repo, external="USER5", account="wangwu", org_code="ORG-A")
        _seed_bindings(repo, legacy, [("ORG-A", "ROLE_ORGAN_OPERATER")])

        first, outcome1 = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-5",
            match_claims={"preferred_username": "wangwu"},
            claims_profile={"username": "wangwu"},
            tenant_id=TENANT,
        )
        assert outcome1 == "rekeyed_legacy"
        count_after_first = len(repo.list_actors(tenant_id=TENANT))

        second, outcome2 = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-5",
            match_claims={"preferred_username": "wangwu"},
            claims_profile={"username": "wangwu"},
            tenant_id=TENANT,
        )
        assert outcome2 == "updated_existing_sub"
        assert second.id == first.id
        assert len(repo.list_actors(tenant_id=TENANT)) == count_after_first == 1
        # bindings untouched / still active
        active = repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iam-sub-5", binding_status="active")
        assert {(b.org_code, b.role_code) for b in active} == {("ORG-A", "ROLE_ORGAN_OPERATER")}


def test_token_roles_overwrite_role_codes_but_legacy_with_no_token_roles_preserved() -> None:
    """token 带产品角色 → 写入 role_codes_json；token 无角色 → 保留导入值（角色仍由 binding 现算）。"""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        _seed_legacy_actor(repo, external="USER6", account="zhao", org_code="ORG-A")

        record, _ = repo.claim_legacy_actor_by_iaf(
            iaf_sub="iam-sub-6",
            match_claims={"preferred_username": "zhao"},
            claims_profile={"username": "zhao"},
            token_role_codes=["ROLE_ORGAN_MANAGER"],
            tenant_id=TENANT,
        )
        assert list(record.role_codes_json or []) == ["ROLE_ORGAN_MANAGER"]
