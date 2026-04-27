"""Synchronous audit bus.

Per D4 upper half: every Skill invocation MUST emit `audit_event` BEFORE the
side-effect commits, and the emit MUST be synchronous. If the audit write
fails the calling Skill MUST raise — silent swallow is mechanically blocked
by `scripts/check_audit_must_block.py` (preflight section 7a).

This module keeps a process-local mirror for assertions and local
observability. Durable `audit_event` persistence happens on the
command/state-store path before business writes complete, so audit failure
still blocks the mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_buffer: list["AuditEvent"] = []


class AuditWriteError(RuntimeError):
    """Raised when the audit bus cannot persist the event. Callers MUST NOT
    catch-and-pass this — see preflight section 7a.
    """


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    actor: str  # user URN or agent URN
    skill_id: str
    phase: str  # "before" | "after" | "error"
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def emit(event: AuditEvent) -> None:
    """Persist `event` synchronously. Raises `AuditWriteError` on failure.

    The local mirror appends to a process-local buffer so tests can assert on
    emitted events.
    """
    if not event.request_id or not event.actor or not event.skill_id:
        raise AuditWriteError("audit_event missing required fields (request_id/actor/skill_id)")
    _buffer.append(event)


def drain() -> list[AuditEvent]:
    """Test helper: pop and return all buffered events."""
    out, _buffer[:] = list(_buffer), []
    return out
