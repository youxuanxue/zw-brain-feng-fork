#!/usr/bin/env python3
"""Preflight segment 42 — verify SkillPipeline middleware order is the documented one.

Action B introduced an ordered middleware chain for write/read paths
(``zw_brain/command/pipeline.py``). The order matters for correctness:

  PolicyMiddleware       — must run before anything else (enforce gates).
  IdentityMiddleware     — must run before AuditEmit (audit needs audit_id + actor).
  AuditEmitMiddleware    — must wrap both successful and failed handler exec.
  CapabilityCallMiddleware — records both success + failure to DB.
  PersistMiddleware      — snapshot persist (write path only).
  AnchorMiddleware       — last (blockchain anchor uses payload | result).

Any reorder silently breaks audit semantics — e.g. if Anchor runs before
AuditEmit, the blockchain anchor hash is computed on raw payload not on
the post-mutation result. This script statically verifies the
``build_default_pipeline`` function constructs middlewares in the order
declared by ``MIDDLEWARE_ORDER``.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FILE = REPO_ROOT / "zw_brain" / "command" / "pipeline.py"


def main() -> int:
    if not PIPELINE_FILE.exists():
        print(f"[pipeline-middleware-order] skip: {PIPELINE_FILE} not present")
        return 0

    src = PIPELINE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Find ``MIDDLEWARE_ORDER`` module-level assignment (covers both bare and
    # annotated assignment forms).
    declared_order: list[str] | None = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "MIDDLEWARE_ORDER":
                    if isinstance(node.value, ast.Tuple):
                        declared_order = [
                            elt.value for elt in node.value.elts
                            if isinstance(elt, ast.Constant)
                        ]
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "MIDDLEWARE_ORDER":
                if isinstance(node.value, ast.Tuple):
                    declared_order = [
                        elt.value for elt in node.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
    if declared_order is None:
        print("[pipeline-middleware-order] FAIL: MIDDLEWARE_ORDER constant not found in pipeline.py")
        return 1

    # Find ``build_default_pipeline`` function and extract the middleware classes
    # passed to ``SkillPipeline(middlewares=(...))``.
    constructed_order: list[str] | None = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_default_pipeline":
            for n in ast.walk(node):
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Call):
                    call = n.value
                    # Find middlewares keyword argument
                    for kw in call.keywords:
                        if kw.arg == "middlewares" and isinstance(kw.value, ast.Tuple):
                            constructed_order = []
                            for elt in kw.value.elts:
                                # Each element is `MiddlewareClass(brain)` — extract class name
                                if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name):
                                    constructed_order.append(elt.func.id)
    if constructed_order is None:
        print("[pipeline-middleware-order] FAIL: build_default_pipeline does not return a SkillPipeline call")
        return 1

    if declared_order != constructed_order:
        print("[pipeline-middleware-order] FAIL: MIDDLEWARE_ORDER does not match build_default_pipeline")
        print(f"  declared:    {declared_order}")
        print(f"  constructed: {constructed_order}")
        print()
        print("  hint: reorder either MIDDLEWARE_ORDER or build_default_pipeline middleware list")
        print("        so they match — silent reordering breaks audit pipeline correctness.")
        return 1

    print(f"[pipeline-middleware-order] OK: {len(declared_order)} middlewares in declared order ({', '.join(declared_order)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
