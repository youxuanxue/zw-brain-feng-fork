"""P1-3: grant_delivery_access cross-aggregate fail-closed guard (46f0 class).

grant_delivery_access only validated the delivery task's own status — not the bound
application's. So a delivery task left in a grantable status (warning/reconciling/...) could
still be granted after its bound application was withdrawn/rejected/revoked (the 46f0
runtime entry). Fix: before granting, look up the bound application (task.requestId →
application_repo.get_record) and refuse (InvalidStateError) when it is in a terminal-negative
state. A valid application still grants normally.

These tests fail against the pre-fix code (terminal-negative application → grant succeeds).
"""
from __future__ import annotations

import pytest

from zw_brain.domain.errors import InvalidStateError

TENANT = "sd-default"


@pytest.fixture()
def brain(tmp_path, monkeypatch):
    """BrainService on an isolated empty DB (no seed); we inject exactly the delivery task
    + bound application the test needs."""
    db_path = tmp_path / "p1_grant.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_DEPLOY_MODE", raising=False)
    from zw_brain.shared import db as _db
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    import zw_brain.shared.audit as audit_bus
    from zw_brain.command.brain import BrainService
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.migrate import ensure_runtime_schema
    from zw_brain.shared.state_store import StateStore

    store = DatabaseStore()
    store.initialize()
    ensure_runtime_schema()
    # D4: write mutations require a durable audit sink; bind the store's append.
    audit_bus.configure_sink(store.append_audit_event)
    svc = BrainService(state_store=StateStore(database_store=store))
    yield svc
    audit_bus.clear_sink()
    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()


def _inject_grantable_task(brain, *, task_id: str, application_code: str) -> None:
    """Put a delivery task in a grantable status bound to `application_code`."""
    brain._snapshot["delivery_tasks"].append(
        {
            "id": task_id,
            "requestId": application_code,
            "name": f"{task_id} 交付任务",
            "status": "warning",  # grantable
            "channel": "数据接口",
            "history": [],
            "backflow": {},
            "aiSummary": {"summary": "", "nextAction": ""},
            "access": {},
        }
    )


def _put_application(brain, *, application_code: str, status: str) -> None:
    brain._state_store.database_store.application_repo.upsert_from_request(
        {
            "id": application_code,
            "status": status,
            "applicant": "申请人",
            "applicantDept": "申请单位",
        },
        tenant_id=TENANT,
    )


@pytest.mark.parametrize("terminal_status", ["withdrawn", "rejected", "revoked"])
def test_grant_refused_when_bound_application_terminal_negative(brain, terminal_status):
    """Bound application in a terminal-negative state → grant fail-closed (InvalidStateError),
    even though the delivery task's own status is grantable."""
    _inject_grantable_task(brain, task_id="DLV-TEST-1", application_code="REQ-TEST-1")
    _put_application(brain, application_code="REQ-TEST-1", status=terminal_status)

    with pytest.raises(InvalidStateError) as exc:
        brain.grant_delivery_access("DLV-TEST-1", role="ROLE_ORGAN_MANAGER", confirmed=True)
    assert terminal_status in str(exc.value)


def test_grant_succeeds_when_bound_application_valid(brain):
    """Bound application in a valid (non-terminal-negative) state → grant proceeds."""
    _inject_grantable_task(brain, task_id="DLV-TEST-2", application_code="REQ-TEST-2")
    _put_application(brain, application_code="REQ-TEST-2", status="granted")

    envelope = brain.grant_delivery_access("DLV-TEST-2", role="ROLE_ORGAN_MANAGER", confirmed=True)
    assert envelope["ok"] is True
    inner = envelope["result"]
    assert inner["status"] == "completed"
    assert inner["task_id"] == "DLV-TEST-2"
