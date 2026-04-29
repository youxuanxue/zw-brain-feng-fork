"""Synchronous durable audit bus."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

_buffer: list["AuditEvent"] = []
_sink: Callable[[str, str, str, str, dict[str, Any]], None] | None = None


class AuditWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    actor: str
    skill_id: str
    phase: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def configure_sink(sink: Callable[[str, str, str, str, dict[str, Any]], None]) -> None:
    global _sink
    _sink = sink


def clear_sink() -> None:
    global _sink
    _sink = None


def emit(event: AuditEvent) -> None:
    if not event.request_id or not event.actor or not event.skill_id:
        raise AuditWriteError("audit_event missing required fields (request_id/actor/skill_id)")
    if _sink is None:
        raise AuditWriteError("durable audit sink is not configured")
    try:
        _sink(event.request_id, event.actor, event.skill_id, event.phase, event.payload)
    except Exception as exc:  # noqa: BLE001
        raise AuditWriteError(str(exc)) from exc
    _buffer.append(event)


def drain() -> list[AuditEvent]:
    out, _buffer[:] = list(_buffer), []
    return out
