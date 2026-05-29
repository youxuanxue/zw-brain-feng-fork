#!/usr/bin/env python3
"""check_acceptance_package.py — preflight 段 55

效果验收材料包（`docs/**/*acceptance-package*.md`）守卫（D37）。与 D35 决策签字
（段 53 查"数据真不真"）区分:本段查"**功能真跑过没**"——锚在 capture 脚本现场
跑出的证据产物上,杜绝 prose 里裸写"已验证 / 通过"。

  Layer 1 证据真实性：frontmatter.evidence 指向的 .json 必须存在 + 每条 check
      result=pass + git_sha 是当前 HEAD 的祖先（否则 WARN 陈旧/异线）；验收点表里
      每条引用的 evidence 标签必须在产物 checks 里找得到（声称必有产物背书）。
  Layer 2 结构：强制「验收范围」节；每条验收点必须挂 evidence 标签（禁裸"已验证"）；
      禁过程/估算数字（复用 D35 规则）。

dump 类外部依赖无关；证据产物缺失即 FAIL（验收必须有据,不降级 skip）。

Exit：0 = OK（含纯 WARN）；1 = FAIL。

Usage:
    ./scripts/check_acceptance_package.py [<path.md> ...] [--verbose]

接入：scripts/preflight.sh 段 55
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from signoff_lib import BANNED_NUMBER_PATTERNS, parse_tables, read_frontmatter

REPO = Path(__file__).resolve().parent.parent


def _is_ancestor(sha: str) -> bool:
    if not sha or sha == "unknown":
        return False
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"], cwd=REPO,
        capture_output=True,
    ).returncode == 0


def check_doc(path: Path, verbose: bool) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(REPO)
    fm = read_frontmatter(text)

    # ---- Layer 2: 强制节 ----
    if "验收范围" not in text:
        fails.append(f"{rel}: 缺「验收范围」强制节")

    # ---- Layer 2: 禁过程数字 ----
    for pat, desc in BANNED_NUMBER_PATTERNS:
        for m in pat.finditer(text):
            ln = text[: m.start()].count("\n") + 1
            fails.append(f"{rel}:{ln}: 禁用{desc} → 「{m.group(0).strip()}」")

    # ---- Layer 1: 证据产物 ----
    ev_rel = fm.get("evidence", "").strip()
    check_names: set[str] = set()
    if not ev_rel:
        fails.append(f"{rel}: frontmatter 缺 evidence（验收必须有据可查）")
    else:
        ev_path = REPO / ev_rel
        if not ev_path.exists():
            fails.append(f"{rel}: evidence 产物不存在 {ev_rel}（先跑 capture_acceptance_evidence.py）")
        else:
            try:
                data = json.loads(ev_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                fails.append(f"{rel}: evidence 产物非合法 JSON：{e}")
                data = {}
            checks = data.get("checks", [])
            check_names = {c.get("name", "") for c in checks}
            if not checks:
                fails.append(f"{rel}: evidence 产物无 checks")
            for c in checks:
                if c.get("result") != "pass":
                    fails.append(f"{rel}: evidence「{c.get('name')}」result={c.get('result')}（非 pass 不得验收）")
            sha = data.get("git_sha", "")
            if not _is_ancestor(sha):
                warns.append(f"{rel}: evidence git_sha={sha[:8]} 非当前 HEAD 祖先（可能陈旧/异线,建议重跑 capture）")

    # ---- Layer 1+2: 验收点表每条挂 evidence 标签 + 回链 ----
    for t in parse_tables(text):
        if "验收点" not in "".join(t["header"]):
            continue
        try:
            ei = next(i for i, h in enumerate(t["header"]) if "evidence" in h.lower() or "证据" in h)
        except StopIteration:
            fails.append(f"{rel}: 验收点表缺 evidence 列")
            continue
        for row in t["rows"]:
            if len(row) <= ei:
                continue
            cell = row[ei]
            tags = re.findall(r"`([^`]+)`", cell)
            point = re.sub(r"`[^`]*`", "", row[0])[:24] if row else ""
            if not tags:
                fails.append(f"{rel}: 验收点「{point}」未挂 evidence 标签（禁裸『已验证』）")
                continue
            if check_names:
                for tag in tags:
                    if tag not in check_names:
                        fails.append(f"{rel}: 验收点「{point}」evidence 标签 `{tag}` 在产物 checks 里查无（声称无背书）")

    return fails, warns


def discover() -> list[Path]:
    return sorted(
        p for p in REPO.glob("docs/**/*acceptance-package*.md")
        if "templates" not in p.parts
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="效果验收材料包守卫（D37 / 段 55）")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    targets = [Path(p).resolve() for p in args.paths] if args.paths else discover()
    if not targets:
        print("[acceptance-package] OK: 无验收材料包待检")
        return 0

    all_fails, all_warns = [], []
    for t in targets:
        f, w = check_doc(t, args.verbose)
        all_fails += f
        all_warns += w

    for w in all_warns:
        print(f"  [WARN] {w}")
    if all_fails:
        print(f"[acceptance-package] FAIL: {len(all_fails)} 项（扫 {len(targets)} 份）：")
        for f in all_fails:
            print(f"  {f}")
        return 1
    print(f"[acceptance-package] OK: {len(targets)} 份验收材料包通过（WARN {len(all_warns)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
