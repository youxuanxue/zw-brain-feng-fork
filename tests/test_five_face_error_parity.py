# Wave: 3
# Journey: Cross
# Consumer-faces: REST, MCP, A2A, CLI
# Trace:
#   zw_brain/shared/surface_errors.py (shared domain-error → surface-error classifier)
#   zw_brain/entry/rest/server.py (_handle_error)
#   zw_brain/entry/mcp/server.py (_structured_invocation_error)
#   zw_brain/entry/a2a/server.py (_route_post invoke error projection)
#   zw_brain/entry/cli/main.py (cmd_invoke confirmed=True self-confirm)
"""Cross-face error-contract parity (D2「5 消费面共享一套契约」).

Before this suite, A2A was the only face that collapsed every domain refusal
into an indistinguishable HTTP 500 (bare ``except Exception``), so an external
Agent could not tell a deterministic refusal from a server fault. The existing
``test_a2a_wire`` only asserted ``status != 403`` after the trust gate cleared,
explicitly noting "下游成败与 trust 无关" — i.e. it covered nothing about how a
*domain* error projects.

These tests pin the contract directly: the SAME domain exception must project to
the SAME meaning on every face —
  * ``AccessDeniedError``        → REST 403 / MCP -32004 / A2A 403  (never 500 / -32000)
  * ``NotFoundError``           → REST 422 / MCP -32006 / A2A 422
  * ``ConfirmationRequiredError`` → REST 409 / MCP structured pending / A2A 409 / CLI self-confirm

They drive the real projection paths (no mock of the classifier) and read the
real envelopes, so any face drifting back to a bare 500 / -32000 fails here.
"""
from __future__ import annotations

from typing import Any

import pytest

from zw_brain.domain.errors import (
    AccessDeniedError,
    ConfirmationRequiredError,
    InvalidStateError,
    NotFoundError,
    QuotaExceededError,
)
from zw_brain.shared.surface_errors import classify_domain_error

# ─────────────────────────────────────────────────────────────────────────────
# Layer 0 — the shared classifier is the single source of the per-surface codes.
# ─────────────────────────────────────────────────────────────────────────────


def test_classifier_is_single_source_of_truth() -> None:
    """Every face derives its status/code from this one map — assert the map itself."""
    access = classify_domain_error(AccessDeniedError("x"))
    assert access is not None
    assert access.reason == "access_denied"
    assert access.http_status == 403  # REST + A2A
    assert access.rpc_code == -32004  # MCP

    not_found = classify_domain_error(NotFoundError("x"))
    assert not_found is not None
    assert not_found.reason == "entity_not_found"
    assert not_found.http_status == 422
    assert not_found.rpc_code == -32006

    invalid = classify_domain_error(InvalidStateError("x"))
    assert invalid is not None
    assert invalid.reason == "invalid_state"
    assert invalid.http_status == 409

    confirm = classify_domain_error(ConfirmationRequiredError("skill.x"))
    assert confirm is not None
    assert confirm.reason == "confirmation_required"
    assert confirm.http_status == 409  # REST + A2A

    quota = classify_domain_error(QuotaExceededError("rate limited", retry_after=42, scope="data.search"))
    assert quota is not None
    assert quota.reason == "quota_exceeded"
    assert quota.http_status == 429  # REST + A2A
    assert quota.rpc_code == -32005  # MCP
    # The classifier echoes retry_after / scope through ``data`` so every face can
    # surface them — REST via ``**cls.data``, MCP/A2A already do.
    assert quota.data["retry_after"] == 42
    assert quota.data["scope"] == "data.search"

    # Pin the intentional unification (D44): when QuotaExceededError carries no
    # explicit scope, the classifier defaults it to the canonical bucket name
    # ``capability_call`` — NOT the old per-face ``mcp_tool_call``. This guards
    # against a silent revert of that drift.
    quota_default = classify_domain_error(QuotaExceededError("rate limited", retry_after=10))
    assert quota_default is not None
    assert quota_default.data["scope"] == "capability_call"

    # An unclassified exception returns None so each face falls back to its own
    # unclassified-error envelope (and never silently mislabels a server fault).
    assert classify_domain_error(ValueError("boom")) is None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — REST: _handle_error projects each domain error onto its HTTP status.
# Driven without a socket via object.__new__ + a capturing _json stub.
# ─────────────────────────────────────────────────────────────────────────────


class _CapturedJson:
    status: int | None = None
    body: Any = None


def _rest_project(exc: Exception) -> _CapturedJson:
    from zw_brain.entry.rest.server import RestHandler

    captured = _CapturedJson()
    handler = RestHandler.__new__(RestHandler)  # bypass socket-bound __init__
    handler.command = "POST"  # type: ignore[attr-defined]
    handler.path = "/zw-brain/api/invoke"  # type: ignore[attr-defined]
    handler._json = lambda status, body: (  # type: ignore[attr-defined,assignment]
        setattr(captured, "status", status),
        setattr(captured, "body", body),
    )
    handler._handle_error(exc)
    return captured


