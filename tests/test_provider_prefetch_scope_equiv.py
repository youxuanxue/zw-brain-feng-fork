# Wave: 1
# Journey: J2
# Pages: P5 提供方资源
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/services/provider_service.py
"""provider `_build_asset_enrich_prefetch` scope 收口等价守卫 (HIGH-1 / 缺陷1).

M2 把 `_build_asset_enrich_prefetch` 的 8 张租户全表加载改为按当页
resource/delivery scope 下推 (M1 IN-filter knobs)。本测试在多资源 shadow DB 上
锁定:
1. scoped prefetch 的 consumed-key 切片 (`<map>.get(code, [])` for codes on the page)
   与旧整租户分组 *逐字节相等* — 输出形态零变更;
2. scoped 结果集 row 数 ≤ 租户总量 (证明真的下推了过滤, 没拉全表);
3. delivery key 变换正确: prefetch 按 `provider-external:{resource_code}` scope,
   不是裸 resource_code (enrich_resource_asset:303 用 provider-external 前缀查 delivery).

自建小规模真库 (repository 真灌库), 不依赖客户 dump seed。

PG 迁移后：DB 由根 conftest 的 function-scoped 空 PG 克隆（已 alembic upgrade head 建表）
供给，本模块只把小规模 fixture 数据灌进每个测试自己的空克隆。无需影子库 /
旧库路径环境变量 / reset_and_upgrade —— schema 已就绪、跨测试天然隔离。
"""
from __future__ import annotations

import pytest

TENANT = "sd-default"

# A page of resources to enrich (subset of all seeded resources). Off-page
# resources MUST also carry evidence rows so a whole-tenant load returns more
# rows than the scoped load — that gap is what proves the IN-filter pushdown.
ON_PAGE = [f"res-{i:03d}" for i in range(6)]
OFF_PAGE = [f"res-{i:03d}" for i in range(6, 20)]
ALL_RESOURCES = ON_PAGE + OFF_PAGE


@pytest.fixture(autouse=True)
def _seed_db():
    _seed()
    yield


