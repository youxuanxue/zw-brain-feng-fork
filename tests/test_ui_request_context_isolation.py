"""Per-request role isolation — regression guard for the concurrency bug where
`role` was stashed on the process-global BrainService singleton (`_ui_state`).

Covers `_UIStateProxy` (the drop-in mapping) + the backing ContextVar across
threads and asyncio tasks, plus the `dict(proxy)` materialization used by
`BrainService.snapshot()` / `_persist`.
"""

from __future__ import annotations

import asyncio
import threading

from zw_brain.command.brain import _UIStateProxy
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
