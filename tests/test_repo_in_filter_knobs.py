# Wave: 1
# Journey: J1/J2
# Pages: P2 发现 / P7 共享专区
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/repositories/resource_api.py
#   zw_brain/domain/repositories/metadata_evidence.py
#   zw_brain/domain/repositories/delivery.py
"""M1 仓层 IN-filter knobs 单测（additive，零 caller 改动）.

镜像 LegacyObjectMappingRepository.list_mappings(canonical_refs=) 的 idiom，给读路径
list_* 方法加可选复数 *_codes / target_refs 参数，把过滤下推到 SQL IN(...)。

每个方法证三件事：
  (a) scoped 调用只返回 code ∈ codes 的行；
  (b) codes=[] → [] 且不发查询；
  (c) codes=None → 与改前一致（整租户全量、同 order_by）。

自建小规模真库（经 repository 真灌库），不耦合 seed snapshot。

PG 迁移后：DB 由根 conftest 的 function-scoped 空 PG 克隆（已 alembic upgrade head 建表）
供给，本模块只把小规模 fixture 数据灌进每个测试自己的空克隆。无需影子库 /
旧库路径环境变量 / reset_and_upgrade —— schema 已就绪、跨测试天然隔离。
"""
from __future__ import annotations

import pytest

TENANT = "sd-default"

RESOURCE_CODES = [f"res-k-{i:04d}" for i in range(6)]


@pytest.fixture(autouse=True)
def _seed_db():
    _seed()
    yield


