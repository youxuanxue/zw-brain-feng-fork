#!/usr/bin/env python3
"""check_grep_guards_batch.py — 段 19/20/21 同构 grep 守卫合并遍历.

三个同构守卫（no-legacy-role-codes / no-retired-features / no-numbered-routes）
此前各跑一遍 Python 解释器 + rglob 全树遍历。本批量器用 ``guard_lib.scan_many``
让三者**共享一次 git ls-files 文件枚举**，每个文件按各自扩展名 / roots / 豁免
归属后逐行扫一次——三段报错语义与段 ID **逐字保留**，只去掉重复遍历成本。

实测（worktree 小文件集）三段串跑 ~1.2s（3× 解释器启动 + 3× 遍历）→ 合并后
单进程单遍历显著下降；canonical 全仓（57+ .vue / 全 docs）降幅更大。

独立运行（各原脚本 shim 仍可单跑某一段）：
    ./scripts/check_grep_guards_batch.py                 # 全跑三段
    ./scripts/check_grep_guards_batch.py --only no-legacy-role-codes
    ./scripts/check_grep_guards_batch.py --only no-retired-features
    ./scripts/check_grep_guards_batch.py --only no-numbered-routes

每段语义、豁免清单、ALLOWED_FILES 与原脚本一一对应（见各 GuardSpec 注释）。
接入：scripts/preflight.sh 段 19/20/21（单 run_check 调用，三段标签输出）。
"""
from __future__ import annotations

import argparse
import re
import sys

from guard_lib import SKIP_PATH_FRAGMENTS as _SHARED_SKIP
from guard_lib import GuardSpec, register_grep_guard, scan_many

# ════════════════════════════════════════════════════════════════════════════
# 段 19 — no-legacy-role-codes (D23 retrofit)
# ════════════════════════════════════════════════════════════════════════════
LEGACY_PATTERN = re.compile(r"\b[rR][1-8]\b")

LEGACY_EXTENSIONS = (".py", ".js", ".json", ".md")
# 段 19 专属跳过（在共享 SKIP 基础上加 .testing —— Wave 测试设计文档含基线 §11
# R1-R15 引用，与已退役 R1-R8 用户角色码同名异 namespace）。
LEGACY_SKIP = _SHARED_SKIP + ("/.testing/",)

LEGACY_ALLOWED_FILES = (
    "docs/approved/zw-brain-architecture.md",
    "docs/approved/zw-brain-roles.md",
    "docs/approved/README.md",
    "docs/reconstructs/README.md",
    "scripts/check_no_legacy_role_codes.py",
    "scripts/check_grep_guards_batch.py",  # 本批量器自身含 r1-r8 正则字面
    "scripts/check_guard_scan_surface.py",  # 元守卫豁免理由含 R1-R8 架构锚点示例字面
    "zw_brain/domain/policy.py",
    "zw_brain/domain/role_codes.py",
    "CLAUDE.md",
    "scripts/check_approved_docs.py",
    "docs/reconstructs/p0-contract-classification.md",
    "docs/approved/zw-brain-flywheel.md",
    "docs/legacy-not-reproduce-signoff.md",
    "docs/decisions/feedback-0611-gate-D57.md",
    "docs/decisions/decision-log.md",  # D64 — D-索引全量副本（原 CLAUDE.md 内，含 R1-R8 退役史）
)

LEGACY_ALLOWED_LINE_MARKERS = (
    "retrofit (D23-D29)", "2026-05-19 retrofit", "D23 retrofit",
    "R1-R8 角色矩阵", "R1-R8 已退役", "R1-R8 退役", "R1-R8 角色码",
    "r1-r8 字面值", "r1-r8 残留", "_LEGACY_ROLE_CODES", "_LEGACY_TO_NEW",
    "legacy R1-R8", "R1-R8 / 部门", "原版 R 编号", "6 个 ROLE", "ROLE_* 6 角色",
    "旧 r3", "旧 r5", "violates R7", "架构约束 R7", "架构约束 R4",
    "R8 反 per-tenant fork",
)


def _legacy_matcher(line: str) -> tuple[bool, str]:
    return (bool(LEGACY_PATTERN.search(line)), "")


