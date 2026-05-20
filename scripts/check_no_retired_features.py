#!/usr/bin/env python3
"""check_no_retired_features.py — preflight 段 20

强约束（v4.1 二轮再砍 / R15 + R17）：
    K12 大屏（zw-brain-dashboard / dashboard_bff / DashboardBffHandler）已退役（R17）。
    alembic 迁移链已删除（R15，新项目用 SQLAlchemy drop & recreate）。
    任何 .py / .sh / .toml / .ini / .yml / .json 文件中不得出现下列 token：
      - K12 dashboard 相关：zw-brain-dashboard, dashboard_bff, DashboardBffHandler,
        DASHBOARD_ROOT, get_dashboard_bff_host, get_dashboard_bff_port,
        zw-brain-dashboard-bff, dashboard.render_command_center,
        dashboard.compliance.query
      - alembic 相关：from alembic, import alembic, alembic upgrade, alembic.ini,
        alembic.config, alembic.command

允许例外：
      - 历史档案章节（基线 §11 R15/R17 反转说明 / D-编号决策记录 / 退役注释）
      - 本脚本自身

退出码：0 = 全部通过；1 = 至少一处违反

使用：
    ./scripts/check_no_retired_features.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 扫描扩展名
EXTENSIONS = (".py", ".sh", ".toml", ".ini", ".yml", ".yaml", ".json", ".js", ".md")

# 跳过路径
SKIP_PATH_FRAGMENTS = (
    "/.venv/",
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.data/",
    "/.reviews/",
    "/old/",  # 旧平台真实数据（含 alembic / dashboard 字面值是旧平台事实）
    "/dist/",
    "/build/",
    "/.testing/",
)

# 退役 token 模式（独立 token 形式）
RETIRED_PATTERNS = (
    (re.compile(r"\bzw-brain-dashboard\b"), "K12 dashboard 目录已退役 (R17)"),
    (re.compile(r"\bdashboard_bff\b"), "K12 dashboard BFF 已退役 (R17)"),
    (re.compile(r"\bDashboardBffHandler\b"), "K12 dashboard handler 已退役 (R17)"),
    (re.compile(r"\bDASHBOARD_ROOT\b"), "K12 dashboard root 常量已退役 (R17)"),
    (re.compile(r"\bget_dashboard_bff_host\b"), "K12 dashboard BFF host 函数已退役 (R17)"),
    (re.compile(r"\bget_dashboard_bff_port\b"), "K12 dashboard BFF port 函数已退役 (R17)"),
    (re.compile(r"\bdashboard\.render_command_center\b"), "dashboard.render_command_center Skill 已退役 (R17)"),
    (re.compile(r"\bdashboard\.compliance\.query\b"), "dashboard.compliance.query Skill 已退役 (R17)"),
    (re.compile(r"\bfrom alembic\b"), "alembic import 已退役 (R15)"),
    (re.compile(r"\bimport alembic\b"), "alembic import 已退役 (R15)"),
    (re.compile(r"\balembic upgrade\b"), "alembic upgrade 命令已退役 (R15)"),
    (re.compile(r"\balembic\.config\b"), "alembic.config 已退役 (R15)"),
    (re.compile(r"\balembic\.command\b"), "alembic.command 已退役 (R15)"),
)

# 允许整文件白名单（历史档案 / R15+R17 反转说明）
ALLOWED_FILES = (
    "docs/approved/zw-brain-architecture.md",  # 唯一基线（含 R15/R17 反转说明）
    "docs/approved/README.md",  # 单一导航
    "docs/reconstructs/README.md",  # 旧仓→新仓映射导航
    "docs/roles-permissions-old-platform-vs-zw-brain-handoff.md",  # 含 R15 通告
    "docs/deployment/sd-default-onboarding.md",  # 客户上线说明含 R15/R17 说明
    "docs/deployment/docker-image-deployment.md",  # 同上
    "docs/deployment/handover-checklist.md",  # 同上
    "scripts/check_no_retired_features.py",  # 本脚本自身
    "scripts/check_no_legacy_role_codes.py",  # 含 R15 注释说明
    "CLAUDE.md",  # 决策记录含 D15/D23+R15+R17 反转注
)

# 允许 line markers（命中即跳过该行）
ALLOWED_LINE_MARKERS = (
    "R15",  # alembic 退役决策标签
    "R17",  # K12 退役决策标签
    "v4.1 R15",
    "v4.1 R17",
    "已退役 (R",
    "已删除（v4.1",
    "已删除 (v4.1",
    "alembic 删除",
    "K12 dashboard unit retired",
    "K12 dashboard typography check retired",
    "K12 dashboard BFF retired",
    "K12 dashboard BFF 退役",
    "K12 dashboard 目录已退役",
    "K12 大屏已退役",
    "v4.1 二轮再砍",
    "v4.1 二轮反转",
    "不用 alembic",
    "不再依赖 alembic",
    "退役 (R17 / v4.1)",
    "(R17 / v4.1)",
    "(R15 / v4.1)",
    "二次反转",
)


def should_skip_path(path: Path) -> bool:
    s = str(path)
    if any(frag in s for frag in SKIP_PATH_FRAGMENTS):
        return True
    rel = path.relative_to(REPO).as_posix()
    return rel in ALLOWED_FILES


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (lineno, line, reason) for violations."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    violations = []
    for lineno, line in enumerate(lines, start=1):
        if any(marker in line for marker in ALLOWED_LINE_MARKERS):
            continue
        for pattern, reason in RETIRED_PATTERNS:
            if pattern.search(line):
                violations.append((lineno, line.strip()[:200], reason))
                break
    return violations


def main() -> int:
    files_scanned = 0
    violations = []

    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in EXTENSIONS:
            continue
        if should_skip_path(path):
            continue
        files_scanned += 1
        for lineno, line, reason in scan_file(path):
            rel = path.relative_to(REPO).as_posix()
            violations.append(f"{rel}:{lineno}: [{reason}] {line}")

    if violations:
        print(f"[no-retired-features] FAIL: scanned {files_scanned} files, {len(violations)} violation(s):")
        for v in violations:
            print(f"  {v}")
        print()
        print("[no-retired-features] hint: K12 dashboard 退役 (R17) / alembic 删除 (R15)；如需引用历史，加 R15/R17 注脚或在 ALLOWED_LINE_MARKERS / ALLOWED_FILES 补充。")
        return 1

    print(f"[no-retired-features] ok: scanned {files_scanned} files; no retired-feature residue (allowed files: {len(ALLOWED_FILES)}; allowed markers: {len(ALLOWED_LINE_MARKERS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
