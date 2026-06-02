#!/usr/bin/env python3
"""check_credential_grant_invariant.py — preflight 段 66

凭据**诚实**不变量机械化守卫（C-1 凭据诚实化后重定向）。

背景：legacy 迁移把 `data_apply_authrization.apply_status==9` 映射为交付态
`granted`（zw_brain/adapters/legacy/mappers/exchange.py
`_map_data_apply_authrization`）。真实授权表**无 per-grant 凭据列**，真凭据在网关域
`dsp_service.api_service_app.SECRET`、与 apply_id 无绑定供数（见 docs/preflight-debt.md）。
旧实现曾在 granted 分支 `derive_demo_credential` **捏造 AK-DEMO** 糊住「granted⟹凭据」——
已停止（C-1）。真实历史 granted 单**本就没有凭据**，应诚实显 not_issued。

新不变量（写边界静态确认，CI 友好不需 seed DB）：`_map_data_apply_authrization`
的 granted 分支必须

1. 存在对字符串 `"granted"` 的比较（granted 分支判定）；
2. **显式处理凭据态**：对下标 `["credential"]` 与 `["credential_status"]` 都有赋值
   （不静默——要么真签发、要么诚实标 not_issued）；
3. **不得回潮捏造**：granted 分支不得再调 `derive_demo_credential`
   （防 AK-DEMO 假凭据重新糊回 granted）。

任一违反 → FAIL（有人删掉诚实标记、或重新引入捏造即被拦下）。

说明：新建在产申请 approve 的自动签发（`_auto_issue_credential_on_approval` →
`credential.issue`）是**平台自身**签发、与本迁移边界无关，不在本守卫约束内。

Exit 0 = 诚实不变量由构造保持；Exit 1 = 至少一处违例。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXCHANGE_PATH = REPO / "zw_brain" / "adapters" / "legacy" / "mappers" / "exchange.py"
FUNC_NAME = "_map_data_apply_authrization"
FACTORY_NAME = "derive_demo_credential"


def _find_func(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _compares_to_granted(func: ast.AST) -> bool:
    """A Compare whose either side is the string constant "granted"."""
    for node in ast.walk(func):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for op in operands:
                if isinstance(op, ast.Constant) and op.value == "granted":
                    return True
    return False


def _assigns_subscript_key(func: ast.AST, key: str) -> bool:
    """An assignment target `something[<key>] = ...`."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.slice, ast.Constant)
                and tgt.slice.value == key
            ):
                return True
    return False


def _calls_factory(func: ast.AST, name: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == name:
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == name:
                return True
    return False


def main() -> int:
    if not EXCHANGE_PATH.exists():
        print(f"[FAIL] {EXCHANGE_PATH} missing — exchange mapper gone", file=sys.stderr)
        return 1
    try:
        tree = ast.parse(EXCHANGE_PATH.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        print(f"[FAIL] cannot parse {EXCHANGE_PATH}: {exc}", file=sys.stderr)
        return 1

    func = _find_func(tree, FUNC_NAME)
    rel = EXCHANGE_PATH.relative_to(REPO).as_posix()
    if func is None:
        print(
            f"[FAIL] {rel}: function `{FUNC_NAME}` not found — granted-delivery "
            "write boundary moved; re-point this guard.",
            file=sys.stderr,
        )
        return 1

    violations: list[str] = []
    if not _compares_to_granted(func):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` no longer branches on delivery_state "
            '== "granted" — cannot locate the granted branch that must handle credential state.'
        )
    if not _assigns_subscript_key(func, "credential"):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` no longer assigns `[\"credential\"]` — "
            "granted branch must explicitly set credential (None for honest not_issued), not leave it silent."
        )
    if not _assigns_subscript_key(func, "credential_status"):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` no longer assigns `[\"credential_status\"]` — "
            "granted branch must explicitly mark credential state (e.g. \"not_issued\"); "
            "honest surfacing, not a silent absent key."
        )
    if _calls_factory(func, FACTORY_NAME):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` calls `{FACTORY_NAME}` — credential "
            "fabrication regressed. Real legacy granted carries NO credential (gateway-domain "
            "secret, no apply_id binding); do not paper over with an AK-DEMO credential."
        )

    if violations:
        print("credential honesty invariant guard FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(
        f"[OK] credential honesty invariant: `{FUNC_NAME}` granted branch marks credential "
        "state explicitly (not_issued) and does not fabricate (no derive_demo_credential).",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
