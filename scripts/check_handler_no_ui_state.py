#!/usr/bin/env python3
"""Preflight segment 46 (Action F) — handlers must not access ``brain._ui_state``.

Action F retired the dual source-of-truth between per-request UI role (already
moved into ``shared.ui_request_context`` ContextVar at PR #128 / Action A) and
the process-wide ``_ui_state`` mutable dict on the BrainService singleton.
Handler / helper code MUST read role from ``ctx.role`` (the SkillContext frozen
at ``invoke_skill`` entry) — NOT from ``brain._ui_state["role"]``.

Background
----------
``_UIStateProxy`` (in ``zw_brain/command/brain.py``) routes the ``role`` key
through a ContextVar so concurrent requests don't overwrite each other's role
between resolve and read. That makes ``brain._ui_state["role"]`` *technically*
concurrency-safe, but the indirection is misleading — a handler that types
``brain._ui_state["role"]`` looks like it's reading process-global state, and
a future engineer could naively reseed it. The correct read site is the
per-call SkillContext (``ctx.role``), which makes the per-request semantics
explicit at the call site.

What this guard catches
-----------------------
Any access to ``brain._ui_state`` (read or write) in any file under
``zw_brain/command/handlers/``.

Legitimate exceptions
---------------------
``b1/system_ops.py`` toggles the process-global ``brainOutage`` flag — this IS
process-global mutable state (not per-request), and the toggle handler is the
authoritative writer. It stays on the ``LEGITIMATE_USERS`` list with an
explicit rationale. Future Action D may extract a thin BrainService API for
the outage toggle; until then, the file is the single allowed handler
mutating ``_ui_state``.

Positive substitution surface
-----------------------------
- role: ``ctx.role`` (preferred — already in scope as SkillContext) or
        ``get_current_role()`` from ``zw_brain.shared.ui_request_context``
        (when ctx is not in scope, e.g. brain.py delegate shims)
- actor: ``ctx.actor`` (manifest-correct, derived from ``_actor_for_role(role)``)
- discoveryQuery: ``DEFAULT_DISCOVERY_QUERY`` (the process-global UI search
        default never mutated at runtime — import from
        ``zw_brain.command.brain``)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = REPO_ROOT / "zw_brain" / "command" / "handlers"

# Files where ``brain._ui_state`` access is explicitly allowed (each entry
# needs a reason). Adding here = explicit debt; reviewers should push back.
LEGITIMATE_USERS: dict[str, str] = {
    # outage toggle is process-global UI flag (not per-request); this handler is
    # the authoritative writer. Future Action D may extract a thin
    # BrainService.toggle_outage() API to drop this exception.
    "b1/system_ops.py": "brainOutage toggle — legitimate process-global UI flag",
}

PATTERN = re.compile(r"\bbrain\._ui_state\b")


def main() -> int:
    if not HANDLERS_DIR.exists():
        print(f"[handler-no-ui-state] skip: {HANDLERS_DIR} not present")
        return 0

    violations: list[str] = []
    for path in sorted(HANDLERS_DIR.rglob("*.py")):
        rel = path.relative_to(HANDLERS_DIR).as_posix()
        if rel in LEGITIMATE_USERS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.split("\n"), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if PATTERN.search(line):
                violations.append(f"{path}:{line_no}: forbidden brain._ui_state access")

    if violations:
        print(f"[handler-no-ui-state] FAIL: {len(violations)} forbidden brain._ui_state access(es) in handlers")
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        print()
        print("  hint: handler/helper must use `ctx.role` (preferred) or")
        print("        `get_current_role()` from zw_brain.shared.ui_request_context")
        print("        (when ctx not in scope). For actor reads use `ctx.actor`.")
        print("        For discoveryQuery use `DEFAULT_DISCOVERY_QUERY` constant.")
        print("  hint: if the access is legitimate process-global UI state (not")
        print("        per-request), add the file to LEGITIMATE_USERS in this script")
        print("        with a one-line reason.")
        return 1

    print(f"[handler-no-ui-state] OK: handlers do not access brain._ui_state outside the {len(LEGITIMATE_USERS)} legitimate file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
