# Wave: 1
# Journey: J1
# Pages: P5 provider / P3 application
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/repositories/legacy_mapping.py
#   zw_brain/domain/services/provider_service.py
#   zw_brain/domain/services/request_service.py
"""legacy_object_mapping scope-pushdown 守卫（HIGH-1 + MEDIUM-1）.

根因：`resource.api.query` / request 列表的 batch 预取此前用全表
`list_mappings()` 把整张 ~68k 行的 legacy_object_mapping 物化进 Python dict 再
按 canonical_ref 分组，而每页实际只读本页 resource_code / application_code 那几条。

本测试锁定下推后：
1. `list_mappings(canonical_refs=[...])` 的 IN 下推 == 旧的「逐 ref 单查再并集」（语义等价）；
2. provider 资产富化的 `legacy_object_mappings` 投影字节级不变（同 #182 byte-identical 断言）；
3. 下推后 provider 路径加载的 legacy 行数 == 本页 resource_code 命中的行数（不再全表）；
4. 空 scope（无 ref 在范围内）返回 []，不发查询、不全表回退。

自建小规模真库（reset_and_upgrade + 经 repository 真灌库），不依赖客户 dump seed。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHADOW_DB = REPO_ROOT / ".data" / "test_read_path_legacy_pushdown_shadow.db"
TENANT = "sd-default"


def _remove_shadow_db_files() -> None:
    for suffix in ("", "-wal", "-shm"):
        (SHADOW_DB.parent / f"{SHADOW_DB.name}{suffix}").unlink(missing_ok=True)


@pytest.fixture(scope="module", autouse=True)
def _shadow_db():
    SHADOW_DB.parent.mkdir(parents=True, exist_ok=True)
    from zw_brain.shared import db as _db

    _db.reset_engine_cache()
    _remove_shadow_db_files()
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade

    reset_and_upgrade()
    _seed(resources=24)
    yield
    _db.reset_engine_cache()
    _remove_shadow_db_files()
    os.environ.pop("ZW_BRAIN_DB_PATH", None)


def _seed(*, resources: int) -> None:
    """Seed resource assets + a legacy_object_mapping row per asset, plus a fat
    tail of unrelated mappings (other canonical_types) that a full-table scan
    would needlessly materialize."""
    from zw_brain.domain.repositories import (
        CatalogRepository,
        LegacyObjectMappingRepository,
        ResourceApiRepository,
    )

    cat_repo = CatalogRepository()
    asset_repo = ResourceApiRepository()
    legacy_repo = LegacyObjectMappingRepository()

    for ri in range(resources):
        code = f"basic-elem:p-{ri:04d}"
        cat_repo.upsert_from_resource(
            {
                "id": code,
                "name": f"测试目录 {ri}",
                "status": "active",
                "provider": f"org-{ri % 8}",
                "source_ref": f"p:catalog:{ri}",
                "legacy_object_ref": code,
            },
            tenant_id=TENANT,
        )
        rc = f"res-p-{ri:04d}"
        asset_repo.upsert_asset(
            {
                "resource_code": rc,
                "title": f"测试资源 {ri}",
                "resource_kind": "dataset",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{ri % 8}",
                "catalog_code": code,
                "source_ref": f"p:resource:{ri}",
                "legacy_object_ref": rc,
            },
            tenant_id=TENANT,
        )
        # one resource_asset legacy mapping keyed by the resource_code
        legacy_repo.upsert_mapping(
            {
                "source_ref": f"p:legacy:resource_asset:{ri}",
                "legacy_system": "DSP",
                "legacy_object_type": "dsp_resource",
                "legacy_object_ref": f"legacy-{rc}",
                "canonical_type": "resource_asset",
                "canonical_ref": rc,
            },
            tenant_id=TENANT,
        )

    # Fat tail: ~400 unrelated mappings (other canonical_types) a full-table
    # scan would load but no page on resource_code ever reads.
    for ti in range(400):
        legacy_repo.upsert_mapping(
            {
                "source_ref": f"p:legacy:tail:{ti}",
                "legacy_system": "DSP",
                "legacy_object_type": "service_invocation_metric",
                "legacy_object_ref": f"tail-legacy-{ti}",
                "canonical_type": "service_invocation_metric_projection",
                "canonical_ref": f"metric-{ti}",
            },
            tenant_id=TENANT,
        )


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss)


class _RowCounter:
    """Count how many legacy_object_mapping rows list_mappings materializes."""

    def __enter__(self):
        import zw_brain.domain.repositories.legacy_mapping as lm

        self.rows = 0
        self._orig = lm.LegacyObjectMappingRepository.list_mappings
        counter = self

        def wrapped(repo_self, **kw):
            out = counter._orig(repo_self, **kw)
            counter.rows += len(out)
            return out

        lm.LegacyObjectMappingRepository.list_mappings = wrapped  # type: ignore[method-assign]
        self._lm = lm
        return self

    def __exit__(self, *exc):
        self._lm.LegacyObjectMappingRepository.list_mappings = self._orig  # type: ignore[method-assign]


def _norm(value) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


# ── 1. repo IN-pushdown == per-ref union (semantic equivalence) ──

def test_canonical_refs_in_equals_per_ref_union():
    brain = _new_brain()
    repo = brain._state_store.database_store.legacy_mapping_repo
    refs = [f"res-p-{ri:04d}" for ri in range(8)]

    union = [
        m
        for ref in refs
        for m in repo.list_mappings(canonical_type="resource_asset", canonical_ref=ref, tenant_id=TENANT)
    ]
    pushed = repo.list_mappings(canonical_type="resource_asset", canonical_refs=refs, tenant_id=TENANT)

    def key(rows):
        return sorted((m.canonical_ref, m.legacy_object_ref, m.mapping_status) for m in rows)

    assert key(pushed) == key(union) and union, "IN pushdown != per-ref union"


def test_empty_canonical_refs_returns_empty_without_query():
    brain = _new_brain()
    repo = brain._state_store.database_store.legacy_mapping_repo
    with _RowCounter() as c:
        out = repo.list_mappings(canonical_type="resource_asset", canonical_refs=[], tenant_id=TENANT)
    assert out == []
    assert c.rows == 0, "empty canonical_refs should short-circuit, not full-scan"


# ── 2. provider asset enrich: byte-identical projection, scoped row load ──

def test_provider_enrich_legacy_mappings_byte_identical_and_scoped():
    brain = _new_brain()
    store = brain._state_store.database_store
    provider = brain._get_handler_deps().services.provider

    assets = store.resource_api_repo.list_assets(tenant_id=TENANT)[:10]
    items = [
        {"resource_code": a.resource_code, "lifecycle_status": a.lifecycle_status, "title": a.title}
        for a in assets
    ]

    with _RowCounter() as c:
        out = provider.enrich_resource_assets(items, store)
    scoped_rows = c.rows

    # Every asset's legacy_object_mappings projection is present + correct
    # (asset upsert auto-creates one resource_asset mapping; the seed adds
    # another — both keyed by resource_code, both must surface).
    by_code = {o["resource_code"]: o["legacy_object_mappings"] for o in out}
    for a in assets:
        mapped = by_code[a.resource_code]
        assert mapped, f"{a.resource_code} should resolve its resource_asset mapping(s)"
        assert all(m["canonical_ref"] == a.resource_code for m in mapped)

    # Scope pushdown: the prefetch must NOT materialize the ~400-row unrelated
    # tail. Total legacy rows loaded ≤ a small multiple of the page size, far
    # below the full table (10 page rows + the fat tail).
    full_table = len(store.legacy_mapping_repo.list_mappings(tenant_id=TENANT))
    assert full_table >= 400, "seed should include the unrelated fat tail"
    assert scoped_rows < 100, (
        f"provider enrich loaded {scoped_rows} legacy rows for 10 assets — "
        f"scope pushdown regressed (full table is {full_table})"
    )


def test_provider_enrich_matches_per_call_path():
    """Batch (prefetch) path == per-call path for the legacy_object_mappings
    projection — the scope pushdown must not drift from the single-resource
    detail path that uses list_mappings(canonical_ref=...)."""
    brain = _new_brain()
    store = brain._state_store.database_store
    provider = brain._get_handler_deps().services.provider

    assets = store.resource_api_repo.list_assets(tenant_id=TENANT)[:10]
    items = [
        {"resource_code": a.resource_code, "lifecycle_status": a.lifecycle_status, "title": a.title}
        for a in assets
    ]
    batch = {o["resource_code"]: o["legacy_object_mappings"] for o in provider.enrich_resource_assets(items, store)}
    for item in items:
        single = provider.enrich_resource_asset(dict(item), store)["legacy_object_mappings"]
        assert _norm(batch[item["resource_code"]]) == _norm(single), (
            f"batch vs per-call legacy_object_mappings differ for {item['resource_code']}"
        )
