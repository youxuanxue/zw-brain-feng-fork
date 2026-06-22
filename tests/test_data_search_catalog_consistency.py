"""P2 data.search must use the same active catalog availability as browse/query."""

from __future__ import annotations

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.domain.repositories.topic_package import TopicPackageRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"
QUERY = "停车场信息"
ACTIVE_PARKING_CODE = "370000308004000000/000001"
DRAFT_PARKING_CODE = "parking-draft-should-not-appear"


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


def _seed_parking_catalogs() -> None:
    catalog = CatalogRepository()
    catalog.upsert_from_resource(
        {
            "id": ACTIVE_PARKING_CODE,
            "name": "停车场信息",
            "status": "active",
            "provider": "11370000MB284651XL",
            "region_code": "370000",
            "summary_json": {
                "description": "全省停车场信息目录",
                "fields": ["停车场名称", "泊位数量"],
            },
        },
        tenant_id=TENANT,
    )
    catalog.upsert_from_resource(
        {
            "id": DRAFT_PARKING_CODE,
            "name": "停车场信息草稿目录",
            "status": "draft",
            "provider": "11370000MB284651XL",
            "region_code": "370000",
        },
        tenant_id=TENANT,
    )

    # Reproduce the historical split: an active catalog can have topic
    # projections that are not projected yet. P2 search must still return the
    # active catalog card; projection status is explanation metadata only.
    topics = TopicPackageRepository()
    topics.create_package(
        {
            "package_code": "tp-parking-blocked",
            "title": "停车专题投影未就绪",
            "status": "draft",
            "display_snapshot_json": {"projection_kind": "topic_package"},
        },
        tenant_id=TENANT,
    )
    topics.configure_package(
        "tp-parking-blocked",
        {
            "items": [
                {
                    "ref_type": "catalog_entry",
                    "ref_id": ACTIVE_PARKING_CODE,
                    "title": "停车场信息",
                    "display_order": 0,
                }
            ],
            "visibility": [],
        },
        tenant_id=TENANT,
    )


def test_data_search_matches_active_catalog_browse_and_query(brain: BrainService) -> None:
    _seed_parking_catalogs()

    search = invoke_trusted(
        brain,
        "data.search",
        {"query": QUERY, "page": 1},
        role="ROLE_ORGAN_OPERATER",
    )
    browse = invoke_trusted(
        brain,
        "catalog.browse",
        {"query": QUERY, "page": 1, "limit": 20},
        role="ROLE_ORGAN_OPERATER",
    )
    entry_query = invoke_trusted(
        brain,
        "catalog.entry.query",
        {"query": QUERY, "lifecycle_status": "active"},
        role="ROLE_ORGAN_OPERATER",
    )

    search_codes = {item["id"] for item in search["results"]}
    browse_codes = {item["catalog_code"] for item in browse["items"]}
    entry_codes = {item["catalog_code"] for item in entry_query["items"]}

    assert ACTIVE_PARKING_CODE in search_codes
    assert ACTIVE_PARKING_CODE in browse_codes
    assert ACTIVE_PARKING_CODE in entry_codes
    assert DRAFT_PARKING_CODE not in search_codes
    assert DRAFT_PARKING_CODE not in browse_codes
    assert DRAFT_PARKING_CODE not in entry_codes

    card = next(item for item in search["results"] if item["id"] == ACTIVE_PARKING_CODE)
    assert card["lifecycleStatus"] == "active"
    assert {item["projectionStatus"] for item in card["topicProjections"]} == {"blocked"}
