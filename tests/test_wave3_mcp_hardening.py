# Wave: 3
# Journey: Cross
# Consumer-faces: MCP
# Trace:
#   zw_brain/entry/mcp/server.py
#   zw_brain/command/brain.py (invoke_skill source=)
#   zw_brain/command/pipeline_ops.py (emit_audit source)
#   zw_brain/shared/runtime_config.py (MCP trust ladder + quota)
#   scripts/export_agent_contract.py (MCP descriptor + --check)
#   .testing/waves/wave-3-protocol-tenant-national/features/mcp-hardening.feature
"""mcp-hardening S2–S7 — real MCP entry-path behavior (no mock of the invoke path).

Every test drives the actual ``zw_brain.entry.mcp.server`` entry points
(``invoke_tool`` / ``call_tool`` / ``_handle_tools_call``) against a real
``BrainService`` built on a throwaway DB, under the dev-IAM-bypass identity the
daemon requires. Assertions read the real audit / capability_call rows or the
structured JSON-RPC envelope — nothing is stubbed.

  S2 audit + source=mcp     test_s2_*
  S3 human_confirmation     test_s3_*
  S4 structured errors      test_s4_*
  S5 exposure filter        test_s5_*
  S6 trust_level cut        test_s6_*
  S7 generated artifact     test_s7_*
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Live, MCP-exposed read capability (audit_required, no side_effects, no required input).
READ_CAP = "catalog.browse"
# Live, MCP-exposed responsibility-bearing write (side_effects + human_confirmation_required).
WRITE_CAP = "subscription.terminate"
# Live capability NOT exposed on MCP (compatibility lacks 'mcp') — used for S5.
NON_MCP_CAP = "request.submit"


@pytest.fixture
def mcp_env(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Fresh DB + dev-IAM-bypass + clean global service for one MCP test.

    Builds the global ``get_service()`` on a throwaway DB so audit / capability_call
    rows written through the real pipeline are inspectable and isolated. Resets the
    in-process MCP quota window so the S4 test is deterministic.
    """
    db_path = tmp_path / "mcp_hardening.db"
    monkeypatch.setenv("ZW_BRAIN_DB_PATH", str(db_path))
    monkeypatch.delenv("ZW_BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_DEV_IAM_BYPASS_ROLES", raising=False)
    monkeypatch.delenv("ZW_BRAIN_MCP_CALLER_TRUST_LEVEL", raising=False)
    monkeypatch.delenv("ZW_BRAIN_MCP_TOOL_QUOTA_PER_MINUTE", raising=False)

    from zw_brain.command import runtime as cmd_runtime
    from zw_brain.entry.mcp import server as mcp_server
    from zw_brain.shared import db as _db

    with _db._CACHE_LOCK:
        _db._ENGINE_CACHE.clear()
    cmd_runtime.reset_service()
    mcp_server.reset_mcp_quota()
    try:
        yield cmd_runtime.get_service()
    finally:
        cmd_runtime.reset_service()
        mcp_server.reset_mcp_quota()
        with _db._CACHE_LOCK:
            _db._ENGINE_CACHE.clear()


def _db_store(service):
    return service._state_store.database_store


# ─── S2 — MCP call is audited with source=mcp + authenticated ────────────────


def test_s2_read_call_writes_audit_event_with_source_mcp(mcp_env) -> None:
    from zw_brain.entry.mcp.server import invoke_tool

    out = invoke_tool(READ_CAP, {})
    assert out["status"] == "ok", out

    store = _db_store(mcp_env)
    events = [e for e in store.list_audit_events(limit=500) if e.skill_id == READ_CAP]
    assert events, "expected at least one audit_event for the MCP read call"
    # Every emitted phase for this call must carry the MCP provenance.
    assert all(e.payload_json.get("source") == "mcp" for e in events), [
        (e.phase, e.payload_json.get("source")) for e in events
    ]


def test_s2_read_call_records_capability_call_with_source_mcp(mcp_env) -> None:
    from zw_brain.entry.mcp.server import invoke_tool

    invoke_tool(READ_CAP, {})

    store = _db_store(mcp_env)
    calls = store.list_capability_calls_for_capability(READ_CAP)
    assert calls, "expected a capability_call row for the MCP read call"
    assert calls[-1].skill_id == READ_CAP
    assert calls[-1].input_json.get("source") == "mcp", calls[-1].input_json


