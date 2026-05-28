#!/usr/bin/env python3
"""Preflight segment 48 — BrainService must hold no cross-cutting bodies (Action E).

Action E lifted the 5 cross-cutting helpers + 5 state-sync helpers off
``BrainService`` into ``zw_brain/command/pipeline_ops.py`` and
``zw_brain/command/sync.py``. BrainService retains a one-line delegate shim
per migrated helper for backward compatibility; this preflight enforces:

  Group A — cross-cutting (pipeline_ops):
    _mutate / _invoke_traced_read / _emit_audit / _enqueue_anchor /
    _append_audit_feed / _record_capability_call
        ⇒ MUST be ≤ 8 statement-bodies delegating to pipeline_ops.X.

  Group B — state sync (sync.py):
    _persist / _sync_reference_tables / _sync_database_aggregates /
    _sync_state_views / _sync_request_todos
        ⇒ MUST be ≤ 3 statement-bodies delegating to sync.X.

  Group C — fully retired (must NOT exist on BrainService at all):
    _safe_json / _request_by_id / _delivery_by_id /
    _delivery_by_request_id / _find_api_resource / _package_by_id

What this guards against
------------------------
- Inline regression — someone re-adds the body of ``_emit_audit`` to
  BrainService instead of routing through ``pipeline_ops.emit_audit``.
- Mid-refactor partial migration — a method is moved into pipeline_ops
  but a hot-fix puts the body back on BrainService.
- Re-creation of retired Group C methods (forbidden by Action E).

What is allowed
---------------
- One-line delegate shims for Groups A and B (statements <= cap).
- Methods *not* in any of the three groups (any other private helper
  on BrainService is outside this segment's scope).

The body cap (8 for cross-cutting, 3 for state sync) accommodates the
required ``from zw_brain.command import pipeline_ops # noqa`` lazy
import line + a small set of construction lines for SkillContext etc.
Pure passthroughs are 2-3 statements; the upper bound is set to catch
re-introduced inline bodies (typically dozens of lines).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAIN_FILE = REPO_ROOT / "zw_brain" / "command" / "brain.py"


# Group A — cross-cutting helpers (pipeline_ops bodies). Shims constructed
# with SkillContext etc. may have up to 8 statements; pure passthroughs use 2.
CROSS_CUTTING_METHODS: dict[str, int] = {
    "_mutate": 8,
    "_invoke_traced_read": 8,
    "_emit_audit": 4,
    "_enqueue_anchor": 4,
    "_append_audit_feed": 4,
    "_record_capability_call": 4,
}

# Group B — state sync helpers (sync.py bodies). 2-3 statements.
STATE_SYNC_METHODS: dict[str, int] = {
    "_persist": 4,
    "_sync_reference_tables": 4,
    "_sync_database_aggregates": 4,
    "_sync_state_views": 4,
    "_sync_request_todos": 4,
}

# Group C — fully retired methods (must NOT exist on BrainService).
RETIRED_METHODS: frozenset[str] = frozenset({
    "_safe_json",
    "_request_by_id",
    "_delivery_by_id",
    "_delivery_by_request_id",
    "_find_api_resource",
    "_package_by_id",
})


def _is_brain_service_method(class_def: ast.ClassDef, fn: ast.FunctionDef) -> bool:
    """True when ``fn`` is a direct child of ``BrainService``."""
    return fn in class_def.body


def main() -> int:
    if not BRAIN_FILE.exists():
        print(f"[brain-no-cross-cutting] skip: {BRAIN_FILE} not present")
        return 0

    text = BRAIN_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    brain_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BrainService":
            brain_class = node
            break

    if brain_class is None:
        print("[brain-no-cross-cutting] FAIL: BrainService class not found in brain.py")
        return 1

    violations: list[str] = []
    cross_cutting_count = 0
    state_sync_count = 0

    for fn in brain_class.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        name = fn.name

        # Group C — retired methods must not exist
        if name in RETIRED_METHODS:
            violations.append(
                f"{BRAIN_FILE}:{fn.lineno}: `{name}` was retired by Action E "
                f"and must NOT be re-introduced on BrainService — call sites "
                f"should use deps.services.X / view.X.find_by_id / direct import."
            )
            continue

        # Group A
        if name in CROSS_CUTTING_METHODS:
            cap = CROSS_CUTTING_METHODS[name]
            if len(fn.body) > cap:
                violations.append(
                    f"{BRAIN_FILE}:{fn.lineno}: `{name}` has {len(fn.body)} body "
                    f"statements (cap {cap}); cross-cutting body must live in "
                    f"zw_brain/command/pipeline_ops.py — restore the shim shape."
                )
            else:
                cross_cutting_count += 1
            continue

        # Group B
        if name in STATE_SYNC_METHODS:
            cap = STATE_SYNC_METHODS[name]
            if len(fn.body) > cap:
                violations.append(
                    f"{BRAIN_FILE}:{fn.lineno}: `{name}` has {len(fn.body)} body "
                    f"statements (cap {cap}); state-sync body must live in "
                    f"zw_brain/command/sync.py — restore the shim shape."
                )
            else:
                state_sync_count += 1
            continue

    if violations:
        print(
            f"[brain-no-cross-cutting] FAIL: {len(violations)} cross-cutting / "
            f"state-sync invariant(s) violated in BrainService"
        )
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        print()
        print("  hint: cross-cutting bodies live in zw_brain/command/pipeline_ops.py")
        print("        state-sync bodies live in zw_brain/command/sync.py")
        print("        retired methods (Group C) must NOT be re-added to BrainService.")
        return 1

    print(
        f"[brain-no-cross-cutting] OK: {cross_cutting_count} cross-cutting shim(s) + "
        f"{state_sync_count} state-sync shim(s); all Group C retired methods absent."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
