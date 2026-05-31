#!/usr/bin/env python3
"""check_trace_triangle.py — preflight 段 38

飞轮 §四 连接守卫（.feature ←→ tests 双向一致）。

  .testing/*.feature  ←→  tests/*

历史：原为「.feature ←→ .twin/plan.yaml ←→ tests」三角。`.twin/`（supervisor 执行
计划）已退役（D46.e）——执行计划不再是真相载体，故第三角（# Twin-F → plan.yaml spec_ref
双向）随之消失，守卫收敛为 SPEC↔test 双边。

强约束：
  1. Owner 字段是 6 个合法 worker 之一（e1-e6，归属标签；不再要求 .twin 目录存在）
  2. Pytest 字段：引用的 tests/*.py（或 zw-brain-web e2e .spec.ts）文件存在（或 pending）

Exit：0 = 全一致；1 = 任一断裂

Usage:
    ./scripts/check_trace_triangle.py [--verbose]

接入：scripts/preflight.sh 段 38
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTING_DIR = REPO / ".testing"

VALID_OWNERS = {"e1", "e2", "e3", "e4", "e5", "e6"}

OWNER_RE = re.compile(r"^# Owner:\s*(\S+)")
PYTEST_RE = re.compile(r"^# Pytest:\s*(.+)")
# 测试路径：pytest 模块（tests/**.py）+ Playwright e2e（tests/**.spec.ts 仓根 e2e 套，
# 或历史 zw-brain-web/tests 前缀）。e2e spec 纳入是测量轴 test-runner 无关化的一部分
# （webui 类只有 e2e，pytest 轴看不到，故 .feature 的 # Pytest 用 spec 路径）。
PYTEST_PATH_RE = re.compile(
    r"(tests/[\w/\-\.]+\.py|tests/[\w/\-\.]+\.spec\.ts|zw-brain-web/tests/[\w/\-\.]+\.(?:ts|spec\.ts))"
)


def _parse_feature_header(feature_path: Path) -> tuple[str | None, str | None, str | None]:
    """读 feature header 前 30 行，返回 (owner, pytest, None)。

    第三元保留为 None 以兼容历史调用方（feature_status_lib 解包 3 元组）——
    `# Twin-F` 已随 .twin 退役不再解析（D46.e）。
    """
    owner = pytest_val = None
    try:
        with feature_path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i > 30:
                    break
                if m := OWNER_RE.match(line):
                    owner = m.group(1).strip()
                elif m := PYTEST_RE.match(line):
                    pytest_val = m.group(1).strip()
    except OSError:
        return None, None, None
    return owner, pytest_val, None


def _check_feature(feature_path: Path) -> list[str]:
    """检查一个 .feature 的连接字段；返回违规字符串列表"""
    violations: list[str] = []
    rel = feature_path.relative_to(REPO).as_posix()
    owner, pytest_val, _ = _parse_feature_header(feature_path)

    if owner is None:
        violations.append(f"{rel}: missing # Owner: header")
    elif owner not in VALID_OWNERS:
        violations.append(f"{rel}: Owner='{owner}' not in {sorted(VALID_OWNERS)}")

    if pytest_val is None:
        violations.append(f"{rel}: missing # Pytest: header")
    elif pytest_val != "pending":
        for match in PYTEST_PATH_RE.finditer(pytest_val):
            path_str = match.group(1)
            if not (REPO / path_str).is_file():
                violations.append(f"{rel}: Pytest references missing file '{path_str}'")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="飞轮连接守卫（.feature ←→ tests）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not TESTING_DIR.is_dir():
        print("[trace-triangle] skip: .testing/ not present")
        return 0

    all_violations: list[str] = []
    scanned = 0
    for feature_path in sorted(TESTING_DIR.rglob("*.feature")):
        scanned += 1
        all_violations.extend(_check_feature(feature_path))

    if all_violations:
        print(f"[trace-triangle] FAIL: scanned {scanned} .feature(s), {len(all_violations)} violation(s):")
        for v in all_violations:
            print(f"  {v}")
        print()
        print("[trace-triangle] hint: # Owner（e1-e6）+ # Pytest（文件存在或 pending）必须齐备。")
        print("[trace-triangle] 飞轮设计: docs/approved/zw-brain-flywheel.md §四（.twin 退役后收敛为 SPEC↔test 双边，D46.e）")
        return 1

    print(f"[trace-triangle] OK: scanned {scanned} .feature(s); SPEC↔test links valid")
    if args.verbose:
        print("  (.twin retired — Twin-F 边已移除，D46.e)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
