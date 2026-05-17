"""M0 rollback contract test.

Verifies that `zw_brain.entry.legacy_migration.rollback.rollback` correctly
flips `legacy_object_mapping.mapping_status` from `mapped` to `rolled_back`,
emits one `audit_event(skill_id="legacy.migration.rollback")`, and is
idempotent under repeat invocation. Canonical suspension is exercised via
the `--also-suspend-canonical` toggle.

Tests use a temporary SQLite DB plus seeded `LegacyObjectMappingRecord` rows
to keep the contract narrow — no full mapper run required.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from zw_brain.domain.models import (
    AuditEventRecord,
    CatalogEntryRecord,
    LegacyObjectMappingRecord,
)
from zw_brain.shared.db import create_session_factory
from zw_brain.shared.migrate import ensure_runtime_schema


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "rollback_contract.sqlite"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema()
    return db_path


@pytest.fixture()
def seeded_mappings(isolated_db: Path) -> list[str]:
    """Seed 3 catalog_entry mappings + 1 resource_asset mapping for dsp_catalog."""
    SessionLocal = create_session_factory()
    ids: list[str] = []
    with SessionLocal() as session:
        for idx in range(3):
            entry = CatalogEntryRecord(
                tenant_id="sd-default",
                catalog_code=f"TEST-CAT-{idx}",
                title=f"测试目录 {idx}",
                lifecycle_status="active",
                summary_json={"seed": True},
            )
            session.add(entry)
            session.flush()
            mapping = LegacyObjectMappingRecord(
                tenant_id="sd-default",
                legacy_system="dsp_catalog",
                legacy_object_type="data_catalog",
                legacy_object_ref=f"legacy-{idx}",
                canonical_type="catalog_entry",
                canonical_ref=entry.id,
                source_ref=f"dsp_catalog:data_catalog:legacy-{idx}",
                mapping_status="mapped",
                evidence_json={"import_batch_id": "B-test-rollback"},
            )
            session.add(mapping)
            ids.append(mapping.legacy_object_ref)
        # Add one unrelated mapping that should NOT be rolled back.
        session.add(
            LegacyObjectMappingRecord(
                tenant_id="sd-default",
                legacy_system="dsp_metaresource",
                legacy_object_type="meta_baseinfo",
                legacy_object_ref="other-99",
                canonical_type="resource_schema_snapshot",
                canonical_ref="snap-99",
                source_ref="dsp_metaresource:meta_baseinfo:other-99",
                mapping_status="mapped",
                evidence_json={"import_batch_id": "B-other"},
            )
        )
        session.commit()
    return ids


def test_rollback_dry_run_does_not_modify(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    report = rollback(legacy_system="dsp_catalog", dry_run=True)
    assert report["dry_run"] is True
    assert report["rolled_back"] == 3
    assert report["audit_id"] is None

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        statuses = list(
            session.execute(
                select(LegacyObjectMappingRecord.mapping_status).where(
                    LegacyObjectMappingRecord.legacy_system == "dsp_catalog"
                )
            ).scalars()
        )
        assert all(s == "mapped" for s in statuses), "dry-run must not flip mapping_status"


def test_rollback_commit_flips_mapping_status_and_writes_audit(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    report = rollback(legacy_system="dsp_catalog", dry_run=False)
    assert report["rolled_back"] == 3
    assert report["audit_id"]

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        statuses = list(
            session.execute(
                select(LegacyObjectMappingRecord.mapping_status).where(
                    LegacyObjectMappingRecord.legacy_system == "dsp_catalog"
                )
            ).scalars()
        )
        assert statuses == ["rolled_back"] * 3
        # Other mapping must be untouched.
        other = session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.legacy_system == "dsp_metaresource"
            )
        ).scalar_one()
        assert other.mapping_status == "mapped"
        # Audit event must be present.
        audit = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.skill_id == "legacy.migration.rollback")
        ).scalar_one()
        assert audit.payload_json["tenant_id"] == "sd-default"
        assert audit.payload_json["rolled_back"] == 3
        assert audit.payload_json["scope"]["legacy_system"] == "dsp_catalog"


def test_rollback_idempotent(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    rollback(legacy_system="dsp_catalog", dry_run=False)
    repeat = rollback(legacy_system="dsp_catalog", dry_run=False)
    # Already-rolled-back entries count as 'already_rolled_back', not double-flipped.
    assert repeat["rolled_back"] == 0
    assert repeat["already_rolled_back"] == 3


def test_rollback_with_canonical_suspension_flips_catalog_entry(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    report = rollback(
        legacy_system="dsp_catalog",
        dry_run=False,
        also_suspend_canonical=True,
    )
    assert report["suspended_by_type"].get("catalog_entry") == 3

    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        catalog_statuses = list(
            session.execute(
                select(CatalogEntryRecord.lifecycle_status).where(
                    CatalogEntryRecord.catalog_code.like("TEST-CAT-%"),
                )
            ).scalars()
        )
        assert catalog_statuses == ["suspended"] * 3


def test_rollback_by_batch_id_scope(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    report = rollback(batch_id="B-test-rollback", dry_run=False)
    assert report["rolled_back"] == 3
    SessionLocal = create_session_factory()
    with SessionLocal() as session:
        # Mapping outside the batch_id must remain mapped.
        other = session.execute(
            select(LegacyObjectMappingRecord).where(
                LegacyObjectMappingRecord.legacy_system == "dsp_metaresource"
            )
        ).scalar_one()
        assert other.mapping_status == "mapped"


def test_rollback_requires_exactly_one_scope(seeded_mappings: list[str]) -> None:
    from zw_brain.entry.legacy_migration.rollback import rollback

    with pytest.raises(ValueError, match="exactly one"):
        rollback(dry_run=True)
    with pytest.raises(ValueError, match="only one scope"):
        rollback(legacy_system="x", batch_id="y", dry_run=True)
