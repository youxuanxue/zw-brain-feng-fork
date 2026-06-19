# Wave: 1
# Journey: J2
# Pages: P5 提供方资源
# Consumer-faces: API (brain.invoke_skill)
# Roles: ROLE_ORGAN_OPERATER | ROLE_ORGAN_MANAGER
# Trace:
#   zw_brain/domain/services/provider_service.py
"""provider `_build_asset_enrich_prefetch` 血缘分组修复守卫 (follow-up to 缺陷1).

背景: prefetch 的 lineage 分组原按 `record.resource_code` 归组, 而
`LineageRelationProjectionRecord` 没有 `resource_code` 字段 (只有 source_resource_code /
target_resource_code) —— 一旦有血缘行流到该 provider 资产, 该行会 AttributeError 崩溃。
这是 bc25447 起的 pre-existing 潜伏 bug, 仅因无血缘数据从未触发 (见
test_provider_prefetch_scope_equiv.py 的 _seed 注释)。本测试**故意灌入血缘行**, 锁定:

1. batch 分组不再崩, 且按 source/target 两端归组 (镜像 repo 单数
   list_lineage_relations(resource_code=) 的 OR(source|target) 语义);
2. batch 路径每个 on-page 资源的血缘切片, 与 non-batch 单查路径 *逐字节相等*;
3. self-loop (source==target) 与 cross-page 关系 (一端 off-page) 都正确处理。

自建小规模真库, 不依赖客户 dump seed。

PG 迁移后：DB 由根 conftest 的 function-scoped 空 PG 克隆（已 alembic upgrade head 建表）
供给，本模块只把小规模 fixture 数据灌进每个测试自己的空克隆。无需影子库 /
旧库路径环境变量 / reset_and_upgrade —— schema 已就绪、跨测试天然隔离。
"""
from __future__ import annotations

import pytest

TENANT = "sd-default"

ON_PAGE = ["res-000", "res-001", "res-002"]
OFF_PAGE = ["res-100", "res-101"]
ALL_RESOURCES = ON_PAGE + OFF_PAGE


@pytest.fixture(autouse=True)
def _seed_db():
    _seed()
    yield


def _seed() -> None:
    """Seed resource assets + lineage relations covering every grouping case:
    - L-01: res-000 → res-001          (both on-page; one row keyed under TWO codes)
    - L-02: res-002 → res-000          (both on-page)
    - L-03: res-000 → res-000          (self-loop: must appear once under res-000)
    - L-04: res-001 → res-100          (cross-page: res-001 on-page, res-100 off-page)
    """
    from zw_brain.domain.repositories import (
        MetadataEvidenceRepository,
        ResourceApiRepository,
    )

    asset_repo = ResourceApiRepository()
    meta_repo = MetadataEvidenceRepository()

    for idx, rc in enumerate(ALL_RESOURCES):
        asset_repo.upsert_asset(
            {
                "resource_code": rc,
                "title": f"资源 {rc}",
                "resource_kind": "api",
                "lifecycle_status": "active",
                "owner_org_id": f"org-{idx % 3}",
                "catalog_code": f"basic-elem:c-{idx:03d}",
                "source_ref": f"t:res:{rc}",
                "legacy_object_ref": rc,
            },
            tenant_id=TENANT,
        )

    relations = [
        ("lin-01", "res-000", "res-001"),
        ("lin-02", "res-002", "res-000"),
        ("lin-03", "res-000", "res-000"),
        ("lin-04", "res-001", "res-100"),
    ]
    for relation_ref, src, tgt in relations:
        meta_repo.upsert_lineage_relation(
            {
                "relation_ref": relation_ref,
                "relation_scope": "table",
                "source_resource_code": src,
                "target_resource_code": tgt,
                "relation_type": "imported",
                "source_ref": f"t:lin:{relation_ref}",
            },
            tenant_id=TENANT,
        )


def _store():
    from zw_brain.shared.database_store import DatabaseStore

    return DatabaseStore()


def _provider_service(store):
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.state_store import StateStore

    ss = StateStore(database_store=store)
    brain = BrainService(state_store=ss)
    return brain._get_handler_deps().services.provider


def _refs(records) -> list[str]:
    return [r.relation_ref for r in records]


# ── batch grouping no longer crashes and keys by both endpoints ──

def test_lineage_batch_grouping_keys_both_endpoints():
    store = _store()
    svc = _provider_service(store)
    # This call previously raised AttributeError on the first lineage row.
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    lineage = scoped["lineage_by_resource"]

    # res-000: source in lin-01 & lin-03, target in lin-02 & lin-03 → {01,02,03} once each
    assert _refs(lineage.get("res-000", [])) == ["lin-01", "lin-02", "lin-03"]
    # res-001: source in lin-04, target in lin-01 → {01,04}
    assert _refs(lineage.get("res-001", [])) == ["lin-01", "lin-04"]
    # res-002: source in lin-02 → {02}
    assert _refs(lineage.get("res-002", [])) == ["lin-02"]


def test_lineage_self_loop_appears_once():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    # lin-03 is res-000→res-000; it must appear exactly once under res-000.
    assert _refs(scoped["lineage_by_resource"]["res-000"]).count("lin-03") == 1


# ── batch slice == non-batch single-query path, byte-for-byte ──

def test_lineage_batch_equals_non_batch_per_resource():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    for code in ON_PAGE:
        non_batch = store.metadata_evidence_repo.list_lineage_relations(
            resource_code=code, tenant_id=TENANT
        )
        batch_slice = scoped["lineage_by_resource"].get(code, [])
        assert _refs(batch_slice) == _refs(non_batch), (
            f"lineage_by_resource[{code}] batch slice != non-batch single-query result"
        )


# ── cross-page relation is reachable from its on-page endpoint ──

def test_lineage_cross_page_relation_grouped_under_on_page_endpoint():
    store = _store()
    svc = _provider_service(store)
    scoped = svc._build_asset_enrich_prefetch(store, list(ON_PAGE))
    # lin-04 (res-001 → res-100): res-001 is on-page → must be under res-001.
    assert "lin-04" in _refs(scoped["lineage_by_resource"]["res-001"])
