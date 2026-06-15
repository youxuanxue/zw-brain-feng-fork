"""Shared domain-error → consumer-surface classification (D2 contract parity).

zw-brain promises D2「5 消费面（WebUI/REST/CLI/MCP/A2A）共享同一套契约」. A
domain-layer exception (``AccessDeniedError`` / ``NotFoundError`` /
``InvalidStateError`` / ``ConfirmationRequiredError`` / ``QuotaExceededError`` /
``TrustLevelInsufficientError``) carries one *meaning*; each HTTP / JSON-RPC
surface must project that meaning onto its own envelope **deterministically and
identically**, so an external caller can distinguish a deterministic refusal
(do-not-retry) from a server fault (retry-able) on every face.

Before this module the classification lived in three places:
- REST ``_handle_error`` isinstance ladder → HTTP status codes,
- MCP ``_structured_invocation_error`` isinstance ladder → JSON-RPC ``-320xx`` codes,
- A2A invoke handler had **no** ladder at all — a bare ``except Exception → 500``
  that collapsed every domain refusal into an indistinguishable server error.

This module is the single source of the ``domain-error → stable-class`` mapping.
Each surface keeps only its own envelope translation:
- HTTP faces (REST / A2A) read ``cls.http_status`` + ``cls.reason``,
- MCP reads ``cls.rpc_code`` + ``cls.reason`` (+ ``cls.data`` for ``retry_after``).

Layer: ``zw_brain.shared.surface_errors`` depends only on the domain error
hierarchy (``zw_brain.domain.errors``) and stdlib — entry layers import *down*
into it (entry → … → shared), never the reverse.

Classification is intentionally *partial*: ``classify_domain_error`` returns
``None`` for an exception it does not recognise, and each caller falls back to
its existing unclassified-error envelope (REST 500 / MCP ``-32000`` / A2A 500)
that still names the exception type — never a silent black box.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zw_brain.domain.errors import (
    AccessDeniedError,
    ConfirmationRequiredError,
    InvalidStateError,
    NotFoundError,
    QuotaExceededError,
    TrustLevelInsufficientError,
)

# HTTP statuses (shared by REST + A2A, both stdlib http.server JSON faces).
HTTP_ACCESS_DENIED = 403
HTTP_CONFIRMATION_REQUIRED = 409
HTTP_QUOTA_EXCEEDED = 429
HTTP_NOT_FOUND_ENTITY = 422
HTTP_INVALID_STATE = 409
HTTP_INTERNAL = 500

# MCP JSON-RPC application error codes (mirror mcp/server.py band; -326xx are
# protocol-reserved, application errors use the -320xx server-error band).
RPC_TRUST_DENIED = -32003
RPC_ACCESS_DENIED = -32004
RPC_QUOTA_EXCEEDED = -32005
RPC_NOT_FOUND = -32006
RPC_INTERNAL = -32000


@dataclass(frozen=True)
class DomainErrorClass:
    """A stable, surface-agnostic classification of a domain exception.

    ``reason`` is the machine-actionable, surface-independent signal (the same
    string every face exposes). ``http_status`` / ``rpc_code`` are the
    per-surface projections. ``data`` carries any extra structured fields
    (e.g. ``retry_after`` for quota) the surfaces should echo through.
    """

    reason: str
    http_status: int
    rpc_code: int
    data: dict[str, Any] = field(default_factory=dict)


def classify_domain_error(exc: BaseException) -> DomainErrorClass | None:
    """Map a known domain exception to its stable cross-surface classification.

    Returns ``None`` for an unrecognised exception so the caller falls back to
    its own unclassified-error envelope. Ordering mirrors the historical REST /
    MCP isinstance ladders exactly so external behaviour is unchanged:
    ``QuotaExceededError`` and ``TrustLevelInsufficientError`` (a subclass of
    ``AccessDeniedError``) are checked before the broader ``AccessDeniedError``.
    """
    if isinstance(exc, QuotaExceededError):
        return DomainErrorClass(
            reason="quota_exceeded",
            http_status=HTTP_QUOTA_EXCEEDED,
            rpc_code=RPC_QUOTA_EXCEEDED,
            data={"retry_after": exc.retry_after, "scope": exc.scope or "capability_call"},
        )
    if isinstance(exc, TrustLevelInsufficientError):
        # Subclass of AccessDeniedError; checked first so it keeps the
        # trust-specific reason + RPC code (HTTP faces still surface 403).
        return DomainErrorClass(
            reason=exc.reason,  # "trust_level_insufficient"
            http_status=HTTP_ACCESS_DENIED,
            rpc_code=RPC_TRUST_DENIED,
            data={"trust_level": exc.trust_level},
        )
    if isinstance(exc, ConfirmationRequiredError):
        return DomainErrorClass(
            reason="confirmation_required",
            http_status=HTTP_CONFIRMATION_REQUIRED,
            # MCP projects confirmation as a *successful* pending_confirmation
            # turn (not an error), so its rpc_code here is the last-resort
            # internal code and is never consulted by the MCP surface.
            rpc_code=RPC_INTERNAL,
        )
    if isinstance(exc, NotFoundError):
        return DomainErrorClass(
            reason="entity_not_found",
            http_status=HTTP_NOT_FOUND_ENTITY,
            rpc_code=RPC_NOT_FOUND,
        )
    if isinstance(exc, InvalidStateError):
        return DomainErrorClass(
            reason="invalid_state",
            http_status=HTTP_INVALID_STATE,
            rpc_code=RPC_INTERNAL,
        )
    if isinstance(exc, AccessDeniedError):
        return DomainErrorClass(
            reason="access_denied",
            http_status=HTTP_ACCESS_DENIED,
            rpc_code=RPC_ACCESS_DENIED,
        )
    return None
