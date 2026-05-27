#!/usr/bin/env python3
"""Preflight segment 40 (Action A 6/6) — guard handler reverse-access to BrainService.

Background
----------
Action A migrated handler signatures to ``(deps: HandlerDeps, ctx: SkillContext, payload)``
and lifted the 6 ``brain._X_repo()`` factories + ``brain._ui_state["role"]`` reads +
high-frequency cross-cutting wrappers (``deps.write`` / ``deps.append_audit_feed``)
into the dependency container. The remaining ``brain.X`` access sites live in two
zones that the script treats differently:

1. **handler-body bypass surface** — A small whitelist of BrainService methods
   that handlers still need to call (e.g. ``brain.get_resource``, ``brain.list_requests``).
   These are aggregate-read helpers / lookup helpers that haven't been pulled
   behind a typed repo yet; they're tracked in HANDLER_WHITELIST below. New
   entries require a debt ticket — adding to the whitelist is intentionally
   verbose so reviewers notice scope creep.

2. **helper-body legacy surface** — Internal ``def _X(brain, ...)`` helpers
   keep ``brain.X`` access by design (they receive a BrainService instance from
   their handler caller via ``deps.brain_legacy``). The guard never inspects
   helper bodies — those reads are legitimate. Helpers will be retired in
   Action B (SkillPipeline) which restructures the closure-mutation pattern.

What this guard catches
-----------------------
Any **new** ``brain.X`` access inside a handler body (def handler_X(deps, ctx,
payload)) that isn't already aliased via the local ``brain = deps.brain_legacy
if deps is not None else None`` line. The intent is to prevent regressions
back to the god-object reverse-access pattern after Action A.

False positives
---------------
None expected. The script splits each file by ``def handler_`` boundaries
and only inspects handler bodies (up to the next ``def``); helper bodies are
implicitly skipped.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLERS_DIR = REPO_ROOT / "zw_brain" / "command" / "handlers"

# Handler-body access surface that's still allowed (each entry needs a reason).
# Adding here = explicit debt; reviewers should push back on growth.
HANDLER_WHITELIST: dict[str, str] = {
    # The alias itself — handler body's first line aliases brain for backward-compat.
    "brain = deps.brain_legacy": "Action A backward-compat alias (commit 2)",
    # Read-path lookups not yet behind a typed repo
    "brain.get_resource": "in-memory snapshot read; Action B/C migrates to deps.repos.resource",
    "brain.get_request": "in-memory snapshot read; Action B/C migrates to deps.repos.request",
    "brain.create_request": "writes to snapshot in addition to repo; Action B",
    "brain.get_delivery_task": "snapshot read; Action B",
    "brain.review_request": "writes to snapshot in addition to repo; Action B",
    "brain.transition_api_resource": "writes to snapshot in addition to repo; Action B",
    "brain.get_dispute": "snapshot read; Action B",
    "brain.list_audit_events": "snapshot+DB merge read; Action C",
    "brain.list_packages": "snapshot+DB merge read; Action C",
    "brain.evaluate_tenant_policy": "policy evaluator surface; Action B",
    "brain.list_zones": "snapshot read; Action C",
    "brain.update_topic_package_policy": "policy update; Action B",
    "brain.list_requests": "aggregate read; Action C",
    "brain.list_delivery_tasks": "aggregate read; Action C",
    "brain.snapshot": "snapshot dump for REST /api/snapshot; Action C",
    "brain.manifests": "manifest registry pass-through; legitimate",
    "brain.enrich_actor_snapshot_for_session": "session bootstrap; Action B",
    "brain.invoke_skill": "credential auto-issue re-entry via invoke_skill; Action B",
    # Remaining residual surface (8 sites at commit 6) — kept here so reviewers can see
    # the explicit "still to migrate" list. Each is harmless today but should empty
    # out as Action B (SkillPipeline) lifts these helpers out of BrainService.
    "brain._snapshot": "audit.list direct snapshot read (no_db fallback); Action C",
    "brain._exchange_metric_summary": "BrainService static helper; Action B pulls into shared",
    "brain._mutate": "legacy.bsp/infra path with multi-line literal; Action B",
    "brain._safe_json": "thin wrapper over shared.sanitization.safe_json; trivial inline candidate, Action B",
    "brain._build_m0_work_queue_cards": "BrainService @staticmethod aggregator; Action B pulls into shared",
    "brain.grant_delivery_access": "PR#86 delegate shim — Action B retires shims",
    "brain._ui_state": "request.py default brain alias 兜底 in tests/CLI; preserved fallback semantics",
}

# Patterns inside handler body that don't count as god-object access
# (alias line + commented-out lines + the auto-issue invoke_skill bridge).
SKIP_LINE_PATTERNS = (
    "brain = deps.brain_legacy",  # the alias line itself
    "# brain.",  # commented-out access
)

HANDLER_DEF = re.compile(r"^def (handler_[a-zA-Z0-9_]*|handler)\(", re.MULTILINE)
HELPER_DEF = re.compile(r"^def ", re.MULTILINE)
BRAIN_ACCESS = re.compile(r"\bbrain\.([_a-zA-Z][_a-zA-Z0-9]*)")


def check_file(path: Path) -> list[str]:
    """Return list of violations (file:line:access) found in path."""
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    # Identify handler bodies (start at handler def, end at next module-level def)
    matches = list(HANDLER_DEF.finditer(text))
    for m in matches:
        body_start = text.find("\n", m.end()) + 1
        # Find next def at module level — handler bodies end where any other def starts
        next_def = HELPER_DEF.search(text[body_start:])
        body_end = body_start + next_def.start() if next_def else len(text)
        body = text[body_start:body_end]

        for ln_offset, line in enumerate(body.split("\n"), start=text[:body_start].count("\n") + 1):
            stripped = line.strip()
            if any(skip in stripped for skip in SKIP_LINE_PATTERNS):
                continue
            for access in BRAIN_ACCESS.finditer(line):
                attr = access.group(1)
                full = f"brain.{attr}"
                if full in HANDLER_WHITELIST:
                    continue
                violations.append(f"{path}:{ln_offset}: handler body uses {full} (not whitelisted)")

    return violations


def main() -> int:
    if not HANDLERS_DIR.exists():
        print(f"[handler-brain-backref] skip: {HANDLERS_DIR} not present")
        return 0

    all_violations: list[str] = []
    for path in sorted(HANDLERS_DIR.rglob("*.py")):
        all_violations.extend(check_file(path))

    if all_violations:
        print(f"[handler-brain-backref] FAIL: {len(all_violations)} new handler-body brain.X reverse-access(es) detected")
        for v in all_violations[:25]:
            print(f"  {v}")
        if len(all_violations) > 25:
            print(f"  ... and {len(all_violations) - 25} more")
        print()
        print("  hint: handler bodies must use `deps.repos.X` / `ctx.role` / `deps.write(ctx, ...)` /")
        print("        `deps.append_audit_feed(...)` instead of brain.X reverse access.")
        print("  hint: if the access is legitimate (e.g. snapshot lookup), add it to")
        print("        HANDLER_WHITELIST in this file with a one-line reason.")
        return 1

    print("[handler-brain-backref] OK: handlers do not reverse-access BrainService outside the whitelist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