def _seed() -> None:
    """Seed every per-resource table enrich_resource_asset reads, for ALL_RESOURCES.

    Each resource gets ≥1 binding / schema_mapping / snapshot / gather / lineage /
    quality (target_type=resource_asset) / delivery attempt / execution evidence /
    legacy mapping, keyed so the scoped slices are non-trivial. Delivery rows are
    keyed by `provider-external:{resource_code}` to mirror the read-path lookup.
    """
    from zw_brain.domain.repositories import (
        MetadataEvidenceRepository,
        ResourceApiRepository,
    )
    from zw_brain.domain.repositories.delivery import DeliveryRepository

    asset_repo = ResourceApiRepository()
    meta_repo = MetadataEvidenceRepository()
    delivery_repo = DeliveryRepository()

    for idx, rc in enumerate(ALL_RESOURCES):
        catalog = f"basic-elem:c-{idx % 5:03d}"
        asset_repo.upsert_asset(
            {
                "resource_code": rc,
                "title": f"资源 {rc}",
                "resource_kind": "api",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{idx % 4}",
                "catalog_code": catalog,
                "source_ref": f"t:res:{rc}",
                "legacy_object_ref": rc,
            },
            tenant_id=TENANT,
        )
        binding_code = f"bind-{rc}"
        asset_repo.upsert_binding(
            {
                "binding_code": binding_code,
                "resource_code": rc,
                "channel_kind": "api_gateway",
                "route_ref": f"/api/{rc}",
                "lifecycle_status": "active",
                "source_ref": f"t:bind:{rc}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_schema_mapping(
            {
                "mapping_code": f"map-{rc}",
                "catalog_code": catalog,
                "catalog_item_code": f"{catalog}:field-0",
                "resource_code": rc,
                "binding_code": binding_code,
                "status": "active",
                "source_ref": f"t:map:{rc}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_schema_snapshot(
            {
                "snapshot_ref": f"snap-{rc}",
                "resource_code": rc,
                "binding_code": binding_code,
                "schema_json": {"cols": [rc]},
                "source_ref": f"t:snap:{rc}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_gather_evidence(
            {
                "gather_task_ref": f"gather-{rc}",
                "resource_code": rc,
                "status": "succeeded",
                "source_ref": f"t:gather:{rc}",
            },
            tenant_id=TENANT,
        )
        # NOTE: lineage rows are deliberately NOT seeded here. The production
        # grouping loop in `_build_asset_enrich_prefetch` (and its pre-M2
        # ancestor at bc25447) keys lineage by `record.resource_code`, an
        # attribute LineageRelationProjectionRecord does not have (it carries
        # source_resource_code / target_resource_code). That grouping is a
        # pre-existing latent bug, harmless only because no seed/real data
        # attaches lineage rows to provider resource assets — so the loop body
        # never runs. Out of scope for this perf PR (must stay byte-identical,
        # not "fix" unrelated latent bugs). The `list_lineage_relations(
        # resource_codes=)` IN-filter scope this PR relies on is already proven
        # equivalent at the repo level in test_repo_in_filter_knobs.py
        # (test_list_lineage_relations_resource_codes_or_semantics / _empty_and_none).
        meta_repo.upsert_quality_evidence(
            {
                "quality_ref": f"qual-{rc}",
                "target_type": "resource_asset",
                "target_ref": rc,
                "quality_status": "passed",
                "source_ref": f"t:qual:{rc}",
            },
            tenant_id=TENANT,
        )
        # also a non-resource_asset quality row keyed by rc → must NOT leak into
        # the resource_asset-scoped prefetch (guards target_type AND combination).
        meta_repo.upsert_quality_evidence(
            {
                "quality_ref": f"qual-other-{rc}",
                "target_type": "catalog_item",
                "target_ref": rc,
                "quality_status": "passed",
                "source_ref": f"t:qual-other:{rc}",
            },
            tenant_id=TENANT,
        )
        delivery_code = f"provider-external:{rc}"
        delivery_repo.upsert_attempt(
            {
                "attempt_code": f"att-{rc}",
                "delivery_code": delivery_code,
                "attempt_kind": "exchange",
                "state": "succeeded",
            },
            tenant_id=TENANT,
        )
        delivery_repo.add_execution_evidence(
            {
                "evidence_ref": f"evd-{rc}",
                "delivery_code": delivery_code,
                "attempt_code": f"att-{rc}",
                "result_status": "succeeded",
            },
            tenant_id=TENANT,
        )


def _store():
    from zw_brain.shared.database_store import DatabaseStore

    return DatabaseStore()


def _whole_tenant_grouping(store):
    """Reconstruct the OLD (pre-M2) whole-tenant grouping: load every table with
    no scope (None → tenant-only full set per M1), group in Python exactly as the
    old `_build_asset_enrich_prefetch` did."""
    bindings: dict[str, list] = {}
    for r in store.resource_api_repo.list_bindings(tenant_id=TENANT):
        bindings.setdefault(r.resource_code, []).append(r)
    mappings: dict[str, list] = {}
    for r in store.metadata_evidence_repo.list_schema_mappings(tenant_id=TENANT):
        mappings.setdefault(r.resource_code, []).append(r)
    snapshots: dict[str, list] = {}
    for r in store.metadata_evidence_repo.list_schema_snapshots(tenant_id=TENANT):
        snapshots.setdefault(r.resource_code, []).append(r)
    gather: dict[str, list] = {}
    for r in store.metadata_evidence_repo.list_gather_evidence(tenant_id=TENANT):
        gather.setdefault(r.resource_code, []).append(r)
    # lineage intentionally omitted — see _seed() note (pre-existing latent
    # grouping bug; repo-level IN-filter equivalence covered by M1 tests).
    quality: dict[str, list] = {}
    for r in store.metadata_evidence_repo.list_quality_evidence(target_type="resource_asset", tenant_id=TENANT):
        quality.setdefault(r.target_ref, []).append(r)
    attempts: dict[str, list] = {}
    for r in store.delivery_repo.list_attempts(tenant_id=TENANT):
        attempts.setdefault(r.delivery_code, []).append(r)
    evidence: dict[str, list] = {}
    for r in store.delivery_repo.list_execution_evidence(tenant_id=TENANT):
        evidence.setdefault(r.delivery_code, []).append(r)
    return {
        "bindings_by_resource": bindings,
        "mappings_by_resource": mappings,
        "snapshots_by_resource": snapshots,
        "gather_by_resource": gather,
        "quality_by_ref": quality,
        "attempts_by_delivery": attempts,
        "evidence_by_delivery": evidence,
    }


def _provider_service(store):
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    ss = StateStore(database_store=store)
    brain = BrainService(state_store=ss)
    return brain._get_handler_deps().services.provider


def _ids(records) -> list:
    """Stable identity per record for byte-for-byte comparison (primary key col)."""
    out = []
    for r in records:
        for attr in ("binding_code", "mapping_code", "snapshot_ref", "gather_task_ref",
                     "relation_ref", "quality_ref", "attempt_code", "evidence_ref"):
            if hasattr(r, attr):
                out.append((attr, getattr(r, attr)))
                break
    return out


# ── consumed-key slices: scoped == whole-tenant, byte-for-byte ──

def test_scoped_prefetch_consumed_slices_equal_whole_tenant():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    old = _whole_tenant_grouping(store)

    resource_keyed = [
        "bindings_by_resource",
        "mappings_by_resource",
        "snapshots_by_resource",
        "gather_by_resource",
    ]
    for mapname in resource_keyed:
        for code in ON_PAGE:
            new_slice = scoped[mapname].get(code, [])
            old_slice = old[mapname].get(code, [])
            assert _ids(new_slice) == _ids(old_slice), (
                f"{mapname}[{code}] scoped slice != whole-tenant slice"
            )

    # quality keyed by target_ref (== resource_code here)
    for code in ON_PAGE:
        assert _ids(scoped["quality_by_ref"].get(code, [])) == _ids(old["quality_by_ref"].get(code, [])), (
            f"quality_by_ref[{code}] scoped slice != whole-tenant slice"
        )

    # delivery keyed by provider-external:{resource_code}
    for code in ON_PAGE:
        dc = f"provider-external:{code}"
        assert _ids(scoped["attempts_by_delivery"].get(dc, [])) == _ids(old["attempts_by_delivery"].get(dc, [])), (
            f"attempts_by_delivery[{dc}] scoped slice != whole-tenant slice"
        )
        assert _ids(scoped["evidence_by_delivery"].get(dc, [])) == _ids(old["evidence_by_delivery"].get(dc, [])), (
            f"evidence_by_delivery[{dc}] scoped slice != whole-tenant slice"
        )

    # legacy_by_ref already scoped pre-M2 (canonical_refs); confirm on-page codes present
    for code in ON_PAGE:
        assert code in scoped["legacy_by_ref"], f"legacy_by_ref missing on-page code {code}"


# ── row-count: scoped totals ≤ whole-tenant totals (pushdown actually happened) ──

def test_scoped_prefetch_row_counts_le_tenant_totals():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    old = _whole_tenant_grouping(store)

    def total(m):
        return sum(len(v) for v in m.values())

    for mapname in (
        "bindings_by_resource",
        "mappings_by_resource",
        "snapshots_by_resource",
        "gather_by_resource",
        "quality_by_ref",
        "attempts_by_delivery",
        "evidence_by_delivery",
    ):
        scoped_total = total(scoped[mapname])
        tenant_total = total(old[mapname])
        assert scoped_total <= tenant_total, (
            f"{mapname}: scoped total {scoped_total} > tenant total {tenant_total} — not scoped"
        )
    # With 6 on-page of 20 resources, the resource-keyed maps must be STRICTLY
    # smaller (proves rows for off-page resources were not loaded).
    assert total(scoped["bindings_by_resource"]) < total(old["bindings_by_resource"])
    assert total(scoped["attempts_by_delivery"]) < total(old["attempts_by_delivery"])


# ── empty page → every scoped map empty (guards short-circuit, no full load) ──

def test_empty_page_yields_empty_prefetch():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, [])
    for mapname in (
        "bindings_by_resource",
        "mappings_by_resource",
        "snapshots_by_resource",
        "gather_by_resource",
        "lineage_by_resource",
        "quality_by_ref",
        "attempts_by_delivery",
        "evidence_by_delivery",
        "legacy_by_ref",
    ):
        assert scoped[mapname] == {}, f"{mapname} non-empty for empty page"


# ── delivery key transform: raw resource_code must NOT match (provider-external:) ──

def test_delivery_keyed_by_provider_external_prefix():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    for code in ON_PAGE:
        # raw resource_code is NOT a delivery key
        assert code not in scoped["attempts_by_delivery"], (
            f"delivery map keyed by raw resource_code {code} — key transform missing"
        )
        assert f"provider-external:{code}" in scoped["attempts_by_delivery"], (
            f"delivery map missing provider-external:{code}"
        )