def test_rest_projects_domain_errors_not_500() -> None:
    access = _rest_project(AccessDeniedError("denied"))
    assert access.status == 403, access.body
    assert access.body["error"] == "access_denied"

    not_found = _rest_project(NotFoundError("missing"))
    assert not_found.status == 422, not_found.body
    assert not_found.body["error"] == "entity_not_found"

    invalid = _rest_project(InvalidStateError("bad state"))
    assert invalid.status == 409, invalid.body
    assert invalid.body["error"] == "invalid_state"

    confirm = _rest_project(ConfirmationRequiredError("subscription.terminate"))
    assert confirm.status == 409, confirm.body
    assert confirm.body["error"] == "confirmation_required"
    # REST keeps its bespoke confirmation body: the message *is* the skill_id.
    assert confirm.body["skill_id"] == "subscription.terminate"

    # Quota: 429 + ``retry_after`` / ``scope`` surface on REST too (proves the
    # ``**cls.data`` echo — consistent with MCP / A2A).
    quota = _rest_project(QuotaExceededError("rate limited", retry_after=42, scope="data.search"))
    assert quota.status == 429, quota.body
    assert quota.body["error"] == "quota_exceeded"
    assert quota.body["retry_after"] == 42, quota.body
    assert quota.body["scope"] == "data.search", quota.body

    # The ``**cls.data`` echo does NOT leak extra fields onto the sibling envelopes:
    # AccessDenied / NotFound / InvalidState classifier data is ``{}`` so their body
    # stays exactly {"error", "detail"} (no spurious retry_after / scope).
    assert set(access.body) == {"error", "detail"}, access.body
    assert set(not_found.body) == {"error", "detail"}, not_found.body
    assert set(invalid.body) == {"error", "detail"}, invalid.body

    # A genuinely unclassified exception still falls through to 500 (named, not a
    # silent black box) — that's the correct floor, only domain errors are lifted.
    unclassified = _rest_project(ValueError("boom"))
    assert unclassified.status == 500, unclassified.body


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — MCP: _structured_invocation_error projects onto JSON-RPC codes.
# ─────────────────────────────────────────────────────────────────────────────


def test_mcp_projects_domain_errors_not_internal() -> None:
    from zw_brain.entry.mcp.server import _structured_invocation_error

    access = _structured_invocation_error(1, "data.search", AccessDeniedError("denied"))
    assert access["error"]["code"] == -32004, access
    assert access["error"]["data"]["reason"] == "access_denied"

    not_found = _structured_invocation_error(2, "data.search", NotFoundError("missing"))
    assert not_found["error"]["code"] == -32006, not_found
    assert not_found["error"]["data"]["reason"] == "entity_not_found"

    # Quota: -32005 + structured retry_after / scope (mcp-hardening S4 contract).
    quota = _structured_invocation_error(
        4, "data.search", QuotaExceededError("rate limited", retry_after=42, scope="data.search")
    )
    assert quota["error"]["code"] == -32005, quota
    assert quota["error"]["data"]["reason"] == "quota_exceeded"
    assert quota["error"]["data"]["retry_after"] == 42, quota
    assert quota["error"]["data"]["scope"] == "data.search", quota

    # Unclassified → -32000 internal, reason internal_error, type still named.
    unclassified = _structured_invocation_error(3, "data.search", ValueError("boom"))
    assert unclassified["error"]["code"] == -32000, unclassified
    assert unclassified["error"]["data"]["reason"] == "internal_error"
    assert "ValueError" in unclassified["error"]["message"]


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — A2A wire: the same domain error escaping invoke projects to the HTTP
# status (403 / 422 / 409) instead of the old bare 500. Driven over a real socket
# with the invoke path monkeypatched to raise the domain error.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def a2a_wire(monkeypatch: pytest.MonkeyPatch):
    """Real A2A daemon on an ephemeral port over the conftest-supplied isolated
    empty PG clone (mirrors test_a2a_wire)."""
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS", "1")
    monkeypatch.setenv("ZW_BRAIN_DEV_IAM_BYPASS_ACK", "development-only")
    monkeypatch.delenv("ZW_BRAIN_A2A_CALLER_TRUST_LEVEL", raising=False)

    from zw_brain.command import runtime as cmd_runtime
    from zw_brain.shared import db as db_module

    with db_module._CACHE_LOCK:
        db_module._ENGINE_CACHE.clear()
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    cmd_runtime._service = None

    from tests._iaf_a2a_http import run_a2a_server, stop_a2a_server

    server, thread, port = run_a2a_server()
    try:
        yield f"http://127.0.0.1:{port}", monkeypatch
    finally:
        stop_a2a_server(server, thread)
        cmd_runtime._service = None
        with db_module._CACHE_LOCK:
            db_module._ENGINE_CACHE.clear()


