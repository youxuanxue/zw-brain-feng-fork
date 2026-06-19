"""Regression lock for the root ``tests/conftest.py`` DB-env isolation contract.

WHY THIS EXISTS
---------------
The function-scoped autouse fixture ``_isolate_db_env`` in ``tests/conftest.py``
is the single global safety net against the historical cross-module leak: ~30
fixtures nakedly mutated a process-wide env var (historically the DB-path knob)
with **no teardown**, and the process-wide ``zw_brain.shared.db._ENGINE_CACHE``
then bled a stale engine into a later test. The net is invisible when green, so a
future edit that removes ``autouse=True`` or breaks the snapshot/restore would
silently re-open the leak without any test going red.

This module pins the contract explicitly so such a regression is caught, using a
neutral throwaway env var as the canary (the contract is dialect-agnostic — it is
about os.environ snapshot/restore, not any specific knob):

1. ``test_naked_env_mutation_is_undone_between_tests`` — a test that nakedly
   mutates the canary env var (exactly the leak pattern) must NOT bleed into the
   next test; the autouse fixture restores the env after every test.
2. ``test_engine_cache_reset_around_each_test`` — the engine cache is reset
   before each test, so a stale cached engine from a prior test cannot serve a
   connection to the wrong/vanished database.

These are pure environmental-hygiene assertions — no Mocks, no business
behaviour, no DB rows. The two tests are intentionally order-coupled (test 1
leaks, the next test verifies the leak was undone), which is exactly the
property under test; pytest runs intra-module tests top-to-bottom.
"""
from __future__ import annotations

import os

from zw_brain.shared import db as _db

# Neutral throwaway canary — any env key works; the contract under test is
# os.environ snapshot/restore by the conftest autouse fixture.
_CANARY_ENV = "ZW_BRAIN_TEST_ISOLATION_CANARY"
_SENTINEL = "isolation-sentinel-value"


def test_naked_env_mutation_is_undone_between_tests() -> None:
    # Precondition: a prior test's naked mutation must already have been undone
    # by the autouse fixture before this test started.
    assert os.environ.get(_CANARY_ENV) != _SENTINEL, (
        f"{_CANARY_ENV} leaked into this test — the conftest autouse isolation "
        "fixture (_isolate_db_env) is not restoring os.environ. See tests/conftest.py."
    )
    # Reproduce the historical leak pattern: naked assignment, no teardown.
    os.environ[_CANARY_ENV] = _SENTINEL


def test_env_restored_after_prior_naked_mutation() -> None:
    # The prior test leaked _SENTINEL with no teardown of its own. If the
    # autouse fixture is doing its job, this test never sees it.
    assert os.environ.get(_CANARY_ENV) != _SENTINEL, (
        f"Naked {_CANARY_ENV} mutation from a prior test bled through — the "
        "conftest autouse isolation fixture is broken (autouse removed or "
        "snapshot/restore regressed). See tests/conftest.py."
    )


def test_engine_cache_reset_around_each_test() -> None:
    # The autouse fixture resets the engine cache both before and after each
    # test. Within a test the cache may be populated by code under test, but it
    # must start empty here because nothing in this test touched the DB yet and
    # the pre-test reset ran.
    cache = getattr(_db, "_ENGINE_CACHE", None)
    assert cache is not None, "zw_brain.shared.db._ENGINE_CACHE missing"
    assert len(cache) == 0, (
        f"engine cache not reset before this test (size={len(cache)}); the "
        "conftest autouse fixture's pre-test reset_engine_cache() regressed."
    )
