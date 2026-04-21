#!/usr/bin/env python3
"""
check_blockchain_async.py — preflight 段 7b

强约束（设计基线 §十四 D4 下半 + D5）：
    区块链锚定通过**可插拔 adapter 异步执行**——主业务路径中禁止直接 await
    blockchain adapter；外链 down 不应阻塞业务流（异步 + 告警 + 重试）。

扫描黑名单模式：
    1. 主业务路径（zw_brain/skills/、zw_brain/orchestrator/、zw_brain/agents/）
       中的 .py 文件
    2. 出现 `await blockchain` / `await chain.anchor` / `await *.adapter.anchor`
       等同步等待区块链 adapter 的语句 → fail

白名单（这些路径允许直接 await 区块链 adapter）：
    - zw_brain/skills/blockchain_adapter/   ← adapter 实现自身
    - zw_brain/shared/queue/                ← 异步队列内部
    - zw_brain/background_tasks/            ← 异步任务执行体
    - tests/                                ← 测试可同步驱动
    - test_*.py / *_test.py

Phase 0 早期 zw_brain/ 不存在时 skip + exit 0。

接入：scripts/preflight.sh 段 7b
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# 模式：函数链中含这些 token 即视为「区块链锚定调用」
BLOCKCHAIN_TOKENS = ("blockchain", "chain_anchor", "anchor_to_chain", ".anchor(", "blockchain_adapter")

# 主业务路径前缀（命中即扫描）
BUSINESS_PATH_PREFIXES = (
    "zw_brain/skills/",
    "zw_brain/orchestrator/",
    "zw_brain/agents/",
    "zw_brain/entry/",  # API 入口
)

# 白名单路径（异步执行体内部允许同步 await）
WHITELIST_PATH_PREFIXES = (
    "zw_brain/skills/blockchain_adapter/",
    "zw_brain/shared/queue/",
    "zw_brain/background_tasks/",
    "tests/",
)


def is_blockchain_call(node: ast.AST) -> tuple[bool, str]:
    """识别区块链 adapter 调用，返回 (是否命中, 调用名描述)。"""
    if not isinstance(node, ast.Call):
        return False, ""
    func = node.func
    chain: list[str] = []
    cur: ast.AST | None = func
    while isinstance(cur, ast.Attribute):
        chain.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        chain.append(cur.id)
    name = ".".join(reversed(chain)).lower()
    for token in BLOCKCHAIN_TOKENS:
        if token.strip("(").lower() in name:
            return True, name
    return False, ""


def scan_file(path: Path) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return violations
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        hit, name = is_blockchain_call(node.value)
        if hit:
            violations.append((node.lineno, name))
    return violations


def is_in_business_path(rel: Path) -> bool:
    s = str(rel).replace("\\", "/")
    if any(s.startswith(w) for w in WHITELIST_PATH_PREFIXES):
        return False
    return any(s.startswith(p) for p in BUSINESS_PATH_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "zw_brain"
    if not src.exists():
        print("[blockchain-async] skip: zw_brain/ not yet created (Phase 0 early)")
        print("  (this check becomes enforcing once Phase 1 introduces blockchain adapter call sites)")
        return 0

    total_files = 0
    total_violations = 0

    for path in src.rglob("*.py"):
        rel = path.relative_to(repo_root)
        if not is_in_business_path(rel):
            continue
        total_files += 1
        violations = scan_file(path)
        if violations:
            total_violations += len(violations)
            print(f"\n  ✗ {rel}")
            for lineno, name in violations:
                print(f"      L{lineno}  await {name}(...)  ← must dispatch to background task")

    print()
    if total_violations == 0:
        print(f"[blockchain-async] OK: scanned {total_files} business-path files, no sync await on blockchain adapter")
        return 0
    print(f"[blockchain-async] FAIL: {total_violations} synchronous blockchain await(s) in business path")
    print("  policy (D4/D5): blockchain anchoring MUST be async (queue / background task)")
    print("  fix: replace `await blockchain.anchor(...)` with `await queue.enqueue('blockchain.anchor', ...)`")
    return 1


if __name__ == "__main__":
    sys.exit(main())
