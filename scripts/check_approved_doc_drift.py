#!/usr/bin/env python3
"""preflight 段 44 — D-编号决策真值源回灌守卫 (D32.d 兑现).

背景（来自 CLAUDE.md D32.d meta finding）
----------------------------------------
D31/D32 双轮 retrofit 暴露了一个反复出现的反模式：

  > D-编号决策（如 D31）在 CLAUDE.md 落地时，**多处真值源**（架构基线 / 飞轮 /
  > mapping doc / yaml fixture / Wave readme / reconstruction plan）需要跟随
  > 同步，但人工"靠自觉"完成回灌时容易遗漏。

D31 原 P0 真值源回灌覆盖了 7 文件，但**漏引用 `docs/reconstructs/` 内 2 份核心
plan**（dsp-dataservice / dsp-sharezone-topic-package）。这种"D-编号网络断裂"
要靠机械检查兜底。

本守卫做什么
-----------
1. **仅在 PR-mode 下启用**（PREFLIGHT_BASE 指向 origin/main 等基线分支时）；
   本地 main 分支或 worktree 头 == base 时直接 skip（无新 D-编号需要校验）。
2. **从 CLAUDE.md diff 提取本分支新增的 D-编号决策段**（形如 `- [date] DXX:`）。
3. **提取每段决策内的"关键引用"**（启发式三类）：
     (a) 反引号包围的 markdown 路径（`docs/.../*.md`）
     (b) "A 类 / D 类 / B 类" 等业务方分类代号
     (c) 业务方 PR 引用 `PR #N`
4. **全仓 grep 这些引用**（在 docs/ + .testing/ + tests/fixtures/ + CLAUDE.md
   范围内），找出**出现 ≥3 次该引用但未提到新 D-编号**的文件 = 候选漂移点。
5. **以 WARN-only 模式输出报告**（exit 0，不阻塞主线）。

为何 WARN-only
-------------
- 启发式提取无法 100% 命中所有合法回灌（例如 plan path 本身就是被引用的目标，
  内部不需要再"自引用 D-编号"）；强 FAIL 易误报反而失信。
- 阶段一暴露 D-编号网络断裂候选给业务方/产品 review，配合 D32 P0 真值源回灌
  人工兜底；阶段二（CLAUDE.md D-编号引用密度足够稳定后）再考虑升级 FAIL。
- 元规则参考：架构基线附录 D「先 WARN、稳定后再 FAIL」演进路径。

触发条件
-------
- PREFLIGHT_BASE=origin/main（CI / pre-push hook 通常会设）
- 或 ZW_BRAIN_DRIFT_BASE 显式覆盖（本地实验用）

误报应对
-------
- 反引号路径如果是文件路径自身（plan 文件不需要回引自己引入的 D-编号），脚本
  通过 `_file_excluded_self_reference` 路径相等比较自动排除。
- 如新 D-编号决策本身就只影响代码层（不涉及文档真值源），脚本仍会扫但
  通常不会有漂移点；属于合理 0 报告。
- 误报候选可在 PR comment 标记 ignore，或调整 `HIGH_DENSITY_REF_THRESHOLD`
  常量（默认 3 — 出现 ≥3 次才算"高密度引用"，过滤偶发提及）。
- 路径扫描范围：默认接受 `docs/` / `.testing/` / `tests/fixtures/` 三类前缀
  （与 SCAN_ROOTS 一致）；外部路径形如 `../foo.md` 不参与漂移判定。

退出码
-----
    0 = OK（无新 D-编号 / 全部回灌完整 / 非 PR-mode skip）
    0 = WARN 模式发现漂移候选但不阻塞主线（默认）
    1 = `--strict` 模式发现漂移候选（阶段二启用）
    1 = base ref 不可解析（参数错误，明示失败而非伪绿）

使用
----
    ./scripts/check_approved_doc_drift.py
    PREFLIGHT_BASE=origin/main ./scripts/check_approved_doc_drift.py --verbose
    ./scripts/check_approved_doc_drift.py --base origin/main  # 显式 override

接入：scripts/preflight.sh 段 44
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO / "CLAUDE.md"

# 仓内回灌真值源范围（哪些目录下的文件需要校验"D-编号是否被引用"）
SCAN_ROOTS = [
    REPO / "docs",
    REPO / ".testing",
    REPO / "tests" / "fixtures",
]
# CLAUDE.md 本身也算回灌目标
SCAN_FILES = [CLAUDE_MD]

# D-编号决策段头匹配：- [2026-MM-DD] DXX[.suffix]: ...
# 兼容形态：D32 / D32.a / D32.d / D31 / D30
D_NUM_HEADER_RE = re.compile(
    r"^[-*]\s*\[\d{4}-\d{2}-\d{2}\]\s+(D\d+(?:\.[a-z])?)[:：]",
)
# 段内反引号路径
BACKTICK_PATH_RE = re.compile(r"`([^`]+\.md)`")
# A 类 / D 类 等业务方代号
CATEGORY_LABEL_RE = re.compile(r"([A-Z])\s*类")
# PR 引用
PR_REF_RE = re.compile(r"PR\s*#(\d+)")

# 高密度引用阈值：某关键引用在文件内出现 ≥N 次才算"高密度"（过滤偶发提及）
HIGH_DENSITY_REF_THRESHOLD = 3

# 反引号路径前缀白名单（与 SCAN_ROOTS 对齐）：仅扫这些前缀下的 .md 路径
SCAN_PATH_PREFIXES = ("docs/", ".testing/", "tests/fixtures/")

# 路径自引用排除（plan 文件自身不需要回引 D-编号）
# 启发式：如果文件路径本身 == 被提取的反引号路径，则该文件天然是引用目标，
# 不算"应该自我回引 D-编号"的漂移候选。


def _validate_base(base: str) -> tuple[bool, str]:
    """校验 base ref 可解析且不等于 HEAD。

    返回 (ok, reason):
      ok=True, reason="resolvable"           — base 可解析且 != HEAD（继续校验）
      ok=True, reason="head_equals_base"     — base 可解析但 == HEAD（合理 skip）
      ok=False, reason="unresolvable"        — base 不可解析（参数错误）
    """
    try:
        base_sha = subprocess.check_output(
            ["git", "rev-parse", "--verify", base],
            cwd=REPO, stderr=subprocess.DEVNULL,
        ).decode().strip()
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO
        ).decode().strip()
    except subprocess.CalledProcessError:
        return False, "unresolvable"
    if base_sha == head_sha:
        return True, "head_equals_base"
    return True, "resolvable"


def _resolve_base_from_env() -> str | None:
    """读环境变量返回 base ref，未设返回 None（本地非 PR-mode）。"""
    return os.environ.get("ZW_BRAIN_DRIFT_BASE") or os.environ.get("PREFLIGHT_BASE")


def _diff_claude_md(base: str) -> str:
    """返回 CLAUDE.md 的 unified diff（base...HEAD）。

    不静默吞错：CalledProcessError 会向上传播由 main() 显式处理；
    若 base 已通过 _validate_base 校验，此处仅可能因 IO 异常失败。
    """
    return subprocess.check_output(
        ["git", "diff", f"{base}...HEAD", "--", "CLAUDE.md"],
        cwd=REPO,
    ).decode()


def _extract_new_d_numbers(diff_text: str) -> dict[str, list[str]]:
    """从 diff 中提取新增 (+) 的 D-编号决策段。

    返回 {D-编号: [段内文本行...]}（仅 + 行）。
    例如：{"D32": [...], "D32.a": [...], "D32.d": [...]}.
    """
    new_blocks: dict[str, list[str]] = {}
    current_d: str | None = None
    for line in diff_text.split("\n"):
        if not line.startswith("+") or line.startswith("+++"):
            # 不是新增行（context / 删除行 / hunk 头 / +++ 文件头）：D-编号段形态上是
            # 一段连续的 + 行，遇到任何非 + 行即结束采集，避免把同 hunk 后续无关 +
            # 行误并入上一段。
            current_d = None
            continue
        # 新增行：去掉 + 前缀
        body = line[1:]
        # 检测段头
        m = D_NUM_HEADER_RE.match(body.lstrip())
        if m:
            current_d = m.group(1)
            new_blocks.setdefault(current_d, []).append(body)
            continue
        # 段内续行（缩进或空行也视作同段；但遇到空 + 行（仅 "+"）或下一个段头才换段）
        if current_d is not None:
            # 续行：必须是缩进或者本就是该段后续描述
            # 简化：所有 + 行只要不是新 D-编号段头都累积进当前段
            new_blocks[current_d].append(body)
    return new_blocks


def _extract_keywords(block_lines: list[str]) -> tuple[set[str], set[str], set[str]]:
    """从一个 D-编号段提取 (paths, categories, prs).

    paths: 反引号包围的 *.md 路径，去 leading `./`，仅保留 SCAN_PATH_PREFIXES 白名单内
    categories: A 类 / D 类 等 (返回 {"A", "D"})；当前仅用于 verbose log，不参与扫描
    prs: PR #129 等 (返回 {"129"})
    """
    text = "\n".join(block_lines)
    paths: set[str] = set()
    for m in BACKTICK_PATH_RE.finditer(text):
        path = m.group(1).strip()
        # 规范化：去 ./
        if path.startswith("./"):
            path = path[2:]
        # 仅保留白名单前缀（与 SCAN_ROOTS 对齐；其他路径不在本守卫范围）
        if path.startswith(SCAN_PATH_PREFIXES):
            paths.add(path)
    categories = {m.group(1) for m in CATEGORY_LABEL_RE.finditer(text)}
    prs = {m.group(1) for m in PR_REF_RE.finditer(text)}
    return paths, categories, prs


def _scan_repo_for_keyword(keyword: str) -> dict[Path, int]:
    """统计仓内文件出现该 keyword 的次数（仅 SCAN_ROOTS + SCAN_FILES）。

    返回 {文件路径: 出现次数}。文件出现次数 = 0 则不入字典。
    """
    counts: dict[Path, int] = {}
    files_to_scan: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            files_to_scan.extend(root.rglob("*.md"))
            files_to_scan.extend(root.rglob("*.yaml"))
            files_to_scan.extend(root.rglob("*.yml"))
    for f in SCAN_FILES:
        if f.is_file():
            files_to_scan.append(f)

    for fp in files_to_scan:
        try:
            text = fp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        n = text.count(keyword)
        if n > 0:
            counts[fp] = n
    return counts


def _file_references_d_number(fp: Path, d_number: str) -> bool:
    """检查文件是否提到某 D-编号（D32 命中 D32 / D32.a / D32.d 任意）。"""
    try:
        text = fp.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    # 命中 D-编号本体 + sub-letter 变种
    if re.search(rf"\b{re.escape(d_number)}\b", text):
        return True
    # 如果是 D32.a，根 D-编号 D32 也算引用
    if "." in d_number:
        root = d_number.split(".")[0]
        if re.search(rf"\b{re.escape(root)}\b", text):
            return True
    return False


def _file_excluded_self_reference(fp: Path, path_keyword: str) -> bool:
    """判断该文件是否就是被引用的 plan 自身（自引用，不需要回引 D-编号）。

    例如：path_keyword = "docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md"
    fp = REPO / "docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md"
    → 排除（plan 本身不需要回引 D-编号）。
    """
    try:
        rel = fp.relative_to(REPO).as_posix()
    except ValueError:
        return False
    return rel == path_keyword


def _find_drift_candidates(
    d_number: str, paths: set[str], prs: set[str]
) -> list[str]:
    """对一个新 D-编号，返回漂移候选报告行。

    检测规则：
      - 对每条反引号路径 keyword，找仓内出现 ≥N 次该路径的文件
      - 该文件如果同时未引用 d_number（或其 root D 编号）→ 候选漂移
      - 排除 self-reference（文件就是 path 自身）
      - PR ref 同理

    注：categories（A 类 / D 类）单字符太宽，false-positive 多，不进入本扫描；
    仅在 verbose log 输出供 debug。
    """
    findings: list[str] = []
    for path_kw in sorted(paths):
        counts = _scan_repo_for_keyword(path_kw)
        for fp, n in sorted(counts.items()):
            if n < HIGH_DENSITY_REF_THRESHOLD:
                continue
            if _file_excluded_self_reference(fp, path_kw):
                continue
            if _file_references_d_number(fp, d_number):
                continue
            rel = fp.relative_to(REPO).as_posix()
            findings.append(
                f"  {d_number} → {rel}: 提到 `{path_kw}` {n} 次但未引用 {d_number}"
            )
    # 业务方 PR 引用：跨文件 PR ref 应配套 D-编号
    for pr in sorted(prs):
        pr_keyword = f"PR #{pr}"
        counts = _scan_repo_for_keyword(pr_keyword)
        for fp, n in sorted(counts.items()):
            if n < HIGH_DENSITY_REF_THRESHOLD:
                continue
            if _file_references_d_number(fp, d_number):
                continue
            rel = fp.relative_to(REPO).as_posix()
            findings.append(
                f"  {d_number} → {rel}: 提到 'PR #{pr}' {n} 次但未引用 {d_number}"
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="D-编号决策真值源回灌守卫")
    parser.add_argument(
        "--base",
        default=None,
        help="对比的 base ref（默认读 PREFLIGHT_BASE / ZW_BRAIN_DRIFT_BASE 环境变量）",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="升级 WARN → FAIL（阶段二启用，目前默认关闭）",
    )
    args = parser.parse_args()

    if not CLAUDE_MD.is_file():
        print("[approved-doc-drift] skip: CLAUDE.md not present")
        return 0

    base = args.base or _resolve_base_from_env()
    if base is None:
        print("[approved-doc-drift] skip: 非 PR-mode（PREFLIGHT_BASE 未设）")
        return 0

    ok, reason = _validate_base(base)
    if not ok:
        print(f"[approved-doc-drift] FAIL: base ref '{base}' 不可解析")
        print("  hint: 检查 PREFLIGHT_BASE / ZW_BRAIN_DRIFT_BASE / --base 取值；")
        print("  CI 通常需先 fetch origin/main 才能解析。")
        return 1
    if reason == "head_equals_base":
        print(f"[approved-doc-drift] skip: HEAD == {base}（本分支无新增 commit）")
        return 0

    diff_text = _diff_claude_md(base)
    if not diff_text.strip():
        print(f"[approved-doc-drift] OK: CLAUDE.md 自 {base} 起无 diff")
        return 0

    new_blocks = _extract_new_d_numbers(diff_text)
    if not new_blocks:
        print(
            f"[approved-doc-drift] OK: CLAUDE.md 自 {base} 起有 diff 但未新增 D-编号决策段"
        )
        return 0

    all_findings: list[str] = []
    summary: list[str] = []
    for d_number, block_lines in sorted(new_blocks.items()):
        paths, categories, prs = _extract_keywords(block_lines)
        if args.verbose:
            print(
                f"  [verbose] {d_number}: paths={sorted(paths)} "
                f"categories={sorted(categories)} prs={sorted(prs)}"
            )
        if not paths and not prs:
            summary.append(f"  {d_number}: 未提取到反引号路径或 PR ref（无需校验）")
            continue
        findings = _find_drift_candidates(d_number, paths, prs)
        if findings:
            all_findings.extend(findings)
        else:
            summary.append(
                f"  {d_number}: {len(paths)} path / {len(prs)} PR ref，无漂移候选"
            )

    if all_findings:
        # WARN-only 模式输出
        print(
            f"[approved-doc-drift] WARN: 自 {base} 起新增 {len(new_blocks)} 条 D-编号决策，"
            f"发现 {len(all_findings)} 个真值源回灌漂移候选："
        )
        for f in all_findings:
            print(f)
        if summary:
            print()
            print("[approved-doc-drift] 其他段（无漂移）：")
            for s in summary:
                print(s)
        print()
        print(
            "[approved-doc-drift] hint: 新 D-编号决策应在所有相关真值源（架构基线 / "
            "飞轮 / mapping doc / yaml fixture / signoff doc 等）显式回引；"
            "本守卫为 WARN-only，请 PR reviewer / 业务方 review 时确认是否漏回灌。"
        )
        print(
            "[approved-doc-drift] 见 CLAUDE.md D32.d meta finding；"
            "升级 FAIL 路径见脚本头 README。"
        )
        if args.strict:
            return 1
        return 0

    print(
        f"[approved-doc-drift] OK: 自 {base} 起新增 {len(new_blocks)} 条 D-编号决策；"
        f"全部真值源回灌完整"
    )
    if args.verbose and summary:
        for s in summary:
            print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
