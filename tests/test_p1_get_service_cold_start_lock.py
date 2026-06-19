"""P1-4: get_service() cold-start double-checked lock.

runtime.get_service had an unlocked `if _service is None:` init. Under ThreadingHTTPServer
(a thread per request) concurrent first requests could both see None and each build a
BrainService + run sync_aggregate_tables(full=True) (~528 upserts). Idempotent but wasteful
and unsynchronized.

This test fires many threads at a freshly-reset get_service and asserts the heavy init runs
exactly once. A small delay injected into the init window makes the race deterministic; the
unlocked code constructs >1 service, the double-checked-locked code constructs exactly one.
"""
from __future__ import annotations

import threading

import pytest


@pytest.fixture()
def fresh_runtime(monkeypatch):
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_DEPLOY_MODE", raising=False)
    from zw_brain.command import runtime

    runtime.reset_service()
    yield runtime
    runtime.reset_service()


def test_concurrent_first_requests_init_once(fresh_runtime, monkeypatch):
    """N concurrent first requests → heavy init runs exactly once, no thread crashes, all
    callers get the same instance.

    Pre-fix (unlocked `if _service is None`) the racing threads re-enter the init body and
    re-run DatabaseStore.initialize()/ensure_runtime_schema()/create_all concurrently — which
    blows up with OperationalError (e.g. "table runtime_state already exists") and/or builds
    multiple services. The double-checked lock serializes init to exactly one.
    """
    runtime = fresh_runtime
    from zw_brain.command import brain as brain_mod

    init_count = {"n": 0}
    init_lock = threading.Lock()
    real_init = brain_mod.BrainService.__init__

    def counting_init(self, *args, **kwargs):
        with init_lock:
            init_count["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(brain_mod.BrainService, "__init__", counting_init)

    # Widen the cold-start window so an unlocked `if _service is None` lets multiple threads
    # into the init body before the first publishes `_service`. We delay inside the very
    # first heavy step (DatabaseStore.initialize) which runs *before* _service is set.
    from zw_brain.shared.database_store import DatabaseStore

    real_initialize = DatabaseStore.initialize

    def slow_initialize(self, *args, **kwargs):
        threading.Event().wait(0.05)
        return real_initialize(self, *args, **kwargs)

    monkeypatch.setattr(DatabaseStore, "initialize", slow_initialize)

    results: list[object] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()  # release all threads together to maximize the race
        try:
            results.append(runtime.get_service())
        except BaseException as exc:  # noqa: BLE001 — capture any cold-start race crash
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"cold-start race crashed {len(errors)} thread(s): {errors[:1]}"
    assert init_count["n"] == 1, f"expected exactly one init, got {init_count['n']}"
    assert len(results) == 8
    # All callers observe the same single service instance.
    assert all(r is results[0] for r in results)
