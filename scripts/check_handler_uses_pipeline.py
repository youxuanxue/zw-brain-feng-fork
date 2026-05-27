#!/usr/bin/env python3
"""Preflight segment 43 — handlers must use deps.write, not brain._mutate.

Action B made ``deps.write(ctx, payload, fn)`` and ``deps.read(ctx, payload,
fn)`` the canonical handler-facing write/read entry points. The underlying
``deps.pipeline.write`` / ``deps.pipeline.read`` are internal implementation
detail — handlers don't access them directly. Direct calls to
``brain._mutate(...)`` and ``brain._invoke_traced_read(...)`` inside
``zw_brain/command/handlers/`` are also forbidden.

Allowed entry points for handlers:
  - ``deps.write(ctx, payload, fn)`` — full mutation chain (replaces _mutate)
  - ``deps.read(ctx, payload, fn)`` — traced read (replaces _invoke_traced_read)
  - ``deps.append_audit_feed(...)`` — audit feed append
  - ``deps.repos.X`` — repository access
  - ``ctx.role`` / ``ctx.actor`` / ``ctx.skill_id`` / ``ctx.confirmed``

Disallowed (silent regression risk):
  - ``brain._mutate(...)`` — bypasses the SkillPipeline middleware chain order
  - ``brain._invoke_traced_read(...)`` — same
  - ``brain._append_audit_feed(...)`` — direct snapshot mutation
  - ``deps.pipeline.write(...)`` — leaks internal pipeline accessor through
    the handler API; if handlers need a new entry shape, add it on HandlerDeps.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = REPO_ROOT / "zw_brain" / "command" / "handlers"

# Forbidden patterns inside handler files
FORBIDDEN = (
    (re.compile(r"\bbrain\._mutate\("), "use deps.write(ctx, payload, fn) instead"),
    (re.compile(r"\bbrain\._invoke_traced_read\("), "use deps.read(ctx, payload, fn) instead"),
    (re.compile(r"\bbrain\._append_audit_feed\("), "use deps.append_audit_feed(event_type, target, result, actor) instead"),
    (re.compile(r"\bdeps\.pipeline\.(write|read)\("), "use deps.write/deps.read — deps.pipeline.X is internal"),
)


def main() -> int:
    if not HANDLERS_DIR.exists():
        print(f"[handler-uses-pipeline] skip: {HANDLERS_DIR} not present")
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
        print(f"[handler-uses-pipeline] FAIL: {len(violations)} handler file(s) bypass deps.pipeline")
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        return 1

    print("[handler-uses-pipeline] OK: handlers use deps.pipeline / deps.append_audit_feed exclusively")
    return 0


if __name__ == "__main__":
    sys.exit(main())
