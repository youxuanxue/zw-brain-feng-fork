#!/usr/bin/env python3
"""Preflight segment 45 — handlers must use deps.view / deps.repos, not direct snapshot/state_store reads.

Action C consolidated the handler-facing read paths behind two typed facades:

  - ``deps.view.X.<method>(...)`` — read facade backed by ``zw_brain.command.views``
    (snapshot deepcopy + DB merge as appropriate).
  - ``deps.repos.X`` — typed repository access (no snapshot deepcopy).

Anything that goes around these facades (direct ``brain._snapshot[...]``,
``brain._state_store.database_store.X``, or the BrainService lookup helpers
``_request_by_id`` / ``_package_by_id`` / ``_delivery_by_request_id`` /
``_delivery_by_id`` / ``_find_api_resource``) is a silent regression risk:

  * couples handlers to BrainService internals (defeats the CQRS split);
  * bypasses the views layer (deepcopy invariants, DB merge semantics);
  * makes Action D's "lift complex projections to domain services" refactor
    impossible to verify mechanically.

This guard runs across ``zw_brain/command/handlers/**/*.py`` and rejects any
file that re-introduces those access patterns. Comments are ignored.

Allowed access for handlers/helpers (positive surface):
  - ``deps.view.<facet>.<method>(...)`` — typed read facade
  - ``deps.repos.<entity>.<method>(...)`` — typed repo
  - ``ctx.role`` / ``ctx.actor`` / ``ctx.skill_id`` / ``ctx.confirmed``
  - ``deps.write(...)`` / ``deps.read(...)`` / ``deps.append_audit_feed(...)``

If a legitimate use of these forbidden patterns surfaces (e.g. a one-off
in-place mutation that views can't model), route it via the explicit
``deps.brain_legacy._snapshot[...]`` escape hatch so the intent is loud at the
call site and the guard remains clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = REPO_ROOT / "zw_brain" / "command" / "handlers"

# Forbidden access patterns inside handler files (commented lines are skipped).
#
# The first pattern matches any ``brain._snapshot`` access — subscript
# (``brain._snapshot["k"]``), attribute (``brain._snapshot.get(...)`` /
# ``brain._snapshot.setdefault(...)``), or bare reference. Read-then-mutate
# closures that need a live snapshot reference must use the explicit
# ``deps.brain_legacy._snapshot`` escape hatch so the intent is loud and
# segment 40 (handler-brain-backref) whitelist still tracks the surface.
FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bbrain\._snapshot\b"), "use deps.view.<facet>.<method>(...) instead (or deps.brain_legacy._snapshot[...] for in-place mutation escape hatch)"),
    (re.compile(r"\bbrain\._state_store\.database_store\b"), "use deps.repos.<entity> instead — no direct database_store access in handlers"),
    (re.compile(r"\bbrain\._request_by_id\("), "use deps.view.requests.find_by_id(rid) instead"),
    (re.compile(r"\bbrain\._package_by_id\("), "use deps.view.packages.find_by_id(pid) instead"),
    (re.compile(r"\bbrain\._delivery_by_request_id\("), "use deps.view.delivery.find_by_request_id(rid) instead"),
    (re.compile(r"\bbrain\._delivery_by_id\("), "use deps.view.delivery.find_by_id(tid) instead"),
    (re.compile(r"\bbrain\._find_api_resource\("), "use deps.view.resources.get_api_resource(code) instead"),
)


def main() -> int:
    if not HANDLERS_DIR.exists():
        print(f"[handler-no-direct-snapshot-read] skip: {HANDLERS_DIR} not present")
        return 0

    violations: list[str] = []
    for path in sorted(HANDLERS_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.split("\n"), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, hint in FORBIDDEN:
                if pattern.search(line):
                    violations.append(f"{path}:{line_no}: forbidden `{pattern.pattern}` — {hint}")

    if violations:
        print(f"[handler-no-direct-snapshot-read] FAIL: {len(violations)} direct snapshot/state_store read(s) in handlers")
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        print()
        print("  hint: handlers must read via deps.view.<facet>.<method>(...) (CQRS read facade)")
        print("        or deps.repos.<entity> (typed repo). Direct brain._snapshot[...] /")
        print("        brain._state_store.database_store / brain._{request,package,delivery}_by_*")
        print("        access is forbidden by Action C.")
        return 1

    print("[handler-no-direct-snapshot-read] OK: handlers read via deps.view / deps.repos exclusively")
    return 0


if __name__ == "__main__":
    sys.exit(main())