def test_s2_non_mcp_in_process_call_is_not_attributed_to_mcp(mcp_env) -> None:
    """Provenance is real: a direct in-process invoke (no source) is NOT labeled mcp."""
    mcp_env.invoke_skill(READ_CAP, {})
    store = _db_store(mcp_env)
    events = [e for e in store.list_audit_events(limit=500) if e.skill_id == READ_CAP]
    assert events
    assert all(e.payload_json.get("source") == "in_process" for e in events), [
        e.payload_json.get("source") for e in events
    ]


# ─── S3 — human_confirmation_required → structured pending, not silent ───────


def test_s3_unconfirmed_write_returns_pending_confirmation(mcp_env, monkeypatch) -> None:
    """A verified caller invoking a hcr write WITHOUT confirmed=true gets a structured
    待确认 envelope — never a committed write and never a silent None (§5.4.5)."""
    # verified clears the trust cut so we reach the confirmation gate (not the trust cut).
    monkeypatch.setenv("ZW_BRAIN_MCP_CALLER_TRUST_LEVEL", "verified")
    from zw_brain.entry.mcp.server import invoke_tool

    out = invoke_tool(WRITE_CAP, {"subscription_code": "SUB-NONEXIST", "reason": "test", "role": "ROLE_ORGAN_MANAGER"})
    assert out["status"] == "pending_confirmation", out
    assert out["confirmation_required"] is True
    assert out["retry_with"] == {"confirmed": True}
    assert "result" not in out  # nothing committed


