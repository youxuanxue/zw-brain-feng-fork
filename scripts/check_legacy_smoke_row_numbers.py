#!/usr/bin/env python3
"""preflight 段 39 — 旧 xlsx 行号引用守卫.

防止 .feature Trace 引用旧 xlsx 中不存在 / mapping doc 未登记的行号。

zw-brain 飞轮势能源之一是 `old/共享平台V5.0.2-冒烟.xlsx` 128 distinct 用例
（详见 `docs/approved/zw-brain-flywheel.md` §三.2）。每条 .feature Trace
都用 "旧 xlsx 行 N" 反向引用业务方过往验证过的用例。如果 N 写错或被删，
飞轮真值源 → spec 的连接就断了。

本脚本两向校验：
  1. 解析 .testing/cross-cutting/legacy-128-mapping.md 表头，提取所有行号集合
  2. 扫描 .testing/ 全部 .feature 的 Trace 行，提取 "旧 xlsx 行 N" 引用
  3. .feature 引用的 N 必须出现在 mapping doc（防止 dangling reference）

不校验：
  - mapping doc 内部行号是否单调递增（自承漂移，由"用例名锚点"软约束承接）
  - 行号是否与 xlsx 实际数据行对齐（需要 xlsx 真值，CI 无此文件）

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_legacy_smoke_row_numbers.py
    ./scripts/check_legacy_smoke_row_numbers.py --verbose

接入：scripts/preflight.sh 段 39
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPPING_DOC = REPO / ".testing" / "cross-cutting" / "legacy-128-mapping.md"
TESTING_DIR = REPO / ".testing"

# 匹配 mapping doc 表行：| <行号> | <用例名> | ...
# 行号可以是纯数字（"3"）或带后缀字母（"32a" / "38b"）或区间合并（"65 / 70 / 63 / 68 / 66 / 67 / 69 / 64"）
MAPPING_ROW_HEAD_RE = re.compile(r"^\|\s*([0-9a-z][0-9a-z\s/]*)\s*\|")

# .feature Trace 中 "旧 xlsx 行 N" 或 "旧 xlsx 行 [N..M]" 或 "旧 xlsx 行 [N,M,..]"
FEATURE_TRACE_ROW_RE = re.compile(r"旧 xlsx 行\s*\[?\s*([0-9a-z]+(?:\s*[-,.]+\s*[0-9a-z]+)*)\s*\]?")

# 单 token 行号（"3" / "32a" / "38b"）
SINGLE_ROW_RE = re.compile(r"^[0-9]+[a-z]?$")


def _parse_mapping_rows(doc_path: Path) -> set[str]:
    """从 mapping doc 提取所有 known 行号（含合并行如 '65 / 70 / 63'）"""
    rows: set[str] = set()
    if not doc_path.is_file():
        return rows
    for line in doc_path.read_text(encoding="utf-8").split("\n"):
        m = MAPPING_ROW_HEAD_RE.match(line)
        if not m:
            continue
        cell = m.group(1).strip()
        # 跳过表头分隔行（"---" / "ID" / "行"）
        if not cell or cell.startswith("-") or cell in {"行", "ID", "id"}:
            continue
        # 跨 case 合并行：65 / 70 / 63 / 68 / 66 / 67 / 69 / 64
        parts = re.split(r"\s*/\s*", cell)
        for p in parts:
            p = p.strip()
            if SINGLE_ROW_RE.match(p):
                rows.add(p)
                # 后缀行 "35a" / "38b" → 同时登记裸数字 "35" / "38" 作为 alias
                # （feature 用区间引用 [35..38] 时能命中）
                m_alias = re.match(r"^(\d+)[a-z]$", p)
                if m_alias:
                    rows.add(m_alias.group(1))
    return rows


def _expand_feature_row_token(token: str) -> list[str]:
    """把 '3' / '32a' / '1..12' / '13' 等展开为单 token 列表"""
    # 区间 N..M
    m = re.match(r"^(\d+)\s*\.\.\s*(\d+)$", token)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return [str(n) for n in range(lo, hi + 1)]
    # 短横线区间 N-M（少见但可能）
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", token)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return [str(n) for n in range(lo, hi + 1)]
    # 逗号列表 N,M
    if "," in token:
        return [p.strip() for p in token.split(",") if SINGLE_ROW_RE.match(p.strip())]
    # 单 token
    if SINGLE_ROW_RE.match(token):
        return [token]
    return []


def _scan_feature_refs(testing_dir: Path) -> dict[str, list[tuple[Path, int]]]:
    """扫所有 .feature Trace 引用的"旧 xlsx 行 N"；返回 {row_token: [(path, line_no), ...]}"""
    refs: dict[str, list[tuple[Path, int]]] = {}
    for fp in testing_dir.rglob("*.feature"):
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.split("\n"), 1):
            for m in FEATURE_TRACE_ROW_RE.finditer(line):
                raw = m.group(1)
                for token in _expand_feature_row_token(raw):
                    refs.setdefault(token, []).append((fp, line_no))
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description="旧 xlsx 行号引用守卫")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not MAPPING_DOC.is_file():
        print("[legacy-smoke-rows] skip: legacy-128-mapping.md not present")
        return 0
    if not TESTING_DIR.is_dir():
        print("[legacy-smoke-rows] skip: .testing/ not present")
        return 0

    known_rows = _parse_mapping_rows(MAPPING_DOC)
    feature_refs = _scan_feature_refs(TESTING_DIR)

    if not known_rows:
        print("[legacy-smoke-rows] FAIL: mapping doc 未解析到任何行号；表格式可能变更")
        return 1

    violations: list[str] = []
    for row_token, refs in sorted(feature_refs.items()):
        if row_token not in known_rows:
            for fp, line_no in refs:
                rel = fp.relative_to(REPO).as_posix()
                violations.append(
                    f"{rel}:{line_no}: 引用 '旧 xlsx 行 {row_token}' 但 mapping doc 无此行号"
                )

    if violations:
        print(f"[legacy-smoke-rows] FAIL: {len(violations)} dangling reference(s):")
        for v in violations:
            print(f"  {v}")
        print()
        print(
            "[legacy-smoke-rows] hint: .feature Trace 引用的行号必须在 "
            ".testing/cross-cutting/legacy-128-mapping.md 出现；"
            "新增引用前先在 mapping doc 登记。"
        )
        return 1

    print(
        f"[legacy-smoke-rows] OK: scanned {len(feature_refs)} unique row reference(s) "
        f"in .feature(s); all resolve in mapping doc ({len(known_rows)} known rows)"
    )
    if args.verbose:
        unused = sorted(known_rows - set(feature_refs.keys()))
        print(f"  mapping doc rows not referenced by any .feature: {len(unused)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
