"""Per-request role isolation — regression guard for the concurrency bug where
`role` was stashed on the process-global BrainService singleton (`_ui_state`).

Covers `_UIStateProxy` (ContextVar routing + `persistable_view`) across threads
and asyncio tasks, `BrainService.snapshot()` materialization, and
`BrainService._persist()` durable storage (DB `ui_state_json`).
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from zw_brain.command.brain import BrainService, _UIStateProxy
from zw_brain.shared import db as db_module
from zw_brain.shared.database_store import DatabaseStore
from zw_brain.shared.migrate import ensure_runtime_schema
from zw_brain.shared.state_store import StateStore
from zw_brain.shared.ui_request_context import (
    DEFAULT_ROLE,
    get_current_role,
    reset_current_role,
    set_current_role,
)


def _fresh_proxy() -> _UIStateProxy:
    return _UIStateProxy({"discoveryQuery": "q", "brainOutage": False})


def test_proxy_role_defaults_to_context_default() -> None:
    token = set_current_role(DEFAULT_ROLE)
    try:
        proxy = _fresh_proxy()
        assert proxy["role"] == DEFAULT_ROLE
        assert proxy.get("role") == DEFAULT_ROLE
        # get() default arg is ignored because role is always resolvable
        assert proxy.get("role", "ignored") == DEFAULT_ROLE
    finally:
        reset_current_role(token)


def test_proxy_role_write_routes_to_contextvar() -> None:
    proxy = _fresh_proxy()
    proxy["role"] = "ROLE_BUSIAUDIT"
    assert proxy["role"] == "ROLE_BUSIAUDIT"
    assert get_current_role() == "ROLE_BUSIAUDIT"


def test_proxy_non_role_keys_stay_on_backing_dict() -> None:
    proxy = _fresh_proxy()
    proxy["brainOutage"] = True
    assert proxy["brainOutage"] is True
    assert proxy._backing["brainOutage"] is True
    assert "role" not in proxy._backing  # invariant locked by preflight gate


def test_proxy_mapping_protocol() -> None:
    proxy = _fresh_proxy()
    assert set(proxy) == {"role", "discoveryQuery", "brainOutage"}
    assert len(proxy) == 3
    materialized = dict(proxy)
    assert materialized["role"] == get_current_role()
    assert materialized["discoveryQuery"] == "q"
    assert materialized["brainOutage"] is False


def test_dict_materialization_reflects_current_contextvar() -> None:
    proxy = _fresh_proxy()
    proxy["role"] = "ROLE_SECURITY_ADMIN"
    assert dict(proxy)["role"] == "ROLE_SECURITY_ADMIN"


@pytest.fixture()
def temp_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "ui_request_context_isolation.db"
        monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
        monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()
        ensure_runtime_schema()
        yield db_path
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


def test_persistable_view_excludes_per_request_role() -> None:
    """role is per-request (ContextVar) — must not leak into durable storage."""
    proxy = _fresh_proxy()
    proxy["role"] = "ROLE_SECURITY_ADMIN"
    view = proxy.persistable_view()
    assert "role" not in view
    assert view == {"discoveryQuery": "q", "brainOutage": False}
    # mutating the returned dict must not affect the proxy's backing
    view["discoveryQuery"] = "mutated"
    assert proxy["discoveryQuery"] == "q"


def test_persist_excludes_per_request_role_from_db(temp_db: Path) -> None:
    """BrainService._persist must write process-wide ui_state only."""
    ds = DatabaseStore()
    ds.initialize()
    brain = BrainService(state_store=StateStore(database_store=ds))
    brain._ui_state["role"] = "ROLE_SECURITY_ADMIN"
    brain._ui_state["discoveryQuery"] = "persist-me"

    assert brain.snapshot()["state"]["role"] == "ROLE_SECURITY_ADMIN"

    brain._persist()
    _, persisted_ui_state = ds.load_runtime_state()
    assert "role" not in persisted_ui_state
    assert persisted_ui_state["discoveryQuery"] == "persist-me"
    assert persisted_ui_state["brainOutage"] is False


def test_role_isolated_across_threads() -> None:
    """N threads set distinct roles concurrently; each must read back its own."""
    proxy = _fresh_proxy()
    roles = [f"ROLE_T{i}" for i in range(8)]
    barrier = threading.Barrier(len(roles))
    observed: dict[str, str] = {}

    def worker(role: str) -> None:
        proxy["role"] = role
        barrier.wait()  # force all writes to happen before any read-back
        observed[role] = proxy["role"]

    threads = [threading.Thread(target=worker, args=(r,)) for r in roles]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert observed == {r: r for r in roles}, "role bled across threads"


def test_role_isolated_across_asyncio_tasks() -> None:
    proxy = _fresh_proxy()

    async def task(role: str) -> str:
        proxy["role"] = role
        await asyncio.sleep(0.01)
        return proxy["role"]

    async def run() -> list[str]:
        return await asyncio.gather(task("ROLE_A"), task("ROLE_B"), task("ROLE_C"))

    assert asyncio.run(run()) == ["ROLE_A", "ROLE_B", "ROLE_C"]
