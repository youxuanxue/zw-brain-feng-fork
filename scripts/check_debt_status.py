#!/usr/bin/env python3
"""check_debt_status — preflight guard for the debt-as-function ledger.

Mirrors check_feature_measurement.py. Runs each debt entry's assert (现算 / now-
compute) and enforces:

  invalid     → FAIL always (malformed schema / errored assert / external w/o
                owner+trigger). Fail-closed: a debt we cannot evaluate is a bug.
  stale-fixed → WARN by default (the tracked thing is gone; close the debt).
                With --strict (or PREFLIGHT_DEBT_STRICT=1) it becomes FAIL, so CI
                can be made to forbid dead debt entries lingering.
  open        → fine (debt is real and still tracked).

Empty ledger (no .testing/debt/*.debt.yaml) is OK — the infra ships before any
migration; the format/compute path must be green on an empty ledger.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from debt_status_lib import INVALID, OPEN, STALE_FIXED, compute_statuses


def main() -> int:
    strict = "--strict" in sys.argv or os.environ.get("PREFLIGHT_DEBT_STRICT") == "1"
    statuses = compute_statuses()
    if not statuses:
        print("[debt-status] OK: no debt entries (.testing/debt/ empty) — format/compute green on empty ledger")
        return 0

    invalid = [s for s in statuses if s.state == INVALID]
    stale = [s for s in statuses if s.state == STALE_FIXED]
    openc = [s for s in statuses if s.state == OPEN]

    for s in invalid:
        print(f"[debt-status] INVALID: {s.slug} ({s.path}) — {s.detail}", file=sys.stderr)
    for s in stale:
        sink = sys.stderr if strict else sys.stdout
        label = "FAIL(strict)" if strict else "WARN"
        print(f"[debt-status] {label}: {s.slug} stale-fixed — {s.detail}; 关债：rm {s.path}", file=sink)

    failed = bool(invalid) or (strict and bool(stale))
    summary = (
        f"[debt-status] scanned {len(statuses)} debt entr(ies): "
        f"open={len(openc)} stale-fixed={len(stale)} invalid={len(invalid)}"
    )
    if failed:
        print(summary, file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
