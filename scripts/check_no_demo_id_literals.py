#!/usr/bin/env python3
"""check_no_demo_id_literals.py — preflight 段 36

Demo-seed entity ids (REQ-/DLV-/PKG-YYYY-MM-DD-NNNN) must not be hardcoded
anywhere under the orchestration layer. They coupled core logic to the
sd-default demo seed.

C-1 删演示单 (2026-06-02): the demo 演示单 are gone from seed_snapshot.json and
the `sync_demo_state_views` cascade in `demo_state_sync.py` is retired to a
no-op, so there is no longer any sanctioned home for these literals. The
allow-list is now **empty** (`ALLOWED_FILES = set()`) — zero demo-id literals
under `zw_brain/command/`.

Scope: every `*.py` under `zw_brain/command/`, plus every `*.spec.ts` under
`tests/e2e/` — D56.b retired the REQ-* minting sequence, so a hardcoded
REQ-/DLV-/PKG- id in a webui spec deep-links a ghost record and the test
passes vacuously (#260 caught two such fake-greens; specs must derive ids
from live lists instead, e.g. openFirstRequestDetail).
Allow-list: none. (`demo-id-ok:` line marker — `#` or `//` comment — still
honored for any deliberate future exception, but none exists.)

退出码：0 = PASS；1 = 违规。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMMAND = REPO / "zw_brain" / "command"
E2E = REPO / "tests" / "e2e"

DEMO_ID = re.compile(r"\b(?:REQ|DLV|PKG)-\d{4}-\d{2}-\d{2}-\d+\b")
LINE_EXEMPT = "demo-id-ok:"
# C-1 删演示单：零 allow-list（demo 演示单已删、cascade 已退役为 no-op）。
ALLOWED_FILES: set[Path] = set()


def _targets() -> list[Path]:
    return sorted(COMMAND.rglob("*.py")) + sorted(E2E.rglob("*.spec.ts"))


def main() -> int:
    violations: list[str] = []
    for path in _targets():
        if path in ALLOWED_FILES or not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LINE_EXEMPT in line:
                continue
            for m in DEMO_ID.finditer(line):
                rel = path.relative_to(REPO).as_posix()
                violations.append(f"{rel}:{lineno}: hardcoded demo id {m.group(0)!r}")

    if violations:
        print("[no-demo-id-literals] FAIL — derive ids from live data (e2e: read the list, don't deep-link) or justify with `demo-id-ok:`:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("[no-demo-id-literals] OK: no REQ-/DLV-/PKG- demo id literals in core + handlers + e2e specs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