# ════════════════════════════════════════════════════════════════════════════
# 段 20 — no-retired-features (K12 dashboard 退役)
# ════════════════════════════════════════════════════════════════════════════
# 注：alembic 退役模式（from/import alembic、alembic upgrade/config/command）已于 D58
# **整体移除** —— 反转 D23 二次升级，alembic forward-migration 回归取代冷启动 drop&recreate
# （全文 docs/decisions/alembic-migration-reintroduction-D58.md）。本段只剩 K12 dashboard 退役守卫。
RETIRED_PATTERNS = (
    (re.compile(r"\bzw-brain-dashboard\b"), "K12 dashboard 目录已退役 (D15 二次反转)"),
    (re.compile(r"\bdashboard_bff\b"), "K12 dashboard BFF 已退役 (D15 二次反转)"),
    (re.compile(r"\bDashboardBffHandler\b"), "K12 dashboard handler 已退役 (D15 二次反转)"),
    (re.compile(r"\bDASHBOARD_ROOT\b"), "K12 dashboard root 常量已退役 (D15 二次反转)"),
    (re.compile(r"\bget_dashboard_bff_host\b"), "K12 dashboard BFF host 函数已退役 (D15 二次反转)"),
    (re.compile(r"\bget_dashboard_bff_port\b"), "K12 dashboard BFF port 函数已退役 (D15 二次反转)"),
    (re.compile(r"\bdashboard\.render_command_center\b"), "dashboard.render_command_center Skill 已退役 (D15 二次反转)"),
    (re.compile(r"\bdashboard\.compliance\.query\b"), "dashboard.compliance.query Skill 已退役 (D15 二次反转)"),
)

# .ts/.vue 纳入（2026-06-14 元守卫自发现补面）：dashboard.* 退役 token（K12 大屏）同样可能
# 在前端代码回潮（如 .vue 误调 dashboard.compliance.query）——干净树 0 命中，无误报负债。
RETIRED_EXTENSIONS = (".py", ".sh", ".toml", ".ini", ".yml", ".yaml", ".json", ".js", ".ts", ".vue", ".md")
# /alembic/ 豁免：D58 起 alembic/ 目录（env.py + versions/*_baseline.py）是合法迁移工件，
# alembic 已非退役 token（段 20 反正则随 D58 移除），跳过该目录避免任何残留 token 误扫。
RETIRED_SKIP = _SHARED_SKIP + ("/.testing/", "/alembic/")

RETIRED_ALLOWED_FILES = (
    "docs/approved/zw-brain-architecture.md",
    "docs/approved/README.md",
    "docs/reconstructs/README.md",
    "docs/roles-permissions-old-platform-vs-zw-brain-handoff.md",
    "docs/deployment/sd-default-onboarding.md",
    "docs/deployment/docker-image-deployment.md",
    "docs/deployment/handover-checklist.md",
    "scripts/check_no_retired_features.py",
    "scripts/check_no_legacy_role_codes.py",
    "scripts/check_grep_guards_batch.py",  # 本批量器自身含退役 token 正则字面
    "CLAUDE.md",
    "docs/decisions/decision-log.md",  # D64 — D-索引全量副本（原 CLAUDE.md 内，含 K12/D15 二次反转退役史）
)

RETIRED_ALLOWED_LINE_MARKERS = (
    "alembic 删除", "alembic 整体删除", "alembic 退役", "alembic 迁移链已删除",
    "alembic upgrade 命令已退役", "alembic import 已退役", "alembic.config 已退役",
    "alembic.command 已退役", "不用 alembic", "不再依赖 alembic",
    "K12 大屏已退役", "K12 大屏本期退役", "K12 大屏在本期退役", "独立大屏 K12 本期退役",
    "K12 大屏作为独立部署面", "原 K12 数据治理大屏", "K12 dashboard unit retired",
    "K12 dashboard typography check retired", "K12 dashboard BFF retired",
    "K12 dashboard BFF 退役", "K12 dashboard 目录已退役", "K12 dashboard handler 已退役",
    "K12 dashboard root 常量已退役", "K12 dashboard 数据块已退役", "K12 dashboard 块已退役",
    "K12 dashboard.burdenMetrics 已退役",
    "K12 dashboard / dashboard.render_command_center Skill 已退役",
    "K12 dashboard / dashboard.compliance.query Skill 已退役",
    "dashboard.render_command_center Skill 已退役", "dashboard.compliance.query Skill 已退役",
    "数据治理大屏（已退役）", "二次反转", "二次升级",
)


def _retired_matcher(line: str) -> tuple[bool, str]:
    for pattern, reason in RETIRED_PATTERNS:
        if pattern.search(line):
            return (True, reason)
    return (False, "")


# ════════════════════════════════════════════════════════════════════════════
# 段 21 — no-numbered-routes (route de-identify guardrail)
# ════════════════════════════════════════════════════════════════════════════
NUMBERED_PATTERN = re.compile(r"#/p[0-9]+-[a-z]")

# .ts/.vue 纳入（2026-06-14 元守卫自发现补面）：编号化路由 `#/p<N>-` 最可能出现在前端
# Vue router(.ts)/模板(.vue) 的链接里——这是该守卫**最该**覆盖的面，干净树 0 命中。
NUMBERED_EXTENSIONS = (".py", ".js", ".ts", ".vue", ".html", ".sh", ".md")
NUMBERED_SKIP = _SHARED_SKIP + ("/.testing/",)

