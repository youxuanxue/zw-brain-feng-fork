#!/usr/bin/env python3
"""Preflight segment 49 — domain layer must not runtime-import command layer.

Architecture baseline §架构约束 (CLAUDE.md root) requires the 4-layer order:
``entry → command → domain → shared``. Reverse imports (domain → command) at
runtime break this layer rule and entangle the domain layer with editorial /
orchestration concerns that should be one direction up.

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

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("zw_brain.command") and not _is_in_type_checking(node, tc_blocks):
                names = ", ".join(a.name for a in node.names)
                violations.append((node.lineno, f"from {mod} import {names}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("zw_brain.command") and not _is_in_type_checking(node, tc_blocks):
                    violations.append((node.lineno, f"import {alias.name}"))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return violations


def main() -> int:
    if not DOMAIN_DIR.exists():
        print(f"[domain-no-command-import] SKIP: {DOMAIN_DIR} not present (fresh checkout)")
        return 0

    all_violations: list[tuple[Path, int, str]] = []
    for path in sorted(DOMAIN_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for lineno, stmt in _scan_file(path):
            all_violations.append((path.relative_to(REPO_ROOT), lineno, stmt))

    if not all_violations:
        print(
            "[domain-no-command-import] OK: zw_brain/domain/ has no runtime "
            "imports from zw_brain.command (TYPE_CHECKING-only imports allowed)."
        )
        return 0

    print(
        f"[domain-no-command-import] FAIL: {len(all_violations)} runtime "
        f"domain → command import(s) found:"
    )
    for path, lineno, stmt in all_violations:
        print(f"  {path}:{lineno}: {stmt}")
    print()
    print(
        "  hint: domain layer must not depend on command layer at runtime "
        "(architecture baseline §架构约束: entry → command → domain → shared)."
    )
    print(
        "  fix: either inline the called helper into the domain method, or "
        "move the helper to zw_brain/domain/ (if it's pure domain logic),"
    )
    print(
        "  or restructure the call so command calls domain (not the reverse). "
        "TYPE_CHECKING-only imports are fine."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
