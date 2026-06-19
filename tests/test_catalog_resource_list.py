"""catalog.resource.list — 目录→资源钻取（有资源 / 无资源 / 404 / 分页 / 角色）。"""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.errors import AccessDeniedError
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.resource_api import ResourceApiRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
CAT_WITH = "cat-with-resources"
CAT_EMPTY = "cat-empty"


@pytest.fixture()
def temp_db() -> None:
    ensure_runtime_schema()
    yield None


def _seed() -> None:
    catalog_repo = CatalogRepository()
    asset_repo = ResourceApiRepository()
    # 有资源的目录 + 挂 7 个资源（真实形态：catalog_code 归属）
    catalog_repo.upsert_from_resource(
        {"id": CAT_WITH, "name": "学生课程信息", "status": "active", "provider": "11370000MB284651XL"},
        tenant_id=TENANT,
    )
    for idx in range(7):
        asset_repo.upsert_asset(
            {
                "resource_code": f"res-stu-{idx:02d}",
                "title": f"学生数据资源 {idx}",
                "resource_kind": "table",
                "lifecycle_status": "active" if idx % 2 == 0 else "suspended",
                "owner_org_id": "11370000MB284651XL",
                "catalog_code": CAT_WITH,
            },
            tenant_id=TENANT,
        )
    # 空目录（无资源，如 F9 医保 basic-element）
    catalog_repo.upsert_from_resource(
        {"id": CAT_EMPTY, "name": "医疗救助信息", "status": "active", "provider": "360002222211"},
        tenant_id=TENANT,
    )


@pytest.fixture()
def brain(temp_db: None) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    _seed()
    return BrainService(state_store=StateStore(database_store=ds))


def _call(brain: BrainService, payload: dict, role: str = "ROLE_ORGAN_OPERATER") -> dict:
    return invoke_trusted(brain, "catalog.resource.list", payload, role=role)


def test_catalog_with_resources(brain: BrainService) -> None:
    res = _call(brain, {"catalog_code": CAT_WITH})
    assert res["catalog"]["title"] == "学生课程信息"
    assert res["total"] == 7
    assert {it["resource_code"] for it in res["items"]} >= {"res-stu-00", "res-stu-01"}


def test_empty_catalog_honest_empty(brain: BrainService) -> None:
    """目录存在但挂 0 资源 → items:[] total:0 + catalog 非空（诚实空态，不 raise）。"""
    res = _call(brain, {"catalog_code": CAT_EMPTY})
    assert res["items"] == []
    assert res["total"] == 0
    assert res["catalog"]["title"] == "医疗救助信息"


def test_catalog_not_found_raises(brain: BrainService) -> None:
    from zw_brain.domain.errors import NotFoundError

    with pytest.raises(NotFoundError):
        _call(brain, {"catalog_code": "nonexistent-xyz"})


def test_lifecycle_filter(brain: BrainService) -> None:
    res = _call(brain, {"catalog_code": CAT_WITH, "lifecycle": "active"})
    assert res["total"] == 4  # idx 0/2/4/6 active
    assert all(it["lifecycle_status"] == "active" for it in res["items"])


def test_pagination(brain: BrainService) -> None:
    p1 = _call(brain, {"catalog_code": CAT_WITH, "limit": 5, "page": 1})
    p2 = _call(brain, {"catalog_code": CAT_WITH, "limit": 5, "page": 2})
    assert len(p1["items"]) == 5
    assert len(p2["items"]) == 2
    assert p1["total"] == 7 == p2["total"]


def test_role_denied(brain: BrainService) -> None:
    with pytest.raises(AccessDeniedError):
        _call(brain, {"catalog_code": CAT_WITH}, role="ROLE_SYSTEM")
