#!/usr/bin/env python3
"""
check_no_legacy_role_codes.py — preflight 段 19

强约束（设计基线 §附录 D / D23 retrofit）：
    R1-R8 用户角色码已于 2026-05-19 退役（详见 docs/approved/zw-brain-roles.md）。
    任何 .py / .js / .json / .md 文件中独立 token 形式的 r1..r8 / R1..R8 字面值
    都不得出现，除非命中下方两类豁免之一。

匹配模型（实际实现，无 role-context 语义判定）：
    扫描就是单条件 `\\b[rR][1-8]\\b`——不区分 namespace。已退役用户角色码 R1-R8
    与基线 §11 架构约束编号 R7/R10、approved-doc frontmatter invariants R1-R5
    共用这个 token 空间，本脚本**不**靠同行上下文 regex 区分它们，而是靠两类显式
    豁免兜底误命中：
      1. ALLOWED_LINE_MARKERS — 同行命中任一短语即跳过该行（精确短语，避免过宽）。
      2. ALLOWED_FILES — 整文件白名单，用于"角色/架构编号密集、逐行加 marker 不划算"
         的权威源（roles.md / architecture.md / policy.py / role_codes.py / CLAUDE.md
         及若干引用 §11 R 编号的 reconstructs 文档）。

    已知取舍：新增引用架构约束 R 编号的 approved/reconstructs 文档时，可能需要往
    ALLOWED_FILES 追加一条。这是 token 空间重叠的代价，不是精确 namespace 判定；
    两个豁免列表的当前条目数以代码中的常量为准，不在本 docstring 复述以免漂移。

注：原 alembic 0009 数据迁移映射已在 v4.1 R15 删除 alembic 时一并清理。

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_no_legacy_role_codes.py
    ./scripts/check_no_legacy_role_codes.py --verbose

接入：scripts/preflight.sh 段 19（D23 retrofit 兜底）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 扫描扩展名
EXTENSIONS = (".py", ".js", ".json", ".md")

# 跳过路径（gitignored / cache / build artifacts / 旧平台只读资料）
SKIP_PATH_FRAGMENTS = (
    "/.venv/",
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.claude/worktrees/",  # 其它 Claude 会话的 git worktree 副本，不属本仓库主树
    "/.claude/twin-workspaces/",  # twin supervisor/worker 运行时编排状态（gitignored）；与 .reviews/.data 同类，非产品代码，含基线 §11 架构约束 R6/R7 引用
    "/.data/",
    "/.reviews/",
    "/.experiences/",  # 已删除（本次 D23 退役）
    "/.testing/",  # Wave 测试用例设计文档（.md 中 R1-R15 是基线 §11 设计主张引用，与已退役 R1-R8 用户角色码同名但不同 namespace）；.feature 文件本就不在 EXTENSIONS 内
    "/old/",  # 旧平台真实数据 / 文档 / xlsx（D23 前的事实源，本身含旧角色码）
    "/dist/",
    "/build/",
)

# 检查模式：独立 token 形式的 r1-r8 或 R1-R8
LEGACY_PATTERN = re.compile(r"\b[rR][1-8]\b")

# 允许出现的 intentional 上下文标记（命中即跳过该行）
ALLOWED_LINE_MARKERS = (
    "retrofit (D23-D29)",
    "2026-05-19 retrofit",
    "D23 retrofit",
    "R1-R8 角色矩阵",
    "R1-R8 已退役",
    "R1-R8 退役",
    "R1-R8 角色码",
    "r1-r8 字面值",
    "r1-r8 残留",
    "_LEGACY_ROLE_CODES",
    "_LEGACY_TO_NEW",
    "legacy R1-R8",
    "R1-R8 / 部门",
    "原版 R 编号",
    "6 个 ROLE",
    "ROLE_* 6 角色",
    # F4 fix: 修剪过宽 markers — 删除短/泛 marker（"D23:" / "status='" 等），改为收紧的精确短语
    # check_approved_docs.py 用 R1-R5 标识 approved-doc frontmatter invariants，已整文件白名单
    # （ALLOWED_FILES 中），无需逐行 marker
    # build_true_data_seed.py 中迁移注释含旧 r3/r5 描述
    "旧 r3",
    "旧 r5",
    # 基线 §11 架构约束 R7（OPC 单人维护）违反引用 — 与已退役用户角色码 R1-R8 同名异 namespace
    "violates R7",
)

# 允许整文件白名单（这些文件本身就是描述 R1-R8 退役的权威源）
# alembic 0009 + 其单元测试已在 v4.1 R15 删除 alembic 时一并清理
ALLOWED_FILES = (
    "docs/approved/zw-brain-architecture.md",  # 唯一基线（含 R10 R1-R8 退役说明）
    "docs/approved/zw-brain-roles.md",  # 7 角色规范 + R1-R8 退役映射
    "docs/approved/README.md",  # 单一导航 spine
    "docs/reconstructs/README.md",  # 旧仓→新仓映射导航
    "scripts/check_no_legacy_role_codes.py",  # 本脚本自身
    "zw_brain/domain/policy.py",  # 启动检查 _LEGACY_ROLE_CODES 本身需含 r1-r8
    "zw_brain/domain/role_codes.py",  # 单一来源：LEGACY_ROLE_CODES 集合定义
    "CLAUDE.md",  # 决策记录 D-编号引用
    # check_approved_docs.py 的 R1-R5 是 approved-doc frontmatter invariants 规则编号
    # 完全不同 namespace（与用户角色码无关），整文件白名单
    "scripts/check_approved_docs.py",
    # P0-01 capability registry classification 文档引用 §11 架构约束 R7/R8/R10/R14/R15
    # 完全不同 namespace（与已退役 R1-R8 用户角色码无关），整文件白名单
    "docs/reconstructs/p0-contract-classification.md",
)


def should_skip_path(path: Path) -> bool:
    s = str(path)
    if any(frag in s for frag in SKIP_PATH_FRAGMENTS):
        return True
    rel = path.relative_to(REPO).as_posix()
    return rel in ALLOWED_FILES


def scan_file(path: Path, verbose: bool = False) -> list[str]:
    """Return list of violation strings (empty = clean)."""
    violations: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not LEGACY_PATTERN.search(line):
            continue
        if any(marker in line for marker in ALLOWED_LINE_MARKERS):
            continue
        violations.append(f"{path.relative_to(REPO)}:{lineno}: {line.strip()[:160]}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="D23 retrofit: 仓库内不得出现 R1-R8 字面值")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    all_violations: list[str] = []
    scanned = 0
    for ext in EXTENSIONS:
        for path in REPO.rglob(f"*{ext}"):
            if should_skip_path(path):
                continue
            scanned += 1
            v = scan_file(path)
            if v:
                all_violations.extend(v)

    if all_violations:
        print(f"[no-legacy-role-codes] FAIL: scanned {scanned} files, {len(all_violations)} violation(s):")
        for v in all_violations:
            print(f"  {v}")
        print()
        print("[no-legacy-role-codes] hint: R1-R8 用户角色码已退役（D23）；如需引用历史，加 retrofit 注脚或在 ALLOWED_LINE_MARKERS 中补充。")
        return 1

    print(f"[no-legacy-role-codes] OK: scanned {scanned} files, no R1-R8 字面值残留")
    if args.verbose:
        print(f"  (allowed files: {len(ALLOWED_FILES)}; allowed markers: {len(ALLOWED_LINE_MARKERS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
