#!/usr/bin/env python3
"""check_signoff_ledger.py — preflight 段 63

签字账本守卫（D46）：`.testing/signoff/` 是 SIGN-OFF 唯一权威源，本守卫保证它机读、不可伪。
每个 `<scope>.signoff.yaml` 必须：
  - 必填字段：scope / signed_by / date / kind / evidence（evidence 非空，禁手写空签）
  - kind ∈ {决策签字, 效果验收, 双签}
  - covers 是 list；每个 covers 路径必须 .feature 且文件存在（防悬空签字）
  - decision_only=true 时 covers 必须为空；false（或缺省）时 covers 至少 1 项
append-only 由 git review 兜底（本守卫不强制不可改，避免离线无法判定历史）。

Exit：0 = OK/skip；1 = 任一账本非法
Usage: ./scripts/check_signoff_ledger.py [--verbose]
接入：scripts/preflight.sh 段 63
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SIGNOFF_DIR = REPO / ".testing" / "signoff"
REQUIRED = ("scope", "signed_by", "date", "kind", "evidence")
KINDS = {"决策签字", "效果验收", "双签"}


def main() -> int:
    ap = argparse.ArgumentParser(description="签字账本守卫（段 63 / D46）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not SIGNOFF_DIR.is_dir():
        print("[signoff-ledger] skip: 无 .testing/signoff/")
        return 0

    files = sorted(SIGNOFF_DIR.glob("*.signoff.yaml"))
    fails: list[str] = []
    feature_signed = 0
    for fp in files:
        rel = fp.relative_to(REPO).as_posix()
        try:
            d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as e:
            fails.append(f"{rel}: 解析失败 {e}")
            continue
        for k in REQUIRED:
            if not str(d.get(k, "")).strip():
                fails.append(f"{rel}: 缺必填字段 {k}（禁手写空签）")
        if d.get("kind") not in KINDS:
            fails.append(f"{rel}: kind='{d.get('kind')}' 不在 {sorted(KINDS)}")
        covers = d.get("covers") or []
        if not isinstance(covers, list):
            fails.append(f"{rel}: covers 必须是 list")
            covers = []
        decision_only = bool(d.get("decision_only", False))
        if decision_only and covers:
            fails.append(f"{rel}: decision_only=true 但 covers 非空（纯决策签字不该挂 feature）")
        if not decision_only and not covers:
            fails.append(f"{rel}: decision_only=false 但 covers 为空（须列被签 feature，或标 decision_only:true）")
        for c in covers:
            cs = str(c).strip()
            if not cs.endswith(".feature"):
                fails.append(f"{rel}: covers '{cs}' 非 .feature 路径")
            elif not (REPO / cs).is_file():
                fails.append(f"{rel}: covers '{cs}' 文件不存在（悬空签字）")
            else:
                feature_signed += 1

    if fails:
        print(f"[signoff-ledger] FAIL: 检 {len(files)} 份账本，{len(fails)} 项：")
        for f in fails:
            print(f"  {f}")
        return 1
    print(f"[signoff-ledger] OK: {len(files)} 份签字账本合法（{feature_signed} 个 feature 签字覆盖）")
    if args.verbose:
        print(f"  dir: {SIGNOFF_DIR.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
