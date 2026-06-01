"""H3 regression — concurrent writes must not clobber each other's snapshot changes.

Defect: ``BrainService._snapshot`` is a process-singleton mutable dict that write
handlers edit in place; ``PersistMiddleware`` then read-modify-writes the whole snapshot
into the single ``id=1`` runtime-state row with no lock / version. Under ``ThreadingMixIn``
two concurrent writes interleave "mutate snapshot → persist", so one request's change can
be silently overwritten by another based on a stale snapshot (last-writer-wins).

Fix: ``SkillPipeline.write`` serializes the entire mutate→persist critical section with a
process-wide ``RLock`` at the single write choke point (every write path funnels through
it). These tests drive concurrent writes through the real pipeline and assert every change
survives — and that the read path is NOT under the write lock (no read/write serialization
regression).
"""

from __future__ import annotations

import threading
import time
from tempfile import TemporaryDirectory

import zw_brain.command.runtime as runtime
from tests._iaf_rest_http import bootstrap_iaf_runtime
from zw_brain.command.deps import SkillContext

_WRITERS = 16


def _make_ctx(skill_id: str, role: str = "ROLE_ORGAN_OPERATER") -> SkillContext:
    brain = runtime._service  # type: ignore[assignment]
    return SkillContext(
        skill_id=skill_id,
        role=role,
        actor=brain._actor_for_role(role),  # type: ignore[union-attr]
        confirmed=True,
        manifest={"side_effects": ["db_write"], "permissions": []},
    )


def test_concurrent_writes_do_not_clobber_snapshot() -> None:
    """N threads each append a unique marker to a shared snapshot list inside the write
    chain (with a widened read-modify-write window). The H3 lock must serialize them so
    all N markers survive — without it, last-writer-wins would drop several."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        brain = runtime._service  # type: ignore[assignment]
        assert brain is not None
        pipeline = brain._get_handler_deps().pipeline  # type: ignore[union-attr]

        # Use a dedicated list on the shared snapshot as the contested resource.
        snapshot = brain._snapshot  # type: ignore[union-attr]
        snapshot["h3_markers"] = []

        ctx = _make_ctx("catalog.entry.create_draft")
        barrier = threading.Barrier(_WRITERS)
        errors: list[Exception] = []

        def writer(idx: int) -> None:
            def mutation(_audit_id: str, _actor: str) -> dict:
                # Classic read-modify-write race: read the list, yield the GIL to
                # widen the interleaving window, then write back a +1 element.
                current = list(snapshot["h3_markers"])
                time.sleep(0.002)
                current.append(idx)
                snapshot["h3_markers"] = current
                return {"idx": idx}

            try:
                barrier.wait(timeout=10)
                pipeline.write(ctx, {"idx": idx}, mutation)
            except Exception as exc:  # noqa: BLE001 — surface to assertion
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(_WRITERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"writer errors: {errors}"
        markers = sorted(snapshot["h3_markers"])
        # The decisive assertion: every concurrent write's change survived.
        assert markers == list(range(_WRITERS)), (
            f"snapshot clobbered: expected {_WRITERS} markers, got {len(markers)} ({markers})"
        )


def test_write_lock_is_reentrant_for_nested_in_process_write() -> None:
    """A write handler that re-enters the write path on the same thread (e.g. a nested
    invoke) must not self-deadlock — the H3 lock is an RLock, not a Lock."""
    with TemporaryDirectory() as tmp, bootstrap_iaf_runtime(tmp):
        brain = runtime._service  # type: ignore[assignment]
        pipeline = brain._get_handler_deps().pipeline  # type: ignore[union-attr]
        ctx = _make_ctx("catalog.entry.create_draft")

        completed: list[str] = []

        def inner_mutation(_audit_id: str, _actor: str) -> dict:
            completed.append("inner")
            return {"ok": True}

        def outer_mutation(_audit_id: str, _actor: str) -> dict:
            # Re-enter the write path while already holding the lock.
            pipeline.write(ctx, {}, inner_mutation)
            completed.append("outer")
            return {"ok": True}

        # If the lock were a plain Lock this would deadlock; with RLock it completes.
        done = threading.Event()

        def run() -> None:
            pipeline.write(ctx, {}, outer_mutation)
            done.set()

        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=10)
        assert done.is_set(), "nested in-process write deadlocked (lock not re-entrant)"
        assert completed == ["inner", "outer"]
