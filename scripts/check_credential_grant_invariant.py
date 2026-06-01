#!/usr/bin/env python3
"""check_credential_grant_invariant.py — preflight 段 66

凭据签发不变量（granted ⟹ credential）机械化守卫。

背景：legacy 迁移把 `data_apply_authrization.apply_status==9` 映射为交付态
`granted`（zw_brain/adapters/legacy/mappers/exchange.py
`_map_data_apply_authrization`）。真实 `app_key` 在边界按 PII 剥除
（APPLY_DROP_FIELDS），因此若 granted 分支不主动物化一份 demo 凭据，
迁移产出的 granted 交付就会 `accessGrantSnapshot` 存在却 `credential` 为空，
导致 `credential.query` / P4 凭据样例渲染失败（曾实证 422 / not_issued）。

本守卫在**写边界**静态确认该不变量由构造保持，CI 友好（不需 seed DB）：
`_map_data_apply_authrization` 的 granted 分支必须

1. 存在对字符串 `"granted"` 的比较（granted 分支判定）；
2. 存在对下标 `["credential"]` 的赋值（写入凭据）；
3. 该赋值取自单一事实源工厂 `derive_demo_credential`（与审批流同形，
   避免另起一套凭据 schema 漂移）。

任一缺失 → FAIL（有人删掉/改写 granted 凭据物化即被拦下）。

说明：运行时授权路径 `BrainService.grant_delivery_access` 故意**不**即时签发
凭据（凭据走独立 `credential.issue` 按需签发，旧 secret reissue 失效语义），
故本守卫只约束**迁移/seed 写边界**的数据一致性，不约束运行时 grant。

Exit 0 = 不变量由构造保持；Exit 1 = 至少一处违例。
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


def _assigns_credential_subscript(func: ast.AST) -> bool:
    """An assignment target `something["credential"] = ...`."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.slice, ast.Constant)
                and tgt.slice.value == "credential"
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
            '== "granted" — cannot locate the granted branch that must issue a credential.'
        )
    if not _assigns_credential_subscript(func):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` no longer assigns `[\"credential\"]` — "
            "granted deliveries would carry accessGrantSnapshot without a credential "
            "(credential.query → 422/not_issued; P4 凭据样例不可渲染)."
        )
    if not _calls_factory(func, FACTORY_NAME):
        violations.append(
            f"{rel}:{func.lineno}: `{FUNC_NAME}` no longer calls `{FACTORY_NAME}` — "
            "seed credential must come from the single-source demo-credential factory "
            "(zw_brain/domain/services/request_service.py), not a divergent shape."
        )

    if violations:
        print("credential⟺grant invariant guard FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(
        f"[OK] credential-grant invariant: `{FUNC_NAME}` granted branch issues a "
        f"credential via {FACTORY_NAME} (granted ⟹ credential by construction)",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
