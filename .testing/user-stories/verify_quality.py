#!/usr/bin/env python3
"""
.testing/user-stories/verify_quality.py — preflight 段 5

按 test-philosophy.mdc § 3 + § 5：
    自动校验每个 User Story 是否满足 10 项必填字段 + 4 类质量门禁
    （可执行命令 ✓ / 负向场景 ✓ / 可观测断言 ✓ / 风险类别 ✓）。

校验维度：
    1. 必填字段存在（ID / Title / Trace / Risk Focus / AC / Assertions /
       Linked Tests / Evidence / Status）
    2. AC 至少含 1 条正向 + 1 条负向 + 1 条回归保护
    3. Linked Tests 格式 = `file::TestFunction`，且至少 1 条可执行运行命令
    4. Risk Focus 至少声明 4 类风险中的 ≥1 类（逻辑/回归/安全/运行时）
    5. 状态 ∈ {Draft, Ready, InTest, Done, Archived}

输出：
    - 控制台：每个故事的 PASS/FAIL 摘要
    - 报告：attachments/story-quality-report.md（详细漂移项）

退出码：0 = 全部 PASS；1 = 至少 1 个 FAIL

接入：scripts/preflight.sh 段 5（dev-rules 模板检测此脚本是否存在）
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STORIES_DIR = ROOT / "stories"
ATTACHMENTS_DIR = ROOT / "attachments"
REPORT_PATH = ATTACHMENTS_DIR / "story-quality-report.md"

REQUIRED_HEADINGS_RE = {
    "acceptance_criteria": re.compile(r"^##\s+Acceptance Criteria\b", re.MULTILINE),
    "assertions": re.compile(r"^##\s+Assertions\b", re.MULTILINE),
    "linked_tests": re.compile(r"^##\s+Linked Tests\b", re.MULTILINE),
    "evidence": re.compile(r"^##\s+Evidence\b", re.MULTILINE),
    "status": re.compile(r"^##\s+Status\b", re.MULTILINE),
}

REQUIRED_FRONT_FIELDS = ("ID", "Title", "Trace", "Risk Focus")

VALID_STATUSES = {"Draft", "Ready", "InTest", "Done", "Archived"}

RISK_CATEGORIES = ("逻辑错误", "行为回归", "安全问题", "运行时问题")

# Heuristics
POSITIVE_AC_RE = re.compile(r"AC-?\d+\s*\(?正向\)?", re.IGNORECASE)
NEGATIVE_AC_RE = re.compile(r"AC-?\d+\s*\(?负向\)?", re.IGNORECASE)
REGRESSION_AC_RE = re.compile(r"AC-?\d+\s*\(?回归\)?", re.IGNORECASE)

LINKED_TEST_RE = re.compile(r"`?[\w./-]+`?\s*::\s*`?\w+`?")
RUN_COMMAND_RE = re.compile(r"运行命令\s*[:：]\s*`([^`]+)`")


@dataclass
class StoryIssue:
    severity: str  # "FAIL" | "WARN"
    code: str
    message: str


@dataclass
class StoryReport:
    file: Path
    story_id: str = ""
    title: str = ""
    issues: list[StoryIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if any(i.severity == "FAIL" for i in self.issues) else "PASS"


def parse_story(path: Path) -> StoryReport:
    rep = StoryReport(file=path)
    text = path.read_text(encoding="utf-8")

    # 1) front fields (lines like `- ID: US-001` or `- Title: foo`)
    front_fields: dict[str, str] = {}
    for m in re.finditer(r"^-\s+([A-Za-z][\w \-/]*?)\s*[:：]\s*(.+)$", text, re.MULTILINE):
        front_fields[m.group(1).strip()] = m.group(2).strip()

    rep.story_id = front_fields.get("ID", "")
    rep.title = front_fields.get("Title", "")

    for f in REQUIRED_FRONT_FIELDS:
        if f not in front_fields or not front_fields[f]:
            rep.issues.append(StoryIssue("FAIL", "MISSING_FIELD", f"front field `{f}` missing or empty"))

    # 2) required H2 sections
    for key, pat in REQUIRED_HEADINGS_RE.items():
        if not pat.search(text):
            rep.issues.append(StoryIssue("FAIL", "MISSING_SECTION", f"## {key.replace('_', ' ').title()} section missing"))

    # 3) AC: positive + negative + regression
    if not POSITIVE_AC_RE.search(text):
        rep.issues.append(StoryIssue("FAIL", "AC_NO_POSITIVE", "no positive (正向) AC found"))
    if not NEGATIVE_AC_RE.search(text):
        rep.issues.append(StoryIssue("FAIL", "AC_NO_NEGATIVE", "no negative (负向) AC found"))
    if not REGRESSION_AC_RE.search(text):
        rep.issues.append(StoryIssue("WARN", "AC_NO_REGRESSION", "no regression (回归) AC found"))

    # 4) Linked Tests block must contain at least 1 file::function reference
    linked_section = _extract_section(text, "Linked Tests")
    if linked_section:
        if not LINKED_TEST_RE.search(linked_section):
            rep.issues.append(StoryIssue("FAIL", "LINKED_TESTS_BAD_FORMAT",
                                          "no `file::TestFunction` reference found in Linked Tests"))
        if not RUN_COMMAND_RE.search(linked_section):
            rep.issues.append(StoryIssue("FAIL", "LINKED_TESTS_NO_RUN_CMD",
                                          "no `运行命令: \\`...\\`` runnable command found"))

    # 5) Risk Focus: at least 1 of 4 categories declared
    risk_text = front_fields.get("Risk Focus", "") + "\n" + (_extract_section(text, "Risk Focus") or "")
    if not any(cat in risk_text for cat in RISK_CATEGORIES):
        rep.issues.append(StoryIssue("FAIL", "RISK_NO_CATEGORY",
                                      f"Risk Focus must declare ≥1 of: {', '.join(RISK_CATEGORIES)}"))

    # 6) Status validity
    status_section = _extract_section(text, "Status") or ""
    found_status = None
    for s in VALID_STATUSES:
        if s in status_section:
            found_status = s
            break
    if not found_status:
        rep.issues.append(StoryIssue("WARN", "STATUS_UNCLEAR",
                                      f"Status section does not clearly indicate one of: {sorted(VALID_STATUSES)}"))

    return rep


def _extract_section(text: str, heading: str) -> str:
    """Pull text under `## {heading}` until next `## ` heading or EOF."""
    pat = re.compile(rf"^##\s+{re.escape(heading)}\b(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    m = pat.search(text)
    return m.group(1) if m else ""


def write_report(reports: list[StoryReport]) -> None:
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Story Quality Report",
        "",
        f"_Generated by `verify_quality.py`. Total stories: {len(reports)}._",
        "",
        "| Story | Status | Title | Issues |",
        "| ----- | ------ | ----- | ------ |",
    ]
    for r in reports:
        issues_summary = "; ".join(f"[{i.severity}/{i.code}]" for i in r.issues) or "—"
        lines.append(f"| `{r.story_id or '?'}` | **{r.status}** | {r.title or '_(no title)_'} | {issues_summary} |")
    lines.append("")
    lines.append("## Detail")
    lines.append("")
    for r in reports:
        if not r.issues:
            continue
        lines.append(f"### {r.story_id or r.file.name}")
        lines.append(f"- file: `{r.file.relative_to(ROOT.parent.parent)}`")
        for i in r.issues:
            lines.append(f"- {i.severity} `{i.code}` — {i.message}")
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not STORIES_DIR.exists():
        print(f"[story-quality] skip: {STORIES_DIR.relative_to(ROOT.parent.parent)}/ does not exist")
        print("  (Phase 0 early — stories will appear once Phase 1 starts)")
        return 0

    story_files = sorted(STORIES_DIR.glob("US-*.md"))
    if not story_files:
        print(f"[story-quality] skip: no US-*.md stories in {STORIES_DIR.relative_to(ROOT.parent.parent)}/")
        return 0

    reports = [parse_story(p) for p in story_files]
    write_report(reports)

    failed = [r for r in reports if r.status == "FAIL"]
    if failed:
        print(f"[story-quality] FAIL: {len(failed)}/{len(reports)} stories have hard issues")
        for r in failed:
            print(f"  ✗ {r.story_id or r.file.name}")
            for i in r.issues:
                if i.severity == "FAIL":
                    print(f"      [{i.code}] {i.message}")
        print(f"\n  detail report: {REPORT_PATH.relative_to(ROOT.parent.parent)}")
        return 1

    print(f"[story-quality] OK: {len(reports)} stories pass quality gate")
    print(f"  report: {REPORT_PATH.relative_to(ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
