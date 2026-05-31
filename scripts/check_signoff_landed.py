#!/usr/bin/env python3
"""check_signoff_landed.py — preflight 段 54（D46 收敛为账本单源）

业务方 sign-off 落盘一致性守卫。**D46 起收敛**：签字唯一权威源 = `.testing/signoff/`
账本（append-only、来源无关）；本守卫不再对账 plan.yaml `[SIGNOFF-CLOSED]` + CLAUDE.md
D-编号三处副本（那是"靠守卫同步副本"的老味道，与段 58 同类，已随 D46 消除）。

收敛后规则：一份 sign-off 材料包（`docs/**/*business-review-package*.md` 或
`*acceptance-package*.md`）frontmatter 标 `status: approved` 时，其 `scope` 必须在
`.testing/signoff/<scope>.signoff.yaml` 有对应账本（单源落盘）。缺 → FAIL。

`.twin` 历史 `[SIGNOFF-CLOSED]` 行保留作执行归档，不再被任何守卫当事实源。
CLAUDE.md D-编号保留作决策史（D1–D46），不再作签字三角的一角。

Exit：0 = OK；1 = FAIL。
Usage: ./scripts/check_signoff_landed.py [--verbose]
接入：scripts/preflight.sh 段 54
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from signoff_lib import read_frontmatter

REPO = Path(__file__).resolve().parent.parent
SIGNOFF_DIR = REPO / ".testing" / "signoff"


def _ledger_scopes() -> set[str]:
    scopes: set[str] = set()
    if not SIGNOFF_DIR.is_dir():
        return scopes
    for fp in SIGNOFF_DIR.glob("*.signoff.yaml"):
        try:
            d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError):
            continue
        if str(d.get("scope", "")).strip():
            scopes.add(str(d["scope"]).strip())
    return scopes


def main() -> int:
    ap = argparse.ArgumentParser(description="sign-off 落盘一致性守卫（D35 / D46 段 54）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    docs = sorted({
        p for pat in ("*business-review-package*.md", "*acceptance-package*.md")
        for p in REPO.glob(f"docs/**/{pat}")
        if "templates" not in p.parts
    })
    ledger = _ledger_scopes()

    fails: list[str] = []
    checked = 0
    for doc in docs:
        fm = read_frontmatter(doc.read_text(encoding="utf-8"))
        if fm.get("status", "") != "approved":
            if args.verbose:
                print(f"  [skip] {doc.relative_to(REPO)} status={fm.get('status') or '无 frontmatter'}")
            continue
        checked += 1
        rel = doc.relative_to(REPO)
        scope = fm.get("scope", "").strip()
        if not scope:
            fails.append(f"{rel}: status=approved 但 frontmatter 缺 scope（无法定位账本）")
            continue
        if scope not in ledger:
            fails.append(
                f"{rel}: status=approved（scope={scope}）但 .testing/signoff/ 无对应账本 "
                f"{scope}.signoff.yaml（D46：签字唯一权威源是账本，请追加签字文件）"
            )

    if fails:
        print(f"[signoff-landed] FAIL: {len(fails)} 项（检 {checked} 份已签材料包）：")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"[signoff-landed] OK: {checked} 份已签材料包均在 .testing/signoff/ 账本落盘（单源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
