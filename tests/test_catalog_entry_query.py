"""catalog.entry.query — SQL-side lifecycle filter + limit (P5 publish queue)."""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db() -> None:
    ensure_runtime_schema()
    yield None


@pytest.fixture()
def brain(temp_db: None) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_catalogs() -> None:
    repo = CatalogRepository()
    for idx in range(8):
        repo.upsert_from_resource(
            {
                "id": f"cat-pending-{idx:02d}",
                "name": f"待发布目录 {idx}",
                "status": "approved_pending_publish",
                "provider": "11370000MB284651XL",
            },
            tenant_id=TENANT,
        )
    for idx in range(3):
        repo.upsert_from_resource(
            {
                "id": f"cat-active-{idx:02d}",
                "name": f"已发布目录 {idx}",
                "status": "active",
                "provider": "11370000MB284651XL",
            },
            tenant_id=TENANT,
        )


def test_catalog_entry_query_filters_and_limits_at_sql(brain: BrainService) -> None:
    _seed_catalogs()
    repo = CatalogRepository()
    expected_total = repo.count_entries(
        tenant_id=TENANT,
        lifecycle_status="approved_pending_publish",
    )
    result = invoke_trusted(
        brain,
        "catalog.entry.query",
        {
            "lifecycle_status": "approved_pending_publish",
            "limit": 5,
        },
        role="ROLE_BUSIAUDIT",
    )
    assert expected_total >= 8
    assert result["total"] == expected_total
    assert len(result["items"]) == min(5, expected_total)
    assert all(item["lifecycle_status"] == "approved_pending_publish" for item in result["items"])


def test_catalog_entry_query_rejects_invalid_limit(brain: BrainService) -> None:
    _seed_catalogs()
    with pytest.raises(ValueError, match="limit must be >= 1"):
        invoke_trusted(
            brain,
            "catalog.entry.query",
            {
                "lifecycle_status": "approved_pending_publish",
                "limit": 0,
            },
            role="ROLE_BUSIAUDIT",
        )


def test_catalog_entry_query_order_updated_desc_surfaces_newest(brain: BrainService) -> None:
    """0611 断点 A：发布队列默认 catalog_code 升序时，新审结目录（j2-* 前缀 ASCII 排在
    存量数字码后）配合截断永不可见。order=updated_desc 让最新提交的目录排最前。"""
    repo = CatalogRepository()
    # 存量数字码目录（ASCII 序排前）
    for idx in range(3):
        repo.upsert_from_resource(
            {
                "id": f"30701337000030800200000/00004{idx}",
                "name": f"存量待发布目录 {idx}",
                "status": "approved_pending_publish",
                "provider": "11370000MB284651XL",
            },
            tenant_id=TENANT,
        )
    # 新审结目录（j2-inline-* 前缀，ASCII 序排最后；updated_at 最新）
    repo.upsert_from_resource(
        {
            "id": "j2-inline-9999-newest",
            "name": "新审结目录（最新提交）",
            "status": "approved_pending_publish",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )

    # 默认序（catalog_code 升序）：j2-* 排最后 —— 截断队列下永不可见的根因。
    default_order = invoke_trusted(
        brain,
        "catalog.entry.query",
        {"lifecycle_status": "approved_pending_publish"},
        role="ROLE_BUSIAUDIT",
    )
    assert default_order["items"][-1]["catalog_code"] == "j2-inline-9999-newest"

    # updated_desc：最新提交的目录排最前（发布队列工作序）。
    recency = invoke_trusted(
        brain,
        "catalog.entry.query",
        {"lifecycle_status": "approved_pending_publish", "order": "updated_desc"},
        role="ROLE_BUSIAUDIT",
    )
    assert recency["items"][0]["catalog_code"] == "j2-inline-9999-newest"
    assert recency["total"] == default_order["total"]
