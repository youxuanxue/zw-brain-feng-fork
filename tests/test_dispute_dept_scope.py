"""异议（disputes）部门数据可见域收口单测（M7）：enrich_disputes_snapshot 按
complainant_org_id / provider_org_id 双侧机构过滤。

一条异议有两个利益相关方——申诉方（complainant，提的人）与提供方（provider，被异议
资源的供方）。部门角色只要任一侧落在自己可见域，就该看见这条异议。锁定三态契约：
None=全局放行 / 非空集=双侧任一命中 / 空集=fail-closed。与 M2 解析器单测同一 temp_db 范式。
"""

from __future__ import annotations

import pytest

from zw_brain.domain.dispute_snapshot_projection import enrich_disputes_snapshot
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared import db as db_module
from zw_brain.shared.migrate import ensure_runtime_schema

TENANT = "sd-default"
ORG_A = "11370000MB284651XL"  # 本机构（部门角色可见域）
ORG_B = "36010000876"         # 无关机构


@pytest.fixture()
def temp_db() -> None:
    """conftest autouse fixture supplies an isolated empty PG clone; just ensure
    schema + reset the engine cache around the test（与 M2 解析器单测同一范式）。"""
    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    ensure_runtime_schema()
    try:
        yield None
    finally:
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def _seed_cases() -> dict[str, str]:
    """三条异议：①申诉方=A、②提供方=A、③两侧都=B（与 A 无关）。"""
    repo = ObjectionRepository()
    complainant_a = repo.create_case(
        {
            "target_type": "catalog",
            "target_id": "cat-complainant-a",
            "title": "A 作为申诉方提的异议",
            "complainant_org_id": ORG_A,
            "provider_org_id": ORG_B,
            "status": "submitted",
        },
        tenant_id=TENANT,
    )
    provider_a = repo.create_case(
        {
            "target_type": "catalog",
            "target_id": "cat-provider-a",
            "title": "A 作为提供方被异议",
            "complainant_org_id": ORG_B,
            "provider_org_id": ORG_A,
            "status": "submitted",
        },
        tenant_id=TENANT,
    )
    other_b = repo.create_case(
        {
            "target_type": "catalog",
            "target_id": "cat-other-b",
            "title": "两侧都与 A 无关",
            "complainant_org_id": ORG_B,
            "provider_org_id": ORG_B,
            "status": "submitted",
        },
        tenant_id=TENANT,
    )
    return {
        "complainant_a": complainant_a.id,
        "provider_a": provider_a.id,
        "other_b": other_b.id,
    }


def _dispute_ids(snapshot: dict) -> set[str]:
    return {item["id"] for item in snapshot["disputes"]}


def test_dept_scope_keeps_either_side_in_scope(temp_db: None) -> None:
    """visible_org_codes={A} → 申诉方=A 与 提供方=A 两条都在，纯 B 的那条不在。"""
    ids = _seed_cases()
    out = enrich_disputes_snapshot({}, tenant_id=TENANT, visible_org_codes={ORG_A})
    seen = _dispute_ids(out)
    assert ids["complainant_a"] in seen  # 申诉方侧命中
    assert ids["provider_a"] in seen     # 提供方侧命中
    assert ids["other_b"] not in seen    # 两侧皆无关 → 不可见


def test_global_role_none_keeps_all(temp_db: None) -> None:
    """visible_org_codes=None（全局角色）→ 全部异议可见，不过滤。"""
    ids = _seed_cases()
    out = enrich_disputes_snapshot({}, tenant_id=TENANT, visible_org_codes=None)
    seen = _dispute_ids(out)
    assert seen == set(ids.values())


def test_empty_set_fail_closed_keeps_none(temp_db: None) -> None:
    """visible_org_codes=set()（部门角色缺机构上下文）→ fail-closed，一条都不见。"""
    _seed_cases()
    out = enrich_disputes_snapshot({}, tenant_id=TENANT, visible_org_codes=set())
    assert out["disputes"] == []
