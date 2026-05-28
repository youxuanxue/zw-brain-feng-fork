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
    # Aggregate / cross-cutting reads that survived Action C (still needed because
    # the underlying projection is multi-source: snapshot + DB + computed). Each
    # will be lifted in Action D when the relevant domain service emerges.
    "brain.list_requests": "aggregate read; Action D",
    "brain.list_delivery_tasks": "aggregate read; Action D",
    "brain.snapshot": "snapshot dump for REST /api/snapshot; legitimate (debug surface)",
    "brain.manifests": "manifest registry pass-through; legitimate",
    "brain.invoke_skill": "credential auto-issue re-entry via invoke_skill; Action D",
    # Remaining residual surface — kept here so reviewers can see the explicit
    # "still to migrate" list. Each is harmless today but should empty out as
    # Action D lifts these helpers out of BrainService into domain services.
    "brain.grant_delivery_access": "PR#86 delegate shim — Action D retires shims",
    # ── Action H commit 4 retired (no handler-body caller left) ──────────
    # ``brain._exchange_metric_summary``: handlers now import
    # ``exchange_metric_summary`` from ``zw_brain.domain.serializers.ops_metrics``.
    # ``brain._mutate``: handler bodies use ``deps.write`` (Action B); the 2
    # remaining mentions in ``b1/intake.py`` are docstring comments (commit 3
    # updated to ``deps.write``).
    # ``brain._build_m0_work_queue_cards``: no handler-body caller after the
    # M0 work-queue removal.

    # ── Pre-Action-E historical (retired by Action E commit 4) ─────────────
    # ``brain._safe_json``: retired by Action E (handlers import safe_json from
    # zw_brain.shared.sanitization directly; brain.py wrapper removed).
    # ``brain._request_by_id`` / ``brain._delivery_by_id`` /
    # ``brain._delivery_by_request_id`` / ``brain._find_api_resource``: retired
    # by Action E (handlers + tests call deps.services.X.Y / deps.view.X.find_by_id).
    # ``brain._package_by_id``: retired by Action E (view.packages.find_by_id
    # inlines the snapshot scan; tests updated).

    # ── Pre-Action-F historical (retired by Action F) ───────────────────────
    # ``brain._ui_state``: retired by Action F (segment 46 forbids handler access;
    # role → ctx.role, actor → ctx.actor, discoveryQuery → DEFAULT_DISCOVERY_QUERY).
    # The one legitimate access path (b1/system_ops.py outage toggle) is allowlisted
    # in scripts/check_handler_no_ui_state.LEGITIMATE_USERS.

    # ── Pre-Action-C historical (kept for diff readability) ──────────────────
    # These entries were retired by Action C (snapshot reads → deps.view facade,
    # repo lookups → deps.repos, lookup helpers → deps.view.X.find_*). Listed
    # here as a no-op / audit trail; they no longer surface in handler bodies
    # but stay in the dict so reviewers tracing the Action C migration can
    # cross-reference the original entry.
    # "brain.get_resource":      retired by Action C (deps.view.resources / deps.repos.catalog)
    # "brain.get_request":       retired by Action C (deps.view.requests.find_by_id)
    # "brain.create_request":    retired by Action B/C (deps.write + deps.view)
    # "brain.get_delivery_task": retired by Action C (deps.view.delivery.find_by_id)
    # "brain.review_request":    retired by Action B/C
    # "brain.transition_api_resource": retired by Action B/C
    # "brain.get_dispute":       retired by Action C
    # "brain.list_audit_events": retired by Action C (deps.view.audit_events.list_all)
    # "brain.list_packages":     retired by Action C (deps.view.packages.list_all)
    # "brain.evaluate_tenant_policy": retired by Action B
    # "brain.list_zones":        retired by Action C (deps.view.zones.list_all)
    # "brain.update_topic_package_policy": retired by Action B
    # "brain.enrich_actor_snapshot_for_session": retired by Action B
    # "brain._snapshot":         retired by Action C (deps.view.X — segment 45 guards)
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
