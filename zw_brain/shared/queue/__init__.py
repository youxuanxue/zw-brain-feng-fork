"""Async dispatch queue.

Per D4 lower half + D5: blockchain anchor and other slow external calls MUST
NOT be awaited on the business path. Skills enqueue the work here; workers in
`zw_brain.background_tasks` drain and execute (with retry + alert on
exhaustion).

This in-memory queue provides fast handoff inside the current process.
Durable recovery for blockchain anchoring comes from `anchor_outbox`, which
workers also drain during recovery passes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_queue: list[Job] = []


@dataclass(frozen=True)
class Job:
    job_id: str
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))


async def enqueue(topic: str, payload: dict[str, Any]) -> str:
    """Enqueue a unit of background work; returns the job id.

    Skills use this in lieu of awaiting blockchain / external adapter
    directly. The `topic` selects which background worker handles the job
    (e.g. `blockchain.anchor`, `notification.send`, `national.relay_submit`).
    """
    job = Job(job_id=str(uuid.uuid4()), topic=topic, payload=dict(payload))
    _queue.append(job)
    return job.job_id


async def drain() -> list[Job]:
    """Test helper. Real workers replace this with a streaming consumer."""
    out, _queue[:] = list(_queue), []
    return out
