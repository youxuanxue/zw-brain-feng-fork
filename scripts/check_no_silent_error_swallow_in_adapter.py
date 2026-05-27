#!/usr/bin/env python3
"""check_no_silent_error_swallow_in_adapter.py — preflight 段 41

CLAUDE.md §2 全局宪法禁止 silent error swallow。legacy adapter mappers 内
`stats.add_issue(...) + continue` 模式表示「业务级跳过这一行」，必须配套写入
`adapter_run_record.error_summary`，否则失败原因从 receipt 上消失。

The single bridge between `stats.issues` and `adapter_run_record.error_summary`
is `zw_brain/adapters/legacy/_common.py::finish_run`. This check enforces:

1. Every mapper module that uses `add_issue+continue` MUST close its run via
   `finish_run` (no bespoke AdapterRunRecord upsert that could forget
   error_summary).
2. `_common.py::finish_run` MUST populate `error_summary` in the payload
   passed to `adapter_repo.upsert_run_record(...)` (i.e. the bridge itself
   doesn't regress).

Both invariants together guarantee that whenever `add_issue+continue` lands
in a mapper, the receipt has a non-empty error_summary. (`finish_run` was
audited to set error_summary to a non-None text whenever any issue exists.)

Exit 0 = invariants hold; exit 1 = at least one violation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPPERS_DIR = REPO / "zw_brain" / "adapters" / "legacy" / "mappers"
COMMON_PATH = REPO / "zw_brain" / "adapters" / "legacy" / "_common.py"


def _has_add_issue_continue(tree: ast.AST) -> list[int]:
    """Return line numbers of every `add_issue(...)` immediately followed by `continue`."""
    hits: list[int] = []
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for i in range(len(body) - 1):
            stmt = body[i]
            nxt = body[i + 1]
            if not isinstance(nxt, ast.Continue):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if isinstance(call.func, ast.Attribute) and call.func.attr == "add_issue":
                    hits.append(stmt.lineno)
    return hits


def _calls_finish_run(tree: ast.AST) -> bool:
    """Module's source explicitly references finish_run as a function call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "finish_run":
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == "finish_run":
                return True
    return False


def _finish_run_writes_error_summary(common_source: str) -> bool:
    """`_common.finish_run` payload must include the `error_summary` key.

    AST-walk: find function `finish_run`, look inside for a Dict literal
    that has a key string `"error_summary"`.
    """
    tree = ast.parse(common_source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "finish_run":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Dict):
                continue
            for k in sub.keys:
                if isinstance(k, ast.Constant) and k.value == "error_summary":
                    return True
    return False


def main() -> int:
    if not MAPPERS_DIR.exists():
        print(f"[skip] {MAPPERS_DIR} not present", file=sys.stderr)
        return 0
    if not COMMON_PATH.exists():
        print(f"[FAIL] {COMMON_PATH} missing — finish_run bridge gone", file=sys.stderr)
        return 1

    violations: list[str] = []

    # Invariant 2: finish_run still writes error_summary
    common_source = COMMON_PATH.read_text(encoding="utf-8")
    if not _finish_run_writes_error_summary(common_source):
        violations.append(
            f"{COMMON_PATH.relative_to(REPO).as_posix()}: finish_run payload no longer "
            "contains `error_summary` key — silent swallow bridge broken"
        )

    # Invariant 1: mappers with add_issue+continue must call finish_run
    for path in sorted(MAPPERS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (UnicodeDecodeError, SyntaxError) as exc:
            violations.append(f"{rel}: parse error — {exc}")
            continue
        hits = _has_add_issue_continue(tree)
        if not hits:
            continue
        if not _calls_finish_run(tree):
            sample_line = hits[0]
            violations.append(
                f"{rel}:{sample_line}: has `add_issue(...) + continue` pattern but does not "
                "call `finish_run(...)` — adapter_run_record.error_summary will be silently None. "
                "Route the import through finish_run from zw_brain.adapters.legacy._common."
            )

    if violations:
        print("Silent-swallow guard FAILED (CLAUDE.md §2 全局宪法):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(
        "[OK] silent-swallow guard: mappers with add_issue+continue route via finish_run; "
        "finish_run writes error_summary",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