def _seed() -> None:
    """One row per code in each projection table, keyed by resource_code / target_ref /
    delivery_code so IN-filters have something to scope. delivery_code uses the
    provider-external:{resource_code} convention (cf. provider_service enrich)."""
    from zw_brain.domain.repositories import (
        DeliveryRepository,
        MetadataEvidenceRepository,
        ResourceApiRepository,
    )

    asset_repo = ResourceApiRepository()
    meta_repo = MetadataEvidenceRepository()
    delivery_repo = DeliveryRepository()

    for i, code in enumerate(RESOURCE_CODES):
        asset_repo.upsert_asset(
            {
                "resource_code": code,
                "title": f"资源 {i}",
                "resource_kind": "dataset",
                "lifecycle_status": "active",
                "source_ref": f"k:resource:{i}",
                "legacy_object_ref": code,
            },
            tenant_id=TENANT,
        )
        asset_repo.upsert_binding(
            {
                "binding_code": f"bind-{code}",
                "resource_code": code,
                "channel_kind": "api_gateway",
                "source_ref": f"k:bind:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_schema_mapping(
            {
                "mapping_code": f"map-{code}",
                "catalog_code": "cat-k",
                "catalog_item_code": f"item-{code}",
                "resource_code": code,
                "binding_code": f"bind-{code}",
                "source_ref": f"k:map:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_schema_snapshot(
            {
                "snapshot_ref": f"snap-{code}",
                "resource_code": code,
                "binding_code": f"bind-{code}",
                "schema_json": {"col": i},
                "source_ref": f"k:snap:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_gather_evidence(
            {
                "gather_task_ref": f"gather-{code}",
                "resource_code": code,
                "status": "succeeded",
                "source_ref": f"k:gather:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_lineage_relation(
            {
                "relation_ref": f"lin-src-{code}",
                "relation_scope": "table",
                "source_resource_code": code,
                "target_resource_code": "other-target",
                "source_ref": f"k:lin-src:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_lineage_relation(
            {
                "relation_ref": f"lin-tgt-{code}",
                "relation_scope": "table",
                "source_resource_code": "other-source",
                "target_resource_code": code,
                "source_ref": f"k:lin-tgt:{i}",
            },
            tenant_id=TENANT,
        )
        meta_repo.upsert_quality_evidence(
            {
                "quality_ref": f"q-{code}",
                "target_type": "resource_asset",
                "target_ref": code,
                "quality_status": "passed",
                "source_ref": f"k:q:{i}",
            },
            tenant_id=TENANT,
        )
        delivery_code = f"provider-external:{code}"
        delivery_repo.upsert_attempt(
            {
                "attempt_code": f"att-{code}",
                "delivery_code": delivery_code,
                "attempt_kind": "exchange",
                "state": "succeeded",
            },
            tenant_id=TENANT,
        )
        delivery_repo.add_execution_evidence(
            {
                "evidence_ref": f"evd-{code}",
                "delivery_code": delivery_code,
                "attempt_code": f"att-{code}",
                "result_status": "succeeded",
            },
            tenant_id=TENANT,
        )


@pytest.fixture
def asset_repo():
    from zw_brain.domain.repositories import ResourceApiRepository

    return ResourceApiRepository()


@pytest.fixture
def meta_repo():
    from zw_brain.domain.repositories import MetadataEvidenceRepository

    return MetadataEvidenceRepository()


@pytest.fixture
def delivery_repo():
    from zw_brain.domain.repositories import DeliveryRepository

    return DeliveryRepository()


# Generic helper asserting the three knob behaviours for a single resource_code-keyed method.
def _assert_knob(list_fn, attr: str, scope_kwarg: str, scope_values: list[str]):
    full = list_fn()
    full_codes = {getattr(r, attr) for r in full}
    for c in scope_values:
        assert c in full_codes, f"seed missing {attr}={c}; full set {full_codes}"

    # (a) scoped → subset whose attr ∈ scope_values
    scoped = list_fn(**{scope_kwarg: scope_values})
    scoped_codes = {getattr(r, attr) for r in scoped}
    assert scoped_codes <= set(scope_values), f"scoped leaked codes: {scoped_codes - set(scope_values)}"
    assert scoped_codes == set(scope_values), f"scoped missing codes: {set(scope_values) - scoped_codes}"

    # (b) empty list → [] (no query, but observable result is [])
    assert list_fn(**{scope_kwarg: []}) == []

    # (c) None → byte-identical to no-arg full call (same rows, same order)
    none_call = list_fn(**{scope_kwarg: None})
    assert [getattr(r, attr) for r in none_call] == [getattr(r, attr) for r in full]


# ── resource_api.list_bindings(resource_codes=) ──
def test_list_bindings_resource_codes(asset_repo):
    _assert_knob(asset_repo.list_bindings, "resource_code", "resource_codes", RESOURCE_CODES[:3])


# ── metadata_evidence.list_schema_mappings(resource_codes=) ──
def test_list_schema_mappings_resource_codes(meta_repo):
    _assert_knob(meta_repo.list_schema_mappings, "resource_code", "resource_codes", RESOURCE_CODES[:3])


# ── metadata_evidence.list_schema_snapshots(resource_codes=) ──
def test_list_schema_snapshots_resource_codes(meta_repo):
    _assert_knob(meta_repo.list_schema_snapshots, "resource_code", "resource_codes", RESOURCE_CODES[:3])


# ── metadata_evidence.list_gather_evidence(resource_codes=) ──
def test_list_gather_evidence_resource_codes(meta_repo):
    _assert_knob(meta_repo.list_gather_evidence, "resource_code", "resource_codes", RESOURCE_CODES[:3])


# ── metadata_evidence.list_quality_evidence(target_refs=) keyed by target_ref ──
def test_list_quality_evidence_target_refs(meta_repo):
    _assert_knob(meta_repo.list_quality_evidence, "target_ref", "target_refs", RESOURCE_CODES[:3])


def test_list_quality_evidence_target_refs_keeps_target_type(meta_repo):
    """target_refs composes with target_type (AND); a non-matching target_type yields []."""
    scope = RESOURCE_CODES[:3]
    assert {r.target_ref for r in meta_repo.list_quality_evidence(target_type="resource_asset", target_refs=scope)} == set(scope)
    assert meta_repo.list_quality_evidence(target_type="catalog_item", target_refs=scope) == []


# ── delivery.list_attempts(delivery_codes=) ──
def test_list_attempts_delivery_codes(delivery_repo):
    codes = [f"provider-external:{c}" for c in RESOURCE_CODES[:3]]
    _assert_knob(delivery_repo.list_attempts, "delivery_code", "delivery_codes", codes)


# ── delivery.list_execution_evidence(delivery_codes=) ──
def test_list_execution_evidence_delivery_codes(delivery_repo):
    codes = [f"provider-external:{c}" for c in RESOURCE_CODES[:3]]
    _assert_knob(delivery_repo.list_execution_evidence, "delivery_code", "delivery_codes", codes)


# ── lineage: OR(source|target) semantics preserved under plural IN ──
def test_list_lineage_relations_resource_codes_or_semantics(meta_repo):
    scope = RESOURCE_CODES[:3]
    rows = meta_repo.list_lineage_relations(resource_codes=scope)
    # every returned row must touch a scoped code on EITHER source or target column
    for r in rows:
        assert r.source_resource_code in scope or r.target_resource_code in scope
    # both the source-keyed and target-keyed seed rows for a scoped code appear
    refs = {r.relation_ref for r in rows}
    for c in scope:
        assert f"lin-src-{c}" in refs and f"lin-tgt-{c}" in refs
    # out-of-scope codes' rows absent
    for c in RESOURCE_CODES[3:]:
        assert f"lin-src-{c}" not in refs and f"lin-tgt-{c}" not in refs


def test_list_lineage_relations_empty_and_none(meta_repo):
    assert meta_repo.list_lineage_relations(resource_codes=[]) == []
    none_refs = [r.relation_ref for r in meta_repo.list_lineage_relations(resource_codes=None)]
    full_refs = [r.relation_ref for r in meta_repo.list_lineage_relations()]
    assert none_refs == full_refs
