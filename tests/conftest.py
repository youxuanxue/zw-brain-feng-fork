"""Root pytest conftest — deterministic per-test environment isolation.

WHY THIS EXISTS
---------------
~50 test modules nakedly set ``ZW_BRAIN_DB_PATH`` (and sibling ``ZW_BRAIN_*``
knobs) via ``os.environ[...] = ...`` / ``monkeypatch.setenv`` / module- or
session-scoped autouse fixtures with **no teardown**. Combined with the
process-wide engine cache in :mod:`zw_brain.shared.db` (``_ENGINE_CACHE``, keyed
by DB URL), this leaks two things across module boundaries:

1. **The env path** — a module that points ``ZW_BRAIN_DB_PATH`` at a
   ``TemporaryDirectory`` shadow DB and never restores it leaves the env var
   pointing at a now-deleted file. A later module that relies on the default
   seed DB silently reads the leaked (deleted/foreign) path instead — empty
   rows or ``no such table`` depending on order.
2. **Cached engines** — ``_ENGINE_CACHE`` holds a live SQLAlchemy engine bound
   to whatever URL was first seen. A leaked or stale entry can serve a later
   test a connection pool pointed at the wrong (or vanished) file, and leaves
   open file handles.

The net effect is an order-sensitive / flaky full-suite run.

WHAT THIS DOES
--------------
A single **function-scoped autouse** fixture that GUARANTEES isolation
regardless of what any individual fixture does:

* snapshots the full ``os.environ`` at the start of every test and restores it
  exactly afterwards (re-adds deleted keys, resets mutated keys, removes added
  keys) — so any naked ``os.environ[...] =`` a test (or its function-scoped
  setup) performs is undone;
* resets the engine cache (disposing engines to free file handles) **both
  before and after** each test, so a leaked path/engine from a prior test
  cannot bleed in, and this test's engines do not bleed out.

COMPOSITION WITH HIGHER-SCOPED FIXTURES
---------------------------------------
pytest tears finalizers down inner-scope-first: a ``module``/``session``
autouse ``_shadow_db`` fixture sets up *before* this function fixture and tears
down *after* it. So the env snapshot taken here already includes that fixture's
shadow path, and restoring to the snapshot preserves it for the next test in
the same module — this fixture only undoes per-function mutations, never the
legitimate higher-scoped setup. The cross-module leak is neutralised by the
unconditional cache reset (stale engine cannot survive) plus the fact that the
*next* module's higher-scoped fixture re-asserts its own env before its first
test's snapshot is taken.

This is purely environmental hygiene: no Mocks, no assertion changes.

``tests/e2e/conftest.py`` is a plain config module (dataclasses + helpers, no
pytest fixtures), so this root conftest composes with it without conflict.
"""

from __future__ import annotations

import os

import pytest

from zw_brain.shared import db as _db


def _reset_engine_cache() -> None:
    """Drop every cached engine, disposing it to free SQLite file handles.

    Prefers the module's own :func:`zw_brain.shared.db.reset_engine_cache`
    (which disposes engines under the cache lock) and falls back to a manual
    dispose+clear if that helper is ever renamed/removed, so isolation never
    silently degrades to a no-op.
    """
    reset = getattr(_db, "reset_engine_cache", None)
    if callable(reset):
        reset()
        return
    # Defensive fallback — keep isolation even if the helper disappears.
    lock = getattr(_db, "_CACHE_LOCK", None)
    cache = getattr(_db, "_ENGINE_CACHE", None)
    if cache is None:
        return
    ctx = lock if lock is not None else _NullCtx()
    with ctx:
        for entry in list(cache.values()):
            engine = entry[0] if isinstance(entry, tuple) else entry
            dispose = getattr(engine, "dispose", None)
            if callable(dispose):
                try:
                    dispose()
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
        cache.clear()


class _NullCtx:
    def __enter__(self) -> None:  # pragma: no cover - trivial fallback
        return None

    def __exit__(self, *_exc: object) -> bool:  # pragma: no cover
        return False


def _restore_env(snapshot: dict[str, str]) -> None:
    """Restore ``os.environ`` to exactly ``snapshot``.

    Removes keys added during the test, restores keys deleted during the test,
    and resets keys whose value changed.
    """
    current = set(os.environ.keys())
    saved = set(snapshot.keys())
    for added in current - saved:
        del os.environ[added]
    for key in saved:
        if os.environ.get(key) != snapshot[key]:
            os.environ[key] = snapshot[key]


@pytest.fixture(autouse=True)
def _isolate_db_env() -> None:
    """Autouse, function-scoped: env snapshot/restore + engine-cache reset.

    See module docstring for the full rationale and the composition guarantee
    with module-/session-scoped autouse DB fixtures.
    """
    # A leaked engine/path from a prior test must not bleed into this one.
    _reset_engine_cache()
    env_snapshot = dict(os.environ)
    try:
        yield
    finally:
        # This test's engines/path must not bleed into the next one.
        _reset_engine_cache()
        _restore_env(env_snapshot)