def test_s3_jsonrpc_unconfirmed_write_returns_structured_pending(mcp_env, monkeypatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_MCP_CALLER_TRUST_LEVEL", "verified")
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(
        id_=11, params={"name": WRITE_CAP, "arguments": {"subscription_code": "SUB-NONEXIST", "reason": "test", "role": "ROLE_ORGAN_MANAGER"}}
    )
    assert "result" in resp, resp  # success-shaped tools/call turn, not an error
    structured = resp["result"]["structuredContent"]
    assert structured["status"] == "pending_confirmation"
    assert resp["result"]["isError"] is False


def test_s3_tool_description_carries_confirmation_marker() -> None:
    """The generated MCP descriptor for a hcr tool advertises 'Requires user confirmation'."""
    import json

    desc = json.loads(
        (REPO_ROOT / "zw_brain" / "entry" / "mcp" / "tools" / f"{WRITE_CAP}.json").read_text(
            encoding="utf-8"
        )
    )
    assert "Requires user confirmation" in desc["description"], desc["description"]
    assert desc["annotations"]["humanConfirmationRequired"] is True


# ─── S4 — structured errors (quota_exceeded + retry_after; not a 500 black box) ─


def test_s4_quota_exceeded_returns_structured_error_with_retry_after(mcp_env, monkeypatch) -> None:
    monkeypatch.setenv("ZW_BRAIN_MCP_TOOL_QUOTA_PER_MINUTE", "1")
    from zw_brain.entry.mcp.server import _handle_tools_call, reset_mcp_quota

    reset_mcp_quota()
    first = _handle_tools_call(id_=21, params={"name": READ_CAP, "arguments": {}})
    assert "result" in first, first  # first call within quota succeeds

    second = _handle_tools_call(id_=22, params={"name": READ_CAP, "arguments": {}})
    assert "error" in second, second
    err = second["error"]
    assert err["code"] == -32005, err
    assert err["data"]["reason"] == "quota_exceeded", err
    assert isinstance(err["data"]["retry_after"], int) and err["data"]["retry_after"] >= 1, err


def test_s4_tool_not_found_distinct_from_internal_error(mcp_env) -> None:
    """tool_not_found is a distinct, typed error — not -32000 / 500 black box (S4 + S5)."""
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(id_=23, params={"name": "bogus.not.a.tool", "arguments": {}})
    assert "error" in resp, resp
    assert resp["error"]["code"] == -32601, resp
    assert resp["error"]["data"]["reason"] == "tool_not_found", resp


# ─── S5 — exposure filter: non-mcp capability invisible + tool_not_found ──────


def test_s5_non_mcp_capability_absent_from_tool_list() -> None:
    from zw_brain.entry.mcp.server import list_tools

    names = {t["name"] for t in list_tools()}
    assert READ_CAP in names  # sanity: an mcp-exposed cap is present
    assert NON_MCP_CAP not in names, f"{NON_MCP_CAP} must not be exposed on MCP"


def test_s5_direct_call_to_non_mcp_capability_is_tool_not_found(mcp_env) -> None:
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(id_=31, params={"name": NON_MCP_CAP, "arguments": {}})
    assert "error" in resp, resp
    assert resp["error"]["code"] == -32601, resp
    assert resp["error"]["data"]["reason"] == "tool_not_found", resp


def test_s5_invoke_tool_non_mcp_raises_surface_not_enabled(mcp_env) -> None:
    from zw_brain.capability_registry.runtime import SurfaceNotEnabledError
    from zw_brain.entry.mcp.server import invoke_tool

    with pytest.raises(SurfaceNotEnabledError):
        invoke_tool(NON_MCP_CAP, {})


# ─── S6 — trust_level cut: untrusted external agent denied on responsibility writes ─


def test_s6_untrusted_caller_denied_on_responsibility_write(mcp_env) -> None:
    """Default MCP caller (untrusted) calling a side-effecting / hcr capability is
    refused with reason=trust_level_insufficient — AI can't trigger 责任性写操作."""
    from zw_brain.domain.errors import TrustLevelInsufficientError
    from zw_brain.entry.mcp.server import invoke_tool

    with pytest.raises(TrustLevelInsufficientError) as exc_info:
        invoke_tool(WRITE_CAP, {"subscription_code": "SUB-X", "reason": "test", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})
    assert exc_info.value.reason == "trust_level_insufficient"
    assert exc_info.value.trust_level == "untrusted"


def test_s6_jsonrpc_untrusted_write_returns_trust_error(mcp_env) -> None:
    from zw_brain.entry.mcp.server import _handle_tools_call

    resp = _handle_tools_call(
        id_=41, params={"name": WRITE_CAP, "arguments": {"subscription_code": "SUB-X", "reason": "test", "role": "ROLE_ORGAN_MANAGER", "confirmed": True}}
    )
    assert "error" in resp, resp
    assert resp["error"]["code"] == -32003, resp
    assert resp["error"]["data"]["reason"] == "trust_level_insufficient", resp
    assert resp["error"]["data"]["trust_level"] == "untrusted", resp


def test_s6_trust_rejection_is_audited(mcp_env) -> None:
    from zw_brain.domain.errors import TrustLevelInsufficientError
    from zw_brain.entry.mcp.server import invoke_tool

    with pytest.raises(TrustLevelInsufficientError):
        invoke_tool(WRITE_CAP, {"subscription_code": "SUB-X", "reason": "test", "role": "ROLE_ORGAN_MANAGER", "confirmed": True})

    store = _db_store(mcp_env)
    rejects = [
        e
        for e in store.list_audit_events(limit=500)
        if e.skill_id == WRITE_CAP and e.phase == "reject"
    ]
    assert rejects, "trust-level rejection must be audited"
    payload = rejects[-1].payload_json
    assert payload.get("reason") == "trust_level_insufficient", payload
    assert payload.get("source") == "mcp", payload


def test_s6_verified_caller_passes_trust_cut(mcp_env, monkeypatch) -> None:
    """A promoted (verified) caller clears the trust cut — the denial is trust-based,
    not a blanket block on the capability."""
    monkeypatch.setenv("ZW_BRAIN_MCP_CALLER_TRUST_LEVEL", "verified")
    from zw_brain.domain.errors import TrustLevelInsufficientError
    from zw_brain.entry.mcp.server import invoke_tool

    # Reaches the confirmation gate (pending), i.e. trust cut did NOT fire.
    out = invoke_tool(WRITE_CAP, {"subscription_code": "SUB-X", "reason": "test", "role": "ROLE_ORGAN_MANAGER"})
    assert out["status"] == "pending_confirmation", out
    # And explicitly: no TrustLevelInsufficientError was raised.
    assert not isinstance(out, TrustLevelInsufficientError)


def test_s6_untrusted_read_capability_still_allowed(mcp_env) -> None:
    """Trust cut is scoped to responsibility-bearing writes — reads stay open."""
    from zw_brain.entry.mcp.server import invoke_tool

    out = invoke_tool(READ_CAP, {})
    assert out["status"] == "ok", out


# ─── S7 — MCP tool files are a generated artifact (no hand edits) ─────────────


def test_s7_export_agent_contract_check_reports_no_drift() -> None:
    """export_agent_contract.py --check is the reverse probe: if anyone hand-edits a
    zw_brain/entry/mcp/tools/*.json it diverges from the registry-derived content and
    --check exits non-zero."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/export_agent_contract.py", "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"contract drift:\n{proc.stdout}\n{proc.stderr}"
