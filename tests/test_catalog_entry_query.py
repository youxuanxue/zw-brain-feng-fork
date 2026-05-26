"""catalog.entry.query — SQL-side lifecycle filter + limit (P5 publish queue)."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
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
        db_path = Path(tmp) / "catalog_entry_query.db"
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