NUMBERED_ALLOWED_FILES = (
    "scripts/check_no_numbered_routes.py",
    "scripts/check_grep_guards_batch.py",  # 本批量器自身含 #/p<N>- 示例字面
    "docs/preflight-debt.md",
)


def _numbered_matcher(line: str) -> tuple[bool, str]:
    return (bool(NUMBERED_PATTERN.search(line)), "")


# ════════════════════════════════════════════════════════════════════════════
# Specs + 守卫面注册（供元守卫 check_guard_scan_surface 对账）
# ════════════════════════════════════════════════════════════════════════════
SPECS: dict[str, GuardSpec] = {
    "no-legacy-role-codes": GuardSpec(
        section_id="no-legacy-role-codes",
        extensions=LEGACY_EXTENSIONS,
        matcher=_legacy_matcher,
        allowed_files=LEGACY_ALLOWED_FILES,
        allowed_line_markers=LEGACY_ALLOWED_LINE_MARKERS,
        skip_fragments=LEGACY_SKIP,
    ),
    "no-retired-features": GuardSpec(
        section_id="no-retired-features",
        extensions=RETIRED_EXTENSIONS,
        matcher=_retired_matcher,
        allowed_files=RETIRED_ALLOWED_FILES,
        allowed_line_markers=RETIRED_ALLOWED_LINE_MARKERS,
        skip_fragments=RETIRED_SKIP,
    ),
    "no-numbered-routes": GuardSpec(
        section_id="no-numbered-routes",
        extensions=NUMBERED_EXTENSIONS,
        matcher=_numbered_matcher,
        allowed_files=NUMBERED_ALLOWED_FILES,
        skip_fragments=NUMBERED_SKIP,
    ),
}

# 守卫面注册：roots=() 表示全仓扫描（三段都是全仓）。
register_grep_guard("no-legacy-role-codes", roots=(), extensions=LEGACY_EXTENSIONS,
                    note="D23 retrofit — R1-R8 字面值")
register_grep_guard("no-retired-features", roots=(), extensions=RETIRED_EXTENSIONS,
                    note="K12 dashboard 退役 token（alembic 退役模式 D58 移除）")
register_grep_guard("no-numbered-routes", roots=(), extensions=NUMBERED_EXTENSIONS,
                    note="#/p<N>- 编号化路由")


# 每段失败时的 hint（与原脚本逐字一致）
_HINTS = {
    "no-legacy-role-codes": "R1-R8 用户角色码已退役（D23）；如需引用历史，加 retrofit 注脚或在 ALLOWED_LINE_MARKERS 中补充。",
    "no-retired-features": "K12 dashboard 退役（D15 二次反转）token 不得回潮；如需引用历史，加退役注脚或在 ALLOWED_LINE_MARKERS / ALLOWED_FILES 补充。（alembic 退役模式已于 D58 移除，alembic 回归取代冷启动 drop&recreate。）",
    "no-numbered-routes": "路由去编号化基线：URL 必须用纯语义路径（#/compliance-ops 而非 #/p6-compliance-ops）。编号化是反模式 — IA 一动就全栈改、新增页无处插、URL 对用户不透明。",
}


def _report(section_id: str, violations: list, scanned: int) -> int:
    if violations:
        print(f"[{section_id}] FAIL: scanned {scanned} files, {len(violations)} violation(s):")
        for v in violations[:30]:
            print(f"  {v.render()}")
        if len(violations) > 30:
            print(f"  ... and {len(violations) - 30} more")
        print(f"[{section_id}] hint: {_HINTS[section_id]}")
        return 1
    print(f"[{section_id}] OK: scanned {scanned} files; no residue")
    return 0


def run_section(section_id: str) -> int:
    """单段执行（独立 shim 入口用）：等价 ``--only <section_id>``。"""
    spec = SPECS[section_id]
    results = scan_many([spec])
    return _report(spec.section_id, results[spec.section_id], scan_many.scanned[spec.section_id])


def main() -> int:
    parser = argparse.ArgumentParser(description="段 19/20/21 同构 grep 守卫合并遍历")
    parser.add_argument("--only", choices=tuple(SPECS), help="只跑指定段（独立 shim 用）")
    args = parser.parse_args()

    selected = [SPECS[args.only]] if args.only else list(SPECS.values())
    results = scan_many(selected)
    scanned = scan_many.scanned  # type: ignore[attr-defined]

    rc = 0
    for spec in selected:
        rc |= _report(spec.section_id, results[spec.section_id], scanned[spec.section_id])
    return rc


if __name__ == "__main__":
    sys.exit(main())
