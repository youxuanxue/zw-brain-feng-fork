#!/usr/bin/env python3
"""check_brain_no_request_state_singleton.py — preflight 段 35

Per-request state must not regress back onto the BrainService process-global
singleton. `role` is the per-request value that previously lived on
`_ui_state["role"]` and bled across concurrent requests; it now lives in a
ContextVar (`zw_brain/shared/ui_request_context.py`), surfaced via _UIStateProxy.

Locks two invariants in `zw_brain/command/brain.py`:
  1. every assignment to `self._ui_state` seeds a backing dict that does NOT
     contain a `role` key (nor any other declared per-request key);
  2. brain.py imports the ContextVar accessors from ui_request_context.

退出码：0 = PASS；1 = 违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRAIN_PY = REPO / "zw_brain" / "command" / "brain.py"

# keys that are per-request and must never be seeded on the singleton backing dict
FORBIDDEN_SINGLETON_KEYS = ("role",)


def _dict_keys(node: ast.AST) -> list[str]:
    """Return string keys of a Dict literal, unwrapping a `_UIStateProxy({...})` call."""
    if isinstance(node, ast.Call) and node.args:
        node = node.args[0]
    if not isinstance(node, ast.Dict):
        return []
    return [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def main() -> int:
    source = BRAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BRAIN_PY))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets_ui_state = any(
            isinstance(t, ast.Attribute) and t.attr == "_ui_state" for t in node.targets
        )
        if not targets_ui_state:
            continue
        keys = _dict_keys(node.value)
        for bad in FORBIDDEN_SINGLETON_KEYS:
            if bad in keys:
                violations.append(
                    f"brain.py:{node.lineno}: `_ui_state` backing dict seeds per-request key "
                    f"{bad!r} — per-request state belongs in ui_request_context ContextVar, "
                    f"not the BrainService singleton."
                )

    imports_context = any(
        isinstance(node, ast.ImportFrom) and (node.module or "").endswith("ui_request_context")
        for node in ast.walk(tree)
    )
    if not imports_context:
        violations.append(
            "brain.py: missing import from zw_brain.shared.ui_request_context "
            "(get_current_role / set_current_role) — per-request role must route through the ContextVar."
        )

    if violations:
        print("[brain-no-request-state-singleton] FAIL:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("[brain-no-request-state-singleton] OK: _ui_state singleton seeds no per-request key; ContextVar wired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
