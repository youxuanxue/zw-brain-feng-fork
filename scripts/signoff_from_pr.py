#!/usr/bin/env python3
"""signoff_from_pr.py — PR 合并时把签字落账进 .testing/signoff/（D46.d）.

「GitHub 是录入口，账本是真相」：业务方在 PR 上签字（label `signoff:<scope>` +
PR body 的 `<!-- signoff ... -->` 机读块），合并时 GitHub Action 调本脚本，把签字事实
**落成 .testing/signoff/<scope>.signoff.yaml 提交回 main**。此后状态函数 `signed()`
永远只读仓库账本（离线可验、进 git 历史、append-only）；GitHub 只在合并那刻用一次。

签字三要素的权威来源：
  - signed_by = PR 的 approvers（GitHub 权威记录"谁批的"）
  - date      = merged_at（GitHub 权威记录"何时合的"）
  - evidence  = PR url/number（可回溯）
  - scope/kind/covers = PR body 的 `<!-- signoff ... -->` YAML 块（作者声明、approver 审过）

可机械化逻辑全在本脚本（dev-rules：workflow 只编排，脚本承载判断），故可单元测试。
idempotent：账本文件已存在则不覆盖（append-only——一个 scope 签一次；重签=新 scope）。

Usage:
    # CI 内：把 GitHub event payload 关键字段拼成 JSON 传入
    ./scripts/signoff_from_pr.py --event /tmp/pr-event.json [--out-dir .testing/signoff] [--check]

event JSON 形如（Action 从 github 上下文组装）：
    {"number": 175, "merged": true, "merged_at": "2026-05-30T12:00:00Z",
     "html_url": "https://github.com/.../pull/175",
     "labels": ["signoff:e3.F9"], "approvers": ["alice", "bob"], "body": "...<!-- signoff\n...\n-->..."}

Exit：0 = 写出/已存在跳过/未触发；1 = 非法（缺块、scope 不符、schema 不全）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / ".testing" / "signoff"
KINDS = {"决策签字", "效果验收", "双签"}

# PR body 内的机读签字块：<!-- signoff ... --> 之间是 YAML（scope/kind/covers/decision_only）
SIGNOFF_BLOCK_RE = re.compile(r"<!--\s*signoff\s*\n(.*?)\n\s*-->", re.DOTALL | re.IGNORECASE)
LABEL_SCOPE_RE = re.compile(r"^signoff:(.+)$")


def parse_block(body: str) -> dict | None:
    """从 PR body 抽 <!-- signoff ... --> 块，解析为 dict；无块返回 None。"""
    m = SIGNOFF_BLOCK_RE.search(body or "")
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None


def scope_from_labels(labels: list[str]) -> str | None:
    for lab in labels or []:
        if m := LABEL_SCOPE_RE.match(str(lab).strip()):
            return m.group(1).strip()
    return None


def build_signoff(event: dict) -> tuple[str, dict] | None:
    """从 PR event 组装 (scope, signoff_dict)；非法/未触发返回 None（含原因打印）。"""
    if not event.get("merged"):
        print("[signoff-from-pr] skip: PR 未合并")
        return None
    scope = scope_from_labels(event.get("labels") or [])
    if not scope:
        print("[signoff-from-pr] skip: 无 signoff:<scope> label，非签字 PR")
        return None
    block = parse_block(event.get("body") or "")
    if block is None:
        print(f"[signoff-from-pr] FAIL: label signoff:{scope} 但 PR body 缺 <!-- signoff ... --> 机读块")
        return None
    if str(block.get("scope", "")).strip() != scope:
        print(f"[signoff-from-pr] FAIL: label scope={scope} 与 body scope={block.get('scope')} 不符")
        return None
    kind = str(block.get("kind", "")).strip()
    if kind not in KINDS:
        print(f"[signoff-from-pr] FAIL: kind='{kind}' 不在 {sorted(KINDS)}")
        return None
    decision_only = bool(block.get("decision_only", False))
    covers = block.get("covers") or []
    if not isinstance(covers, list):
        print("[signoff-from-pr] FAIL: covers 必须是 list")
        return None
    if decision_only and covers:
        print("[signoff-from-pr] FAIL: decision_only=true 但 covers 非空")
        return None
    if not decision_only and not covers:
        print("[signoff-from-pr] FAIL: decision_only=false 但 covers 为空（须列被签 feature）")
        return None
    approvers = event.get("approvers") or []
    signed_by = " + ".join(approvers) if approvers else "（PR approver 未取到）"
    date = str(event.get("merged_at", ""))[:10]
    pr = event.get("number")
    url = event.get("html_url", f"PR #{pr}")
    signoff = {
        "scope": scope,
        "signed_by": signed_by,
        "date": date,
        "kind": kind,
        "evidence": f"PR #{pr} {url}（merge 自动落账 D46.d）",
        "decision_only": decision_only,
        "covers": [str(c).strip() for c in covers],
    }
    return scope, signoff


def main() -> int:
    ap = argparse.ArgumentParser(description="PR 合并签字落账（D46.d）")
    ap.add_argument("--event", required=True, help="PR event 关键字段 JSON 文件")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--check", action="store_true", help="只解析校验，不写文件")
    args = ap.parse_args()

    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[signoff-from-pr] FAIL: 读 event 失败 {e}")
        return 1

    built = build_signoff(event)
    if built is None:
        # 未触发（未合并/无 label）= 0；非法已在 build 内打印 FAIL —— 用 sentinel 区分
        return 1 if (event.get("merged") and scope_from_labels(event.get("labels") or [])) else 0

    scope, signoff = built
    out = Path(args.out_dir) / f"{scope}.signoff.yaml"
    if out.exists():
        print(f"[signoff-from-pr] skip: {out} 已存在（append-only，scope 已签过，不覆盖）")
        return 0
    if args.check:
        print(f"[signoff-from-pr] OK (check): 将写 {out} covers={len(signoff['covers'])}")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(signoff, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[signoff-from-pr] wrote {out} — scope={scope} kind={signoff['kind']} "
          f"covers={len(signoff['covers'])} signed_by={signoff['signed_by']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
