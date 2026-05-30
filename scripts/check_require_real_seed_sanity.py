#!/usr/bin/env python3
"""check_require_real_seed_sanity.py — preflight 段 57（D44 硬化）

D44 (2026-05-30) 决策：真数据 baseline 脆测试批量修。其中 **A 类设计错误**是
``require_real_seed({"capability_call": 744})`` —— 把**运行时累积遥测量**当 seed 门槛：
``capability_call`` 由 pipeline 每次 invoke 经 ``record_capability_call`` 落库，**不来自
legacy import**（fresh import=0、本机 clean=个位数）。``>=744`` 把"某次本机累积后的量"
当 seed 门槛 → CI 无 DB skip、本地 clean 也 skip、**整 module 永久不跑**，且数周无任何
机械守卫抓到（宪法 §5：靠自觉反复出现必须硬化）。

本守卫：AST 扫 ``tests/`` 下所有 ``require_real_seed(...)`` 调用，禁止 gate
**运行时累积表**（DENYLIST）。需要运行时数据的测试必须由 fixture **自产**
（genuine ``invoke_skill`` 经真实 pipeline 落库，见 D44 的 ``_runtime_capability_calls``），
不得靠 seed 门槛。

判定模型：``require_real_seed`` 的第一参数（dict ``{table: min}`` / tuple
``(table, min)`` / ``(table, min, where)`` / 上述的可迭代）里，**表名以字符串字面量出现**。
收集该参数子树内全部字符串常量，与 DENYLIST 精确相等比对——where 子句 SQL 串
（如 ``"decision_mode='department'"``）不等于裸表名、天然不误伤（B 类阈值贴稳定态
难以机械化，留 prose，见 D44 "How to apply"）。

DENYLIST（运行时累积，禁当 seed 门槛）：
  - ``capability_call`` —— pipeline invoke 遥测
  - ``audit_event``     —— 审计总线运行时事件
  - ``anchor_outbox``   —— 区块链锚定 outbox 队列
  - ``audit_receipt``   —— 锚定回执

ALLOWLIST：空。D44 立场是**没有**合法的"gate 运行时表"场景。若未来确有，按
``(rel_path, table)`` 对加入并在 PR 说明理由（与 check_no_legacy_inference_env.py 同范式）。

退出码：
    0 = 无 require_real_seed gate 运行时累积表
    1 = 检出 gate 运行时累积表（A 类设计错误回潮）
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO / "tests"

# 运行时累积表：由 runtime 写入（pipeline 遥测 / 审计总线 / 锚定队列），legacy import 产出 0 行。
DENYLIST: frozenset[str] = frozenset(
    {
        "capability_call",
        "audit_event",
        "anchor_outbox",
        "audit_receipt",
    }
)

# 合法例外 (rel_path, table)。D44：无合法场景，故为空。
ALLOWLIST: frozenset[tuple[str, str]] = frozenset()


def _string_constants(node: ast.AST) -> list[str]:
    """收集 AST 子树内全部 str 常量值。"""
    out: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def _is_require_real_seed(func: ast.AST) -> bool:
    if isinstance(func, ast.Name):
        return func.id == "require_real_seed"
    if isinstance(func, ast.Attribute):
        return func.attr == "require_real_seed"
    return False


def main() -> int:
    hits: list[str] = []
    scanned = 0
    for path in sorted(TESTS_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        scanned += 1
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_require_real_seed(node.func):
                continue
            if not node.args:
                continue
            tables_arg = node.args[0]
            for table in _string_constants(tables_arg):
                if table in DENYLIST and (rel, table) not in ALLOWLIST:
                    hits.append(f"{rel}:{node.lineno}: require_real_seed gate 运行时累积表 {table!r}")

    if hits:
        print(
            f"[require-real-seed-sanity] FAIL: 检出 {len(hits)} 处 require_real_seed "
            "gate 运行时累积表（D44 A 类设计错误回潮）："
        )
        for h in hits:
            print(f"  {h}")
        print(
            "  运行时累积表（capability_call / audit_event / anchor_outbox / audit_receipt）"
            "由 pipeline/审计/锚定 runtime 写入，legacy import 产出 0 行 → 当 seed 门槛会让整"
            " module 永久 skip（CI 无 DB / 本地 clean 均不达阈）。"
        )
        print(
            "  修复：移出门槛，改 gate legacy-seeded 前置表；需要运行时数据的测试由 fixture"
            " 自产（genuine invoke_skill 经真实 pipeline 落库，参见 D44 _runtime_capability_calls）。"
        )
        return 1

    print(
        f"[require-real-seed-sanity] OK: scanned {scanned} test file(s); "
        f"no require_real_seed gates a runtime-accumulated table（DENYLIST {len(DENYLIST)} 表）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
