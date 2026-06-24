"""P0-1: MCP + CLI mirror the A2A M5 prod fail-closed guard.

Gap (坐实): A2A `serve_http` evaluates `get_dev_iam_bypass_enabled()` at start-up and
refuses to start under a prod deploy mode, but MCP `serve_stdio` and CLI in-process
invoke only *bound* the dev-iam-bypass synthetic full-role identity per call — they had
no start-up/entry gate. Under `ZW_BRAIN_DEPLOY_MODE in {prod,production}` + bypass env,
MCP/CLI would run with the synthetic full-role identity, making the shared C1/N1 boundary
resolver a no-op (a forged role is always honored).

These tests fail against the pre-fix code (no gate → MCP serves / CLI invokes) and pass
once the prod guard mirrors A2A.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr

import pytest


def _set_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")


@pytest.fixture()
def isolated_runtime():
    """Isolate the CLI in-process invoke so it doesn't leave the runtime module-global
    populated for later tests (the real CLI in-process path builds a BrainService via
    runtime.get_service()).

    The conftest autouse fixture already supplies a fresh per-test PG clone and resets the
    engine cache; this just additionally resets the cached BrainService on the way in/out so
    a service built here against this test's clone doesn't leak into the next test."""
    from zw_brain.command import runtime

    runtime.reset_service()
    yield
    runtime.reset_service()


# ─── MCP serve_stdio ────────────────────────────────────────────────────────


@pytest.mark.no_db
@pytest.mark.parametrize("mode", ["prod", "production", "PROD", "Production"])
def test_mcp_serve_refuses_in_prod_with_bypass(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """MCP daemon must refuse to start (exit 2) under a prod deploy mode with bypass env,
    mirroring A2A. Otherwise it serves with a full-role synthetic identity in prod."""
    _set_bypass(monkeypatch)
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", mode)
    from zw_brain.entry.mcp.server import serve_stdio

    err = io.StringIO()
    with redirect_stderr(err):
        # stdin is irrelevant: the gate returns before reading any message.
        code = serve_stdio()
    assert code == 2, f"expected refuse-to-start (2) under {mode}, got {code}"
    assert "refusing to start" in err.getvalue()


def test_mcp_serve_ok_in_non_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-prod (dev) with bypass: MCP starts normally. EOF stdin → exit 0."""
    _set_bypass(monkeypatch)
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "dev")
    from zw_brain.entry.mcp.server import serve_stdio

    err = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # immediate EOF
    with redirect_stderr(err):
        code = serve_stdio()
    assert code == 0
    assert "stdio ready" in err.getvalue()
    assert "refusing to start" not in err.getvalue()


# ─── CLI in-process invoke ──────────────────────────────────────────────────


@pytest.mark.no_db
@pytest.mark.parametrize("mode", ["prod", "production"])
def test_cli_inprocess_refuses_in_prod_with_bypass(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """CLI in-process invoke must fail closed (non-zero) under a prod deploy mode with
    bypass env, instead of running with the synthetic full-role identity.

    The gate must fire BEFORE the synthetic identity is bound or the service is touched —
    so a process whose BrainService is already cached (snapshot() not re-evaluated on the
    invoke path) still fails closed. We assert `get_service` is never reached, proving the
    explicit entry gate rather than an incidental snapshot()-time raise on first build.
    """
    _set_bypass(monkeypatch)
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", mode)
    from zw_brain.command import runtime as cmd_runtime
    from zw_brain.entry.cli import main as cli_main

    def _boom() -> None:  # pragma: no cover - must not be called
        raise AssertionError("get_service must NOT be reached when prod guard fires")

    monkeypatch.setattr(cmd_runtime, "get_service", _boom)
    code, result = cli_main._invoke_inprocess("workbench.view", {"role": "ROLE_ORGAN_OPERATER"})
    assert code == cli_main.EXIT_INVOKE_FAILED, f"expected fail-closed under {mode}, got {code}"
    assert result["error"] == "DevBypassInProductionError"


def test_cli_inprocess_ok_in_non_prod(monkeypatch: pytest.MonkeyPatch, isolated_runtime) -> None:
    """Non-prod (dev): CLI in-process invoke runs the read-only skill normally."""
    _set_bypass(monkeypatch)
    monkeypatch.setenv("ZW_BRAIN_DEPLOY_MODE", "dev")
    from zw_brain.entry.cli import main as cli_main

    code, result = cli_main._invoke_inprocess("workbench.view", {"role": "ROLE_ORGAN_OPERATER"})
    assert code == cli_main.EXIT_OK, f"expected ok in dev, got {code}: {result}"
