"""Catalog read-path SQL filters — browse / snapshot projection / duplicate check."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.command.handlers.j2.duplicate_check import check_catalog_duplicate
from zw_brain.domain.provider_snapshot_projection import project_provider_inbox
from zw_brain.domain.repositories.catalog import CatalogRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "catalog_hot_paths.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


@pytest.fixture()
def brain(temp_db: Path) -> BrainService:
    ds = DatabaseStore()
    ds.initialize()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=StateStore(database_store=ds))


def _seed_browse_mix() -> None:
    repo = CatalogRepository()
    for idx in range(5):
        repo.upsert_from_resource(
            {
                "id": f"cat-active-{idx:02d}",
                "name": f"企业信息目录{idx}",
                "status": "active",
                "provider": "11370000MB284651XL",
            },
            tenant_id=TENANT,
        )
    for idx in range(3):
        repo.upsert_from_resource(
            {
                "id": f"cat-retired-{idx:02d}",
                "name": f"退役目录{idx}",
                "status": "retired",
                "provider": "11370000MB284651XL",
            },
            tenant_id=TENANT,
        )
    repo.upsert_from_resource(
        {
            "id": "api-group:demo",
            "name": "API 分组",
            "status": "active",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )


def test_catalog_browse_default_filters_active_real_only(brain: BrainService) -> None:
    _seed_browse_mix()
    result = invoke_trusted(
        brain,
        "catalog.browse",
        {"limit": 20, "page": 1},
        role="ROLE_ORGAN_OPERATER",
    )
    codes = {item["catalog_code"] for item in result["items"]}
    assert "cat-active-00" in codes
    assert not any(code.startswith("cat-retired-") for code in codes)
    assert "api-group:demo" not in codes
    assert result["total"] >= 5
    assert all(not str(item["catalog_code"]).startswith("cat-retired-") for item in result["items"])


def test_provider_inbox_projection_uses_status_filters(brain: BrainService) -> None:
    repo = CatalogRepository()
    repo.upsert_from_resource(
        {
            "id": "cat-pending-review-001",
            "name": "待审目录",
            "status": "pending_review",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    repo.upsert_from_resource(
        {
            "id": "cat-active-only-001",
            "name": "已发布目录",
            "status": "active",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    inbox = project_provider_inbox(tenant_id=TENANT)
    ids = {item["id"] for item in inbox["field_decisions"]}
    assert "cat-pending-review-001" in ids
    assert "cat-active-only-001" not in ids


def test_duplicate_check_targets_candidates_only(brain: BrainService) -> None:
    repo = CatalogRepository()
    repo.upsert_from_resource(
        {
            "id": "cat-target",
            "name": "重复标题目录",
            "status": "approved_pending_publish",
            "provider": "11370000MB284651XL",
            "region_code": "370000",
        },
        tenant_id=TENANT,
    )
    repo.upsert_from_resource(
        {
            "id": "cat-dup-title",
            "name": "重复标题目录",
            "status": "active",
            "provider": "11370000MB284651XL",
            "region_code": "370100",
        },
        tenant_id=TENANT,
    )
    repo.upsert_from_resource(
        {
            "id": "cat-retired-noise",
            "name": "重复标题目录",
            "status": "retired",
            "provider": "11370000MB284651XL",
        },
        tenant_id=TENANT,
    )
    result = check_catalog_duplicate(brain, "cat-target")
    codes = {item["catalog_code"] for item in result["duplicate_warnings"]}
    assert "cat-dup-title" in codes
    assert "cat-retired-noise" not in codes
