"""Background workers — drain the durable ``anchor_outbox`` table into ``audit_receipt``.

H2 fix: this is the right half of the D4 blockchain-anchoring contract (the bus
itself stays synchronous fail-closed; anchoring is the async, pluggable lower
half). Before this fix nothing in the running service ever invoked the drain
loop, so ``audit_receipt`` was永远 empty and the outbox grew unbounded.

Whitelisted for direct ``await blockchain_adapter.anchor(...)`` per
``scripts/check_blockchain_async.py`` whitelist (this is the right side of the
queue boundary).

Two entry points:
  * ``run_outbox_once()``  — one synchronous drain pass over the durable outbox
    table (no in-memory queue dependency). Safe to call from a worker thread in
    the synchronous ThreadingHTTPServer; idempotent (delivered rows are skipped,
    receipts are upserted).
  * ``AnchorWorker``        — in-process daemon thread that calls
    ``run_outbox_once()`` on an interval, started from the service lifecycle
    (``start_anchor_worker``) and stopped gracefully (``stop``). Disabled in
    tests by default — it is only auto-started when explicitly enabled.

``run_once()`` is retained as a thin async shim for existing in-process callers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading

from zw_brain.adapters.blockchain_adapter import anchor as _anchor
from zw_brain.shared import queue as _queue
from zw_brain.shared.database_store import DatabaseStore

_LOGGER = logging.getLogger(__name__)

# Default poll interval for the in-process daemon; override via env.
_DEFAULT_INTERVAL_SECONDS = 5.0


async def _drain_outbox(store: DatabaseStore) -> int:
    """Anchor every pending outbox row and write its receipt (idempotent).

    Each row is atomically *claimed* before the chain adapter is invoked (C-2);
    a row another worker/replica already holds a fresh lease on is skipped, so
    the (possibly real) anchor tx fires at most once per row even under multiple
    drain loops. ``mark_anchor_delivered`` runs only after a successful anchor;
    a failed anchor leaves the lease to expire so the row can be retried later.
    """
    processed = 0
    for record in store.list_pending_anchor_outbox():
        if not store.claim_anchor_outbox(record.content_hash):
            continue  # another worker/replica owns this row's lease
        receipt = await _anchor(record.content_hash, chain_id=record.chain_id)
        store.append_anchor_receipt(record, receipt)
        store.mark_anchor_delivered(record.content_hash)
        processed += 1
    return processed


def run_outbox_once(store: DatabaseStore | None = None) -> int:
    """Synchronous single drain pass over the durable ``anchor_outbox`` table.

    Returns the number of outbox rows turned into receipts. Each call opens its
    own short-lived event loop (``asyncio.run``) — that is correct here because
    this runs on the worker *thread's* own cadence (a handful of times a second
    at most), not once per business write. Idempotent: ``append_anchor_receipt``
    upserts and ``mark_anchor_delivered`` flips the row so re-runs are no-ops.
    """
    store = store or DatabaseStore()
    return asyncio.run(_drain_outbox(store))


async def run_once() -> int:
    """Async drain pass: in-memory queue jobs (legacy) + durable outbox table.

    Retained for in-process callers / tests that still seed the in-memory queue.
    The durable outbox is the production source of truth; the queue branch is a
    compatibility tail and is naturally empty in the running service after the
    H2 fix removed per-write in-memory enqueue.
    """
    jobs = await _queue.drain()
    store = DatabaseStore()
    seen_hashes: set[str] = set()
    processed = 0

    for job in jobs:
        if job.topic != "blockchain.anchor":
            continue
        content_hash = job.payload["content_hash"]
        receipt = await _anchor(content_hash, chain_id=job.payload.get("chain_id", "mock-chain"))
        outbox = next(
            (record for record in store.list_pending_anchor_outbox() if record.content_hash == content_hash),
            None,
        )
        if outbox is not None:
            store.append_anchor_receipt(outbox, receipt)
        store.mark_anchor_delivered(content_hash)
        seen_hashes.add(content_hash)
        processed += 1

    for record in store.list_pending_anchor_outbox():
        if record.content_hash in seen_hashes:
            continue
        if not store.claim_anchor_outbox(record.content_hash):
            continue  # another worker/replica owns this row's lease (C-2)
        receipt = await _anchor(record.content_hash, chain_id=record.chain_id)
        store.append_anchor_receipt(record, receipt)
        store.mark_anchor_delivered(record.content_hash)
        processed += 1

    return processed


class AnchorWorker:
    """In-process daemon thread that periodically drains the anchor outbox.

    Deliberately conservative: a single daemon thread polling the durable outbox
    table on an interval. Failures in a drain pass are logged and swallowed so a
    transient chain/DB error does not kill the worker (D4 fail-soft — anchoring
    is the non-blocking lower half; the synchronous audit bus is unaffected).
    """

    def __init__(self, interval_seconds: float = _DEFAULT_INTERVAL_SECONDS) -> None:
        self._interval = max(0.1, float(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="zw-brain-anchor-worker", daemon=True
        )
        self._thread.start()
        _LOGGER.info("anchor worker started (interval=%.1fs)", self._interval)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = run_outbox_once()
                if processed:
                    _LOGGER.info("anchor worker drained %d outbox row(s)", processed)
            except Exception as exc:  # noqa: BLE001 — D4 fail-soft: log, never die.
                _LOGGER.warning("anchor worker drain pass failed: %s", exc.__class__.__name__)
            # Interruptible sleep: stop() wakes us immediately.
            self._stop_event.wait(self._interval)

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        _LOGGER.info("anchor worker stopped")


# ── Service-lifecycle integration ───────────────────────────────────────────

_WORKER: AnchorWorker | None = None


def anchor_worker_enabled() -> bool:
    """Whether the in-process anchor worker should auto-start.

    Default ON in a normal deployment; OFF under pytest (so unit tests stay
    deterministic and don't race the worker) and when explicitly disabled.
    Override with ``ZW_BRAIN_ANCHOR_WORKER=1|0``.
    """
    raw = os.environ.get("ZW_BRAIN_ANCHOR_WORKER")
    if raw is not None:
        return raw.strip() not in ("", "0", "false", "False")
    # Auto-off inside the test harness unless explicitly enabled.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def start_anchor_worker() -> AnchorWorker | None:
    """Start (once) the process-global anchor worker if enabled. Idempotent."""
    global _WORKER
    if not anchor_worker_enabled():
        return None
    if _WORKER is None:
        interval = float(os.environ.get("ZW_BRAIN_ANCHOR_WORKER_INTERVAL", _DEFAULT_INTERVAL_SECONDS))
        _WORKER = AnchorWorker(interval_seconds=interval)
    _WORKER.start()
    return _WORKER


def stop_anchor_worker() -> None:
    """Stop the process-global anchor worker if running (graceful)."""
    global _WORKER
    if _WORKER is not None:
        _WORKER.stop()
        _WORKER = None
