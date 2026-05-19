#!/usr/bin/env python3
"""Preflight 段 18: db-bloat-check

Watch for sqlite physical bloat in the canonical zw-brain DB. WAL + heavy
audit_event / anchor_outbox writes can let .data/zw_brain.db reach gigabytes
while the actual rowcount stays small. That bloat made audit.list /
dashboard.render look like product bugs (77s / 30s timeouts) — the cure is
`scripts/db-vacuum.sh`, not code.

Severity:
  - size < SOFT_LIMIT (500MB): OK
  - SOFT_LIMIT <= size < HARD_LIMIT (2GB): WARN (preflight still PASS so a
    merge in progress isn't held hostage by an old dev box; print clear advice)
  - size >= HARD_LIMIT: FAIL (someone needs to run vacuum before shipping)

CI-friendly: when the canonical DB doesn't exist (CI/clean checkout), skip.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / ".data" / "zw_brain.db"

SOFT_LIMIT_BYTES = 500 * 1024 * 1024   # 500 MB
HARD_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


def _resolve_db_path() -> Path:
    env = os.environ.get("ZW_BRAIN_DB_PATH")
    if env:
        return Path(env)
    return DEFAULT_DB


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n = n / 1024  # type: ignore[assignment]
    return f"{n:.1f}PB"


def main() -> int:
    db = _resolve_db_path()
    if not db.exists():
        print(f"check_db_bloat: skip ({db} not found — CI / fresh checkout)")
        return 0

    size = db.stat().st_size
    if size < SOFT_LIMIT_BYTES:
        print(f"check_db_bloat: OK ({_human(size)} < {_human(SOFT_LIMIT_BYTES)} soft limit) — {db}")
        return 0

    advice = (
        "next-step: stop REST → bash scripts/db-vacuum.sh "
        "(--include-legacy to also clean customer_acceptance.db / pre-m0-* / dryrun residue)"
    )

    if size < HARD_LIMIT_BYTES:
        # WARN — do not fail preflight; print clear actionable advice.
        # Soft cap exists because dev boxes accumulate; preflight should
        # warn the developer but not block PR merges over operational state.
        print(
            f"check_db_bloat: WARN ({_human(size)} >= {_human(SOFT_LIMIT_BYTES)} soft limit) — {db}\n"
            f"  {advice}"
        )
        return 0

    print(
        f"check_db_bloat: FAIL ({_human(size)} >= {_human(HARD_LIMIT_BYTES)} hard limit) — {db}\n"
        f"  {advice}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
