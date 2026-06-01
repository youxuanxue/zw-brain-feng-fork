#!/usr/bin/env python3
"""Write-path performance benchmark — H3 write-lock critical-section cost (HIGH-2).

Every write funnels through ``SkillPipeline.write`` under a process-wide H3
RLock; inside it, ``AnchorMiddleware`` runs ``sync_database_aggregates`` which
(before this change) re-upserted the *entire* snapshot each write — O(snapshot
size) transactions, all serialized inside the lock. As the snapshot accumulates
requests over a long-running process the lock-hold time grows without bound.

This bench scales the in-memory snapshot to N requests/deliveries and measures,
per write:
- DB sessions opened by ``sync_aggregate_tables`` (proxy for transactions), and
- wall-clock of the aggregate sync (the dominant lock-held work),
contrasting a full sync (startup) with a steady-state no-change write and a
single-entity-change write (the realistic per-write delta).

Correctness note: the delta only elides *no-op* re-upserts — the persisted DB
state is identical (asserted byte-for-byte in
tests/test_write_path_aggregate_delta.py). H3 lock serialization is unchanged
and covered by tests/test_h3_snapshot_write_concurrency.py.

Usage:
    .venv/bin/python scripts/bench_write_path.py [--requests N]

Env: writes to a throwaway DB under .data/bench_write_path.db (removed first).
"""
from __future__ import annotations

import argparse
import copy
import os
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DB = REPO_ROOT / ".data" / "bench_write_path.db"
TENANT = "sd-default"


def _reset_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        (BENCH_DB.parent / f"{BENCH_DB.name}{suffix}").unlink(missing_ok=True)
    BENCH_DB.parent.mkdir(parents=True, exist_ok=True)
    os.environ["ZW_BRAIN_DB_PATH"] = str(BENCH_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db
    _db.reset_engine_cache()
    from zw_brain.shared.migrate import reset_and_upgrade
    reset_and_upgrade()


def _new_brain():
    from zw_brain.command.brain import BrainService
    from zw_brain.shared import audit as audit_bus
    from zw_brain.shared.database_store import DatabaseStore
    from zw_brain.shared.state_store import StateStore

    ds = DatabaseStore()
    ss = StateStore(database_store=ds)
    audit_bus.clear_sink()
    audit_bus.configure_sink(ds.append_audit_event)
    return BrainService(state_store=ss)


class _SessionCounter:
    def __enter__(self):
        import sys

        import zw_brain.shared.db as dbmod

        self._orig = dbmod.create_session_factory
        self.count = 0
        counter = self

        def wrapped():
            factory = counter._orig()

            def make():
                counter.count += 1
                return factory()

            return make

        self._patched = []
        for name, mod in list(sys.modules.items()):
            if name.startswith("zw_brain") and getattr(mod, "create_session_factory", None) is not None:
                mod.__dict__["create_session_factory"] = wrapped
                self._patched.append(mod)
        return self

    def __exit__(self, *exc):
        for mod in self._patched:
            mod.__dict__["create_session_factory"] = self._orig


def _grow_snapshot(brain, n: int) -> None:
    """Scale the in-memory snapshot to ~n requests (models long-running accrual)."""
    snap = brain._snapshot
    base_req = copy.deepcopy(snap["requests"][0])
    base_app = copy.deepcopy(snap["approvals"][0]) if snap.get("approvals") else {"id": "", "suggestion": "建议通过"}
    while len(snap["requests"]) < n:
        i = len(snap["requests"])
        r = copy.deepcopy(base_req)
        r["id"] = f"REQ-BENCH-{i:05d}"
        snap["requests"].append(r)
        a = copy.deepcopy(base_app)
        a["id"] = r["id"]
        snap.setdefault("approvals", []).append(a)


def _time_sync(brain, *, full: bool, repeat: int = 5) -> float:
    best = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        brain._state_store.database_store.sync_aggregate_tables(brain.snapshot(), full=full)
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=265, help="snapshot request count (default 265 ~ real sd-default application_record)")
    args = ap.parse_args()

    _reset_db()
    brain = _new_brain()
    _grow_snapshot(brain, args.requests)
    n = len(brain._snapshot["requests"])
    print(f"snapshot scaled to {n} requests / {len(brain._snapshot.get('approvals', []))} approvals\n", flush=True)

    store = brain._state_store.database_store

    # FULL sync (startup) — O(snapshot): primes the fingerprint cache + upserts all.
    with _SessionCounter() as c:
        store.sync_aggregate_tables(brain.snapshot(), full=True)
    full_sessions = c.count
    full_ms = _time_sync(brain, full=True)

    # Steady-state per-write sync, no snapshot change → O(0) entity upserts.
    with _SessionCounter() as c:
        store.sync_aggregate_tables(brain.snapshot(), full=False)
    nochange_sessions = c.count
    nochange_ms = _time_sync(brain, full=False)

    # One request changed → O(1) entity upsert.
    brain._snapshot["requests"][n // 2]["status"] = "need-fix"
    with _SessionCounter() as c:
        store.sync_aggregate_tables(brain.snapshot(), full=False)
    onechange_sessions = c.count
    # re-dirty each timed run so the change is actually synced (else cache hits)
    def _time_one_change():
        best = None
        for k in range(5):
            brain._snapshot["requests"][n // 2]["status"] = f"need-fix-{k}"
            t0 = time.perf_counter()
            store.sync_aggregate_tables(brain.snapshot(), full=False)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best * 1000
    onechange_ms = _time_one_change()

    print("=" * 78)
    print(f"per-write aggregate sync @ {n}-request snapshot")
    print("-" * 78)
    print(f"{'mode':<40}{'sessions/write':>16}{'lock-held(ms)':>18}")
    print("-" * 78)
    print(f"{'FULL sync (startup, O(snapshot))':<40}{full_sessions:>16}{full_ms:>18.1f}")
    print(f"{'per-write, no change (steady state)':<40}{nochange_sessions:>16}{nochange_ms:>18.1f}")
    print(f"{'per-write, 1 entity changed (typical)':<40}{onechange_sessions:>16}{onechange_ms:>18.1f}")
    print("=" * 78)
    print(
        f"HIGH-2: before = {full_sessions} sessions EVERY write (O(snapshot), constant\n"
        f"        regardless of what changed); after = {onechange_sessions} for a 1-entity\n"
        f"        write (O(touched)). Lock-held work {full_ms:.1f}ms → {onechange_ms:.1f}ms."
    )


if __name__ == "__main__":
    main()
