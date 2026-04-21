#!/usr/bin/env python3
"""
check_audit_must_block.py — preflight 段 7a

强约束（设计基线 §十四 D4 上半）：
    审计总线**强制同步落库**——所有写操作必须先 emit audit_event 同步落库，
    落库失败必须熔断（raise / abort），禁止吞错继续。

扫描黑名单模式（AST 级别）：
    1. `try: ... audit_*.emit(...) ... except ... pass`         ← 吞错
    2. `try: ... audit_*.emit(...) ... except ... log.warning`  ← 弱错处理
    3. `try: ... audit_*.emit(...) ... except ... return ...`   ← 跳过审计

白名单：测试文件（test_*.py / *_test.py）允许 mock audit 失败场景。

Phase 0 早期 zw_brain/ 不存在时 skip + exit 0。

接入：scripts/preflight.sh 段 7a
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

AUDIT_FUNC_HINTS = ("audit", "audit_bus", "audit_event")
SWALLOW_NAMES = {"pass", "continue", "log.warning", "logger.warning", "print"}


def is_audit_call(node: ast.AST) -> bool:
    """识别 audit.* / audit_bus.* / *.audit_event(...) 等调用。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        # e.g. audit.emit / audit_bus.write
        chain = []
        cur = func
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            chain.append(cur.id)
        text = ".".join(reversed(chain)).lower()
        return any(hint in text for hint in AUDIT_FUNC_HINTS)
    if isinstance(func, ast.Name):
        return any(hint in func.id.lower() for hint in AUDIT_FUNC_HINTS)
    return False


def has_audit_call_in(body: list[ast.stmt]) -> bool:
    for stmt in body:
        for node in ast.walk(stmt):
            if is_audit_call(node):
                return True
    return False


def is_swallow_handler(handler: ast.ExceptHandler) -> tuple[bool, str]:
    """检查 except 子句是否吞错。返回 (是否吞错, 原因描述)。"""
    if not handler.body:
        return True, "empty body"
    last = handler.body[-1]

    # except: ... pass / continue
    if isinstance(last, ast.Pass):
        return True, "ends with `pass`"
    if isinstance(last, ast.Continue):
        return True, "ends with `continue`"

    # except: return / return None / return False
    if isinstance(last, ast.Return):
        return True, "ends with `return` (audit failure swallowed)"

    # except: log.warning(...) / print(...) — 仅日志，不阻塞
    if isinstance(last, ast.Expr) and isinstance(last.value, ast.Call):
        call = last.value
        chain: list[str] = []
        cur: ast.AST | None = call.func
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            chain.append(cur.id)
        name = ".".join(reversed(chain))
        # 检查是否仅日志/打印且无 raise
        body_has_raise = any(isinstance(s, ast.Raise) for s in handler.body)
        if not body_has_raise and name in SWALLOW_NAMES:
            return True, f"only `{name}` without raise"

    return False, ""


def scan_file(path: Path) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not has_audit_call_in(node.body):
            continue
        for handler in node.handlers:
            swallow, reason = is_swallow_handler(handler)
            if swallow:
                violations.append((handler.lineno, reason))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "zw_brain"
    if not src.exists():
        print("[audit-must-block] skip: zw_brain/ not yet created (Phase 0 early)")
        print("  (this check becomes enforcing once Phase 1 introduces audit emit sites)")
        return 0

    total_files = 0
    total_violations = 0

    for path in src.rglob("*.py"):
        # 测试文件允许 mock audit 失败
        rel = path.relative_to(repo_root)
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in str(rel):
            continue
        total_files += 1
        violations = scan_file(path)
        if violations:
            total_violations += len(violations)
            print(f"\n  ✗ {rel}")
            for lineno, reason in violations:
                print(f"      L{lineno}  audit failure swallowed: {reason}")

    print()
    if total_violations == 0:
        print(f"[audit-must-block] OK: scanned {total_files} files, no audit-swallow handlers detected")
        return 0
    print(f"[audit-must-block] FAIL: {total_violations} swallow handler(s) detected")
    print("  policy (D4): audit emit failure MUST raise/abort, not be silently passed")
    print("  fix: re-raise the exception or use circuit-breaker pattern")
    return 1


if __name__ == "__main__":
    sys.exit(main())
