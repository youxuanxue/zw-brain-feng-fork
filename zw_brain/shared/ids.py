"""Project ID generators — request IDs + audit event IDs.

Extracted from ``BrainService._new_audit_id`` / ``_new_request_id`` (Phase 1.2b).

- ``new_audit_id()``: stateless — date + HHMMSS + microsecond suffix. The
  microsecond resolution keeps audit events within a millisecond burst unique.
- ``next_request_id(existing_ids)``: takes the existing snapshot's request IDs
  and returns ``REQ-YYYY-MM-DD-NNNN`` with the next 4-digit sequence for today.
  The snapshot scan stays at the caller — keeps this module dependency-free.

ID format contracts are baked into J1/J2 e2e demos + audit feed UI:
- ``REQ-`` prefix is what `_delivery_task_id_for_request` rewrites to ``DLV-``;
- ``AE-`` prefix is what audit-feed grep filters expect.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime


def new_audit_id() -> str:
    return f"AE-{datetime.now():%Y-%m-%d-%H%M%S%f}"


def next_request_id(existing_ids: Iterable[str]) -> str:
    prefix = f"REQ-{datetime.now():%Y-%m-%d}-"
    seq = 1
    for item_id in existing_ids:
        if item_id.startswith(prefix):
            try:
                seq = max(seq, int(item_id.rsplit("-", 1)[-1]) + 1)
            except ValueError:
                continue
    return f"{prefix}{seq:04d}"
