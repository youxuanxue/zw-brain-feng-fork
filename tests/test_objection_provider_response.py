"""F4 提供方异议响应 — provider inbox 投影 + reply/review 闭环."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tests._trusted_payload import invoke_trusted
from zw_brain.command.brain import BrainService
from zw_brain.domain.repositories.objection import ObjectionRepository
from zw_brain.shared import audit as audit_bus
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore

TENANT = "sd-default"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "objection_provider.db"
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


def _seed_provider_investigating_case() -> str:
    created = ObjectionRepository().create_case(
        {
            "objection_kind": "catalog_quality",
            "target_type": "catalog",
            "target_id": "cat-obj-inbox-001",
            "title": "提供方待响应异议",
            "complainant_org_id": "ORG-A",
            "provider_org_id": "ORG-B",
            "status": "provider_investigating",
        },
        tenant_id=TENANT,
    )
    return created.id


def test_manager_snapshot_includes_provider_objection_inbox(brain: BrainService) -> None:
    case_id = _seed_provider_investigating_case()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    rows = snap["provider"]["objection_cases"]
    assert isinstance(rows, list)
    assert any(row["id"] == case_id for row in rows)
    row = next(item for item in rows if item["id"] == case_id)
    assert row["title"] == "提供方待响应异议"
    assert row["status"] == "provider_investigating"


def test_operater_snapshot_redacts_provider_objection_inbox(brain: BrainService) -> None:
    _seed_provider_investigating_case()
    snap = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"}, role="ROLE_ORGAN_OPERATER")
    assert snap["provider"]["objection_cases"] == []


def test_objection_reply_then_review_resolve_updates_provider_inbox(brain: BrainService) -> None:
    case_id = _seed_provider_investigating_case()
    common = {"objection_id": case_id, "confirmed": True}

    reply = invoke_trusted(
        brain,
        "objection.case.reply",
        {
            **common,
            "node_name": "提供方部门核查回复",
            "opinion": "已核实字段描述",
            "action_result": "submitted",
        },
        role="ROLE_ORGAN_MANAGER",
    )["result"]
    assert reply["status"] == "provider_investigating"

    mid = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    assert any(row["id"] == case_id for row in mid["provider"]["objection_cases"])

    resolved = invoke_trusted(
        brain,
        "objection.case.review",
        {**common, "decision": "resolve", "resolved_summary": "字段已修正"},
        role="ROLE_ORGAN_MANAGER",
    )["result"]
    assert resolved["status"] == "resolved"

    after = invoke_trusted(brain, "system.snapshot", {"role": "ROLE_ORGAN_MANAGER"}, role="ROLE_ORGAN_MANAGER")
    inbox_ids = {row["id"] for row in after["provider"]["objection_cases"]}
    assert case_id not in inbox_ids
