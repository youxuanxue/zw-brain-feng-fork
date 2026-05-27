"""Project clock helpers — return human-format timestamp strings.

Extracted from ``BrainService._now_*`` / ``_month_day_time`` (Phase 1.2a).
The 4 functions return *local-time*, *human-readable* formats — NOT ISO 8601.
Format choices are baked into legacy WebUI / audit-feed expectations:

- ``now_date()``        → ``"%Y-%m-%d"``         (request prefix, validity window)
- ``now_datetime()``    → ``"%Y-%m-%d %H:%M"``   (timeline / submittedAt)
- ``now_short_time()``  → ``"%H:%M"``            (delivery history rows)
- ``month_day_time()``  → ``"%m-%d %H:%M"``      (audit feed compact)

ISO timestamps live on the SQLAlchemy record's own ``.isoformat()`` — these
helpers are explicitly for UI / audit-feed projection where the legacy format
is the contract.

If we ever need to fake/freeze time for tests, replace this module with a
clock interface rather than monkey-patching ``datetime.datetime.now`` (see
discussion in Phase 2 — out of scope here).
"""
from __future__ import annotations

from datetime import datetime


def now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def now_short_time() -> str:
    return datetime.now().strftime("%H:%M")


def month_day_time() -> str:
    return datetime.now().strftime("%m-%d %H:%M")