# A live, A2A-exposed read capability with no required input — its surface check
# passes so the request reaches the invoke call we monkeypatch to raise.
_A2A_READ_CAP = "data.search"


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_reason"),
    [
        (AccessDeniedError("denied"), 403, "access_denied"),
        (NotFoundError("missing"), 422, "entity_not_found"),
        (InvalidStateError("bad state"), 409, "invalid_state"),
        (ConfirmationRequiredError("data.search"), 409, "confirmation_required"),
    ],
)
def test_a2a_wire_domain_error_is_classified_not_500(
    a2a_wire: tuple[str, pytest.MonkeyPatch],
    exc: Exception,
    expected_status: int,
    expected_reason: str,
) -> None:
    wire, mp = a2a_wire
    from tests._iaf_a2a_http import a2a_request
    from zw_brain.entry.a2a import server as a2a_server

    def _raise(skill_id: str, payload: dict[str, Any]) -> Any:
        raise exc

    mp.setattr(a2a_server, "_invoke_under_dev_identity", _raise)

    status, body = a2a_request(
        "POST", f"{wire}/a2a/skills/{_A2A_READ_CAP}/invoke", body={}
    )
    assert status == expected_status, (status, body)
    assert isinstance(body, dict)
    assert body["reason"] == expected_reason, body
    # The deterministic refusal must NOT be an indistinguishable server fault.
    assert status != 500, body


def test_a2a_wire_quota_carries_retry_after_not_500(
    a2a_wire: tuple[str, pytest.MonkeyPatch],
) -> None:
    """Quota escaping invoke projects to 429 with retry_after — never a bare 500.

    A2A already echoes ``**cls.data``, so retry_after / scope ride the wire; this
    pins that the structured quota signal reaches an external Agent intact.
    """
    wire, mp = a2a_wire
    from tests._iaf_a2a_http import a2a_request
    from zw_brain.entry.a2a import server as a2a_server

    def _raise(skill_id: str, payload: dict[str, Any]) -> Any:
        raise QuotaExceededError("rate limited", retry_after=42, scope="data.search")

    mp.setattr(a2a_server, "_invoke_under_dev_identity", _raise)
    status, body = a2a_request(
        "POST", f"{wire}/a2a/skills/{_A2A_READ_CAP}/invoke", body={}
    )
    assert status == 429, (status, body)
    assert isinstance(body, dict)
    assert body["reason"] == "quota_exceeded", body
    assert body["retry_after"] == 42, body
    # The structured throttle signal must NOT collapse into a server fault.
    assert status != 500, body


def test_a2a_wire_unclassified_error_still_500(
    a2a_wire: tuple[str, pytest.MonkeyPatch],
) -> None:
    """Floor: a genuinely unexpected exception is still a named 500 (not a black box)."""
    wire, mp = a2a_wire
    from tests._iaf_a2a_http import a2a_request
    from zw_brain.entry.a2a import server as a2a_server

    def _raise(skill_id: str, payload: dict[str, Any]) -> Any:
        raise RuntimeError("unexpected boom")

    mp.setattr(a2a_server, "_invoke_under_dev_identity", _raise)
    status, body = a2a_request(
        "POST", f"{wire}/a2a/skills/{_A2A_READ_CAP}/invoke", body={}
    )
    assert status == 500, (status, body)
    assert isinstance(body, dict)
    assert body["error"] == "RuntimeError"  # type named, never opaque


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — confirmation four-way contrast (the heart of requirement 2): each
# face handles ConfirmationRequiredError differently *by design* — REST/A2A 409,
# MCP structured-pending, CLI self-confirms ("running the CLI IS confirmation").
# This pins that the four philosophies stay distinct and are NOT unified.
# ─────────────────────────────────────────────────────────────────────────────


def test_confirmation_four_way_contract() -> None:
    # REST: ConfirmationRequiredError → 409 confirmation_required (asserted above too).
    rest = _rest_project(ConfirmationRequiredError("x"))
    assert rest.status == 409

    # A2A (HTTP face): classifier maps it to 409 (asserted in wire test above).
    assert classify_domain_error(ConfirmationRequiredError("x")).http_status == 409

    # MCP: confirmation is a *successful* pending_confirmation turn, not an error —
    # the MCP handler catches ConfirmationRequiredError before _structured_invocation_error
    # and returns isError=False. Assert the handler source still routes it that way.
    import inspect

    from zw_brain.entry.mcp import server as mcp_server

    handler_src = inspect.getsource(mcp_server._handle_tools_call)
    assert "ConfirmationRequiredError" in handler_src
    assert "pending_confirmation" in handler_src

    # CLI: "running the CLI IS the operator's confirmation" — cmd_invoke defaults
    # confirmed=True, so a write capability never raises ConfirmationRequiredError on
    # the CLI path. Assert that deliberate self-confirm contract is intact (NOT a 409).
    from zw_brain.entry.cli import main as cli_main

    cli_src = inspect.getsource(cli_main.cmd_invoke)
    assert 'setdefault("confirmed", True)' in cli_src
