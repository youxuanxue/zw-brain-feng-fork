#!/usr/bin/env python3
"""check_signoff_landed.py — preflight 段 54

业务方 sign-off 落盘一致性守卫（D35）。关掉 F9 §5.3 自陈的「C/D 靠人记忆」债：

当一份 sign-off 材料包（`docs/**/*business-review-package*.md`）frontmatter 标
`status: approved` 时，意味着业务方已签字，则其落盘三角必须齐全：

  A（evidence）：某 `.twin/**/plan.yaml` 有 `[SIGNOFF-CLOSED ...] ... <scope>` 行
  C（决策）：CLAUDE.md 有提及该 scope 的 D-编号决策

缺任一 → FAIL。B（PR label）是 GitHub 侧开关，离线不可验，由 promote_signoff.py 消费，不在此校验。

Exit：0 = OK；1 = FAIL。

Usage:
    ./scripts/check_signoff_landed.py [--verbose]

接入：scripts/preflight.sh 段 54
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO / "CLAUDE.md"


def _frontmatter(text: str) -> dict:
    """解析文首 --- ... --- 之间的简单 key: value。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip()
    return fm


def _plan_yaml_texts() -> str:
    raw = "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in REPO.glob(".twin/**/plan.yaml")
    )
    # YAML 折叠标量跨多行——把列表项内的续行（非 '- ' 开头的缩进行）并回单逻辑行，
    # 这样 [SIGNOFF-CLOSED ...] 与同一条 evidence 里的 scope 落在同一行可被匹配。
    return re.sub(r"\n(?!\s*-\s)[ \t]+", " ", raw)


def main() -> int:
    ap = argparse.ArgumentParser(description="sign-off 落盘一致性守卫（D35 / 段 54）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    docs = [
        p for p in REPO.glob("docs/**/*business-review-package*.md")
        if "templates" not in p.parts
    ]
    plan_text = _plan_yaml_texts()
    claude_text = CLAUDE_MD.read_text(encoding="utf-8") if CLAUDE_MD.exists() else ""

    fails: list[str] = []
    checked = 0
    for doc in sorted(docs):
        fm = _frontmatter(doc.read_text(encoding="utf-8"))
        status = fm.get("status", "")
        if status != "approved":
            if args.verbose:
                print(f"  [skip] {doc.relative_to(REPO)} status={status or '无 frontmatter'}（未落盘，段 53 管内容）")
            continue
        checked += 1
        rel = doc.relative_to(REPO)
        scope = fm.get("scope", "").strip()
        if not scope:
            fails.append(f"{rel}: status=approved 但 frontmatter 缺 scope（无法校验落盘三角）")
            continue
        # A: plan.yaml SIGNOFF-CLOSED evidence
        if not re.search(r"\[SIGNOFF-CLOSED[^\]]*\][^\n]*" + re.escape(scope), plan_text):
            fails.append(f"{rel}: status=approved（scope={scope}）但 .twin/**/plan.yaml 无匹配 [SIGNOFF-CLOSED ... {scope}] evidence（落盘 A 缺）")
        # C: CLAUDE.md D-编号
        if scope not in claude_text:
            fails.append(f"{rel}: status=approved（scope={scope}）但 CLAUDE.md 无提及 {scope} 的 D-编号决策（落盘 C 缺）")

    if fails:
        print(f"[signoff-landed] FAIL: {len(fails)} 项（检 {checked} 份已签材料包）：")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"[signoff-landed] OK: {checked} 份已签材料包落盘三角齐全")
    return 0


if __name__ == "__main__":
    sys.exit(main())
