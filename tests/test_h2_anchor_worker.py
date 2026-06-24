"""H2 regression — the blockchain-anchor loop must actually close in the service.

Defect: ``zw_brain.background_tasks.run_once`` had no caller anywhere in the running
service, so the durable ``anchor_outbox`` table was never drained and ``audit_receipt``
stayed empty forever (the lower half of D4 anchoring was built but never wired). The
business path also spun up a fresh event loop per write (``asyncio.run`` per mutation)
to push onto a non-durable in-memory list.

These tests assert the fixed loop:
  1. A real mutation writes a durable outbox row; ``run_outbox_once`` drains it into an
     ``audit_receipt`` row.
  2. The drain is idempotent — re-running produces no duplicate receipts and no
     re-delivery of already-delivered rows.
  3. The synchronous audit bus stays fail-closed (D4 upper half not weakened).
"""

from __future__ import annotations

from tempfile import TemporaryDirectory

import pytest

import zw_brain.command.runtime as runtime
from tests._iaf_rest_http import bootstrap_iaf_runtime
from zw_brain.background_tasks import AnchorWorker, run_outbox_once
from zw_brain.shared import audit as audit_bus
from zw_brain.shared.audit import AuditEvent, AuditWriteError
from zw_brain.shared.session_context import build_trusted_skill_payload

_OPERATOR_SNAPSHOT = {
    "tenant_id": "sd-default",
    "available_contexts": [{"org_code": "ORG-A", "role_code": "ROLE_ORGAN_OPERATER", "actor_tags": {}}],
    "current_org_code": "ORG-A",
    "current_role": "ROLE_ORGAN_OPERATER",
    "org_code": "ORG-A",
    "role_codes": ["ROLE_ORGAN_OPERATER"],
}


def _write_creates_outbox(catalog_code: str) -> None:
    payload = build_trusted_skill_payload(
        {
            "catalog_code": catalog_code,
            "title": f"H2 anchor worker {catalog_code}",
            "owner_org_id": "ORG-A",
            "summary_json": {"description": "h2 outbox drain regression"},
            "confirmed": True,
        },
        actor_snapshot=_OPERATOR_SNAPSHOT,
    )
    result = runtime._service.invoke_skill("catalog.entry.create_draft", payload)  # type: ignore[union-attr]
    assert result["ok"] is True, result


def test_worker_drains_outbox_into_receipt() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None
        assert len(store.list_audit_receipts()) == 0

        _write_creates_outbox("H2-DRAIN-1")
        pending = store.list_pending_anchor_outbox()
        assert len(pending) == 1, "write must persist a durable anchor_outbox row"

        processed = run_outbox_once(store)
        assert processed == 1

        receipts = store.list_audit_receipts()
        assert len(receipts) == 1
        assert receipts[0].content_hash == pending[0].content_hash
        assert receipts[0].tx_hash  # adapter produced a receipt
        # Outbox row is now delivered → no longer pending.
        assert len(store.list_pending_anchor_outbox()) == 0


def test_worker_drain_is_idempotent() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None

        _write_creates_outbox("H2-IDEM-1")
        assert run_outbox_once(store) == 1
        receipts_after_first = len(store.list_audit_receipts())
        assert receipts_after_first == 1

        # Second pass: nothing pending → no work, no duplicate receipts.
        assert run_outbox_once(store) == 0
        assert len(store.list_audit_receipts()) == 1


def test_worker_thread_start_stop_drains() -> None:
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None
        _write_creates_outbox("H2-THREAD-1")
        assert len(store.list_pending_anchor_outbox()) == 1

        worker = AnchorWorker(interval_seconds=0.1)
        worker.start()
        try:
            # Poll until the daemon drains the outbox (fast: mock adapter, no I/O).
            import time

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and store.list_pending_anchor_outbox():
                time.sleep(0.05)
            assert len(store.list_pending_anchor_outbox()) == 0, "worker thread must drain outbox"
            assert len(store.list_audit_receipts()) == 1
        finally:
            worker.stop()


def test_claim_is_atomic_and_prevents_double_anchor() -> None:
    """C-2: a claimed-but-not-delivered row must not be anchored a second time.

    Two concurrent drain loops both see the row in ``list_pending`` (delivered is
    still False), but only the claim winner anchors it — the loser skips. This
    prevents a duplicate (potentially real) chain tx under multi-replica deploys.
    """
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None

        _write_creates_outbox("C2-CLAIM-1")
        pending = store.list_pending_anchor_outbox()
        assert len(pending) == 1
        content_hash = pending[0].content_hash

        # First claim wins; an immediate second claim loses (fresh lease held).
        assert store.claim_anchor_outbox(content_hash) is True
        assert store.claim_anchor_outbox(content_hash) is False

        # A drain pass now finds the row still pending but already claimed → it
        # skips, so no receipt is written and the chain adapter is not re-invoked.
        assert run_outbox_once(store) == 0
        assert len(store.list_audit_receipts()) == 0


def test_stale_lease_is_reclaimable() -> None:
    """C-2: a row claimed but never delivered (worker crash) is retried once the
    lease goes stale — it must not be stranded forever."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        store = runtime._service._state_store.database_store  # type: ignore[union-attr]
        assert store is not None

        _write_creates_outbox("C2-STALE-1")
        content_hash = store.list_pending_anchor_outbox()[0].content_hash
        assert store.claim_anchor_outbox(content_hash) is True

        # Re-claim with a zero-second lease == treat any prior claim as stale.
        assert store.claim_anchor_outbox(content_hash, lease_seconds=0) is True


@pytest.mark.no_db
def test_audit_bus_still_fail_closed() -> None:
    """D4 upper-half invariant: a failing audit sink must raise AuditWriteError —
    the H2 anchor change must not have softened the synchronous audit bus."""
    audit_bus.clear_sink()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("sink down")

    audit_bus.configure_sink(_boom)
    try:
        with pytest.raises(AuditWriteError):
            audit_bus.emit(
                AuditEvent(
                    request_id="R-H2-FAILCLOSED",
                    actor="actor",
                    skill_id="catalog.entry.create_draft",
                    phase="commit",
                    payload={},
                )
            )
    finally:
        audit_bus.clear_sink()
        audit_bus.drain()
