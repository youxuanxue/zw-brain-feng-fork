"""Snapshot delivery_tasks enrichment for Web UI (E5 F15)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
SHADOW_DB = REPO_ROOT / ".data" / "test_delivery_snapshot_shadow.db"


@pytest.fixture(scope="module", autouse=True)
def _shadow_db() -> None:
    if not SEED_DB.is_file():
        pytest.skip("seed db missing")
    if SHADOW_DB.exists():
        SHADOW_DB.unlink()
    shutil.copy(SEED_DB, SHADOW_DB)
    os.environ["ZW_BRAIN_DB_PATH"] = str(SHADOW_DB)
    os.environ.pop("ZW_BRAIN_DATABASE_URL", None)
    from zw_brain.shared import db as _db

    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    yield


def test_system_snapshot_delivery_tasks_matches_list_delivery_tasks() -> None:
    from zw_brain.command.brain import BrainService
    from zw_brain.command.handlers.b1.system_ops import handler_system_snapshot

    brain = BrainService()
    listed = brain.list_delivery_tasks()
    snap = handler_system_snapshot(brain, "system.snapshot", {"role": "ROLE_ORGAN_OPERATER"})
    snap_tasks = snap.get("delivery_tasks") or []
    assert len(snap_tasks) == len(listed)
    assert len(snap_tasks) >= 1
