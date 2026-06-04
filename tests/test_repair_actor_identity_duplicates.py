"""scripts/repair_actor_identity_duplicates.py 的工具测试（不进 feature 头）。

钉死：dry-run 零写、apply 正确合并双行、二次 apply 幂等、unmatched/ambiguous 只报告不动数据、
delete_actor_row 守卫拒删非 iaf:claims 行。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._iaf_rest_http import bootstrap_iaf_runtime
from zw_brain.domain.repositories.governance_projection import (
    ActorMatchError,
    GovernanceProjectionRepository,
)

TENANT = "sd-default"
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_actor_identity_duplicates.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("repair_actor_identity_duplicates", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _seed_legacy(repo: GovernanceProjectionRepository, *, external: str, account: str, status: str = "iam_account_missing"):
    return repo.upsert_actor(
        {
            "external_actor_id": external,
            "display_name": account,
            "role_codes": [],
            "status": status,
            "source_ref": f"dsp-bsp:pub_user:{external}",
            "profile_json": {"account": account, "preferred_username": account, "legacy_actor_ref": external},
        },
        tenant_id=TENANT,
    )


def _seed_thin_login_row(repo: GovernanceProjectionRepository, *, sub: str, username: str):
    # Mimic the pre-fix duplicate: a sub-keyed iaf:claims row created by the old login path.
    return repo.upsert_actor(
        {
            "external_actor_id": sub,
            "iaf_sub": sub,
            "display_name": username,
            "role_codes": [],
            "status": "active",
            "source_ref": "iaf:claims",
            "profile_json": {"username": username, "iaf_sub": sub},
        },
        tenant_id=TENANT,
    )


def test_dry_run_writes_nothing_but_reports_plan() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        _seed_legacy(repo, external="USER1", account="zhangsan")
        _seed_thin_login_row(repo, sub="iam-sub-1", username="zhangsan")
        before = {(a.external_actor_id, a.status) for a in repo.list_actors(tenant_id=TENANT)}

        module = _load_script()
        rc = module.main(["--dry-run"])

        assert rc == 0
        after = {(a.external_actor_id, a.status) for a in repo.list_actors(tenant_id=TENANT)}
        assert after == before  # nothing changed


def test_apply_merges_duplicate_into_single_row_and_is_idempotent() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        legacy = _seed_legacy(repo, external="USER1", account="zhangsan")
        repo.sync_actor_bindings(legacy, [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER"}], batch_no="seed")
        _seed_thin_login_row(repo, sub="iam-sub-1", username="zhangsan")
        assert len(repo.list_actors(tenant_id=TENANT)) == 2

        module = _load_script()
        rc = module.main(["--apply"])
        assert rc == 0

        actors = repo.list_actors(tenant_id=TENANT)
        assert len(actors) == 1
        merged = actors[0]
        assert merged.external_actor_id == "iam-sub-1"
        assert merged.id == legacy.id  # legacy row kept (rich), thin deleted
        assert merged.profile_json["account"] == "zhangsan"
        # bindings followed the rekey
        active = repo.list_actor_org_role_bindings(tenant_id=TENANT, external_actor_id="iam-sub-1", binding_status="active")
        assert {(b.org_code, b.role_code) for b in active} == {("ORG-A", "ROLE_ORGAN_OPERATER")}

        # second apply is a no-op
        rc2 = module.main(["--apply"])
        assert rc2 == 0
        assert len(repo.list_actors(tenant_id=TENANT)) == 1


def test_unmatched_and_ambiguous_are_reported_not_mutated() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        # unmatched: thin row whose username has no legacy twin
        _seed_thin_login_row(repo, sub="iam-sub-x", username="nobody")
        # ambiguous: two legacy rows share account "dup"
        _seed_legacy(repo, external="USERA", account="dup")
        _seed_legacy(repo, external="USERB", account="dup")
        _seed_thin_login_row(repo, sub="iam-sub-dup", username="dup")
        before = {a.external_actor_id for a in repo.list_actors(tenant_id=TENANT)}

        module = _load_script()
        report = Path(tmp) / "report.json"
        rc = module.main(["--apply", "--json-report", str(report)])

        assert rc == 1  # needs-human
        after = {a.external_actor_id for a in repo.list_actors(tenant_id=TENANT)}
        assert after == before  # neither unmatched nor ambiguous touched
        assert report.exists()


def test_delete_guard_refuses_non_thin_rows() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        repo = GovernanceProjectionRepository()
        _seed_legacy(repo, external="USER1", account="zhangsan")
        with pytest.raises(ActorMatchError):
            repo.delete_actor_row("USER1", tenant_id=TENANT, source_ref_guard="iaf:claims")
        # row still present
        assert repo._get_actor("USER1", tenant_id=TENANT) is not None
