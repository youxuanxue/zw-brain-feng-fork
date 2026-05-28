#!/usr/bin/env python3
"""Preflight segment 46 — BrainService must hold no domain method bodies.

Action D split BrainService's 137 private methods into 7 domain services
under ``zw_brain/domain/services/``. After commit 4, each domain method on
BrainService is a one-line delegate shim:

    def _catalog_entry_status(self, catalog_code: Any) -> str | None:
        return self._get_handler_deps().services.catalog.entry_status(catalog_code)

This preflight segment ensures the boundary holds: any future "real"
implementation of a ``_catalog_*`` / ``_topic_*`` / ``_delivery_*`` /
``_application_*`` / ``_request_*`` / ``_provider_*`` / ``_governance_*``
method in brain.py is rejected. The check enforces "shim-only" structure:
each matching method body must be a single ``return`` statement.

What this guards against
------------------------
- Inline regression — a new branch adds a `_catalog_X` method on BrainService
  with a body, slipping past code review.
- Mid-refactor partial migration — a method is moved into a service but a
  hot-fix puts the body back on BrainService.

What is allowed
---------------
- One-line delegate shims that route to ``self._get_handler_deps().services.X.Y``.
- Any method whose name does NOT match the seven domain prefixes (cross-cutting
  helpers like `_mutate`, `_emit_audit`, `_sync_*` remain on BrainService for now;
  Action E is the next refactor that lifts them).
- Public methods (no leading underscore) — `list_requests`, `list_delivery_tasks`,
  `grant_delivery_access` etc. are intentionally not in this segment's scope.

Failure mode
------------
If a forbidden pattern is found, the script lists the file:line and the method
name. To fix: move the implementation into the corresponding service class.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAIN_FILE = REPO_ROOT / "zw_brain" / "command" / "brain.py"

# Domain method prefixes — these names own a domain service home, so any
# BrainService method matching them must be a thin one-line delegate shim.
DOMAIN_PREFIXES = (
    "_catalog_",
    "_topic_",
    "_delivery_",
    "_application_",
    "_request_",
    "_provider_",
    "_governance_",
)

# Methods exempt from the shim-only rule. Reason for each exemption:
#   _delivery_repo / _topic_package_repo / _governance_projection_repo:
#       factory accessors for the corresponding Repository (one of 5 *_repo
#       helpers on BrainService). Their name matches a domain prefix but
#       they're not domain methods — they return a Repository handle.
EXEMPT_METHODS = frozenset({
    "_delivery_repo",
    "_topic_package_repo",
    "_governance_projection_repo",
})


def _is_one_line_shim(node: ast.FunctionDef) -> bool:
    """A delegate shim is a method whose body is a single Return statement that
    calls ``self._get_handler_deps().services.<name>.<method>(...)``.
    """
    if len(node.body) != 1:
        return False
    stmt = node.body[0]
    if not isinstance(stmt, ast.Return):
        return False
    if not isinstance(stmt.value, ast.Call):
        return False
    # The chain we expect: <expr>.services.<svc>.<method>(...)
    func = stmt.value.func
    if not isinstance(func, ast.Attribute):
        return False
    if not isinstance(func.value, ast.Attribute):
        return False
    if not isinstance(func.value.value, ast.Attribute):
        return False
    return func.value.value.attr == "services"


def _is_domain_method_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in DOMAIN_PREFIXES)


def main() -> int:
    if not BRAIN_FILE.exists():
        print(f"[brain-no-domain-method] skip: {BRAIN_FILE} not present")
        return 0

    text = BRAIN_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    violations: list[str] = []
    shim_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not _is_domain_method_name(node.name):
            continue
        if node.name in EXEMPT_METHODS:
            continue
        if _is_one_line_shim(node):
            shim_count += 1
            continue
        violations.append(
            f"{BRAIN_FILE}:{node.lineno}: `{node.name}` has a domain-method "
            f"name but is not a one-line delegate shim — move body into the "
            f"corresponding service under zw_brain/domain/services/"
        )

    if violations:
        print(
            f"[brain-no-domain-method] FAIL: {len(violations)} domain method(s) "
            f"have inline bodies in brain.py (expected: one-line delegate shims only)"
        )
        for v in violations[:25]:
            print(f"  {v}")
        if len(violations) > 25:
            print(f"  ... and {len(violations) - 25} more")
        return 1

    print(
        f"[brain-no-domain-method] OK: {shim_count} domain method(s) are all "
        f"one-line delegate shims; no inline bodies left in BrainService"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
