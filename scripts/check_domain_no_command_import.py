#!/usr/bin/env python3
"""Preflight segment 49 — lower layers must not runtime-import upper layers.

Architecture baseline §架构约束 (CLAUDE.md root) requires the 4-layer order:
``entry → command → domain → shared``. Reverse imports at runtime break this
layer rule and entangle a lower layer with editorial / orchestration concerns
that belong one direction up. This guard scans both ``zw_brain/domain/`` and
``zw_brain/shared/`` and forbids runtime imports of ``zw_brain.command`` and
``zw_brain.entry`` (TYPE_CHECKING-only imports are allowed).

shared/ scan added 2026-06 after ``shared/agent_runtime/{service,capability_provider}.py``
were caught eager-importing ``zw_brain.command``; the fix used IoC (a provider
registered from the upper layer) + a TYPE_CHECKING-only annotation, with **no
whitelist**. (That IoC wiring was later removed in D68 once the http-form facade
stopped needing an in-process brain — shared/agent_runtime now imports no command.)

Action D (#142) introduced ``zw_brain/domain/errors.py`` to retire
``from zw_brain.command.brain import NotFoundError`` reverse imports inside
``zw_brain/domain/services/*``. Action D R-021 fix moved serializers into
``zw_brain/domain/serializers/`` so ``from zw_brain.command.serializers``
went away.

Action H (#149) introduced one regression: ``catalog_service.py`` lazy-imported
``zw_brain.command.demo_state_sync`` inside ``resolve_resource_for_application``
to call its 4-line ``resource_by_id`` lookup. R-001 (PR #149 local-acceptance)
inlined that lookup; this segment locks the invariant.

What this guards against
------------------------
- Any runtime ``from zw_brain.command...`` / ``import zw_brain.command...``
  inside ``zw_brain/domain/`` (services, serializers, repositories, errors,
  or any future submodule).
- TYPE_CHECKING-only imports are allowed (Python's typing-only escape hatch
  doesn't trigger at runtime, so it's not a layer violation in practice).

How AST detection works
-----------------------
We walk each file's AST and classify each Import / ImportFrom node by whether
its enclosing context is the ``if TYPE_CHECKING:`` block. Anything else is
runtime. This is more accurate than text grep (which gets confused by the
fact that ``TYPE_CHECKING:`` is on the previous line, not the import line).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIR = REPO_ROOT / "zw_brain" / "domain"
SHARED_DIR = REPO_ROOT / "zw_brain" / "shared"
SCAN_DIRS = (DOMAIN_DIR, SHARED_DIR)
# Upper layers a lower layer must not runtime-import (entry → command → domain → shared).
FORBIDDEN_PREFIXES = ("zw_brain.command", "zw_brain.entry")


def _is_in_type_checking(node: ast.AST, type_checking_blocks: list[tuple[int, int]]) -> bool:
    """Return True if ``node`` falls inside any ``if TYPE_CHECKING:`` body."""
    return any(start <= node.lineno <= end for start, end in type_checking_blocks)


def _find_type_checking_blocks(tree: ast.Module) -> list[tuple[int, int]]:
    """Return list of (start_line, end_line) ranges for ``if TYPE_CHECKING:`` bodies."""
    blocks: list[tuple[int, int]] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.If):
            is_tc_check = (
                isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
            )
            if is_tc_check and node.body:
                start = node.body[0].lineno
                end = node.body[-1].end_lineno or node.body[-1].lineno
                blocks.append((start, end))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return blocks


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, statement) for runtime ``zw_brain.command...`` imports."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    tc_blocks = _find_type_checking_blocks(tree)
    violations: list[tuple[int, str]] = []

    def _forbidden(mod: str) -> bool:
        return any(mod == p or mod.startswith(p + ".") for p in FORBIDDEN_PREFIXES)

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if _forbidden(mod) and not _is_in_type_checking(node, tc_blocks):
                names = ", ".join(a.name for a in node.names)
                violations.append((node.lineno, f"from {mod} import {names}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden(alias.name) and not _is_in_type_checking(node, tc_blocks):
                    violations.append((node.lineno, f"import {alias.name}"))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return violations


def main() -> int:
    present = [d for d in SCAN_DIRS if d.exists()]
    if not present:
        print("[layer-no-reverse-import] SKIP: no zw_brain/{domain,shared}/ present (fresh checkout)")
        return 0

    all_violations: list[tuple[Path, int, str]] = []
    for base_dir in present:
        for path in sorted(base_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for lineno, stmt in _scan_file(path):
                all_violations.append((path.relative_to(REPO_ROOT), lineno, stmt))

    if not all_violations:
        print(
            "[layer-no-reverse-import] OK: zw_brain/domain/ + zw_brain/shared/ have no "
            "runtime imports from zw_brain.command / zw_brain.entry (TYPE_CHECKING-only allowed)."
        )
        return 0

    print(
        f"[layer-no-reverse-import] FAIL: {len(all_violations)} runtime "
        f"reverse-layer import(s) found (domain/shared → command/entry):"
    )
    for path, lineno, stmt in all_violations:
        print(f"  {path}:{lineno}: {stmt}")
    print()
    print(
        "  hint: domain/shared must not depend on command/entry at runtime "
        "(architecture baseline §架构约束: entry → command → domain → shared)."
    )
    print(
        "  fix: inline the helper, move pure logic down a layer, or invert the "
        "dependency (let the upper layer register a provider via IoC). "
        "TYPE_CHECKING-only imports are fine."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
