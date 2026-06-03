#!/usr/bin/env python3
"""check_d_index_entry_size.py — preflight 段 68（D-编号索引防再膨胀）.

把 CLAUDE.md「## 决策记录」段头自有契约硬化：每条 D-编号 = 日期 + scope + 一句裁决
（+ 被全仓引用的子决策锚点速记）+ 全文指针；**prose essay 不进索引**。CLAUDE.md 每
会话整份入上下文，膨胀=持续烧 token，且历史上 D46–D49 一路长成 1–2 千字小作文、违背
段头自己定的格式（2026-06-03 收口回锚点速记，见 #202）。本守卫把"靠自觉"的格式规则
变成机械门禁，防再膨胀。

判据：决策记录段内每条 D-条目行（`- Dxx …`）字符数 ≤ MAX_CHARS。
- 当前保锚点后最长 = D46（7 个子锚点）756 字符；被剪掉的 essay ≥ 1015 字符。
- MAX_CHARS=900 落在 756→1015 的空档：给真锚点丰富的条目 ~150 字符（~2 锚点）headroom，
  又远低于任何 essay。超限 → FAIL，提示把 Why/How 移到 docs/decisions/* 全文、索引只留锚点。

Exit 0 = 全部条目合规；1 = 至少一条超限。
接入：scripts/preflight.sh 段 68。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO / "CLAUDE.md"

MAX_CHARS = 900
# 决策记录段起始锚（只在此段内查 D-条目，避免误伤别处引用 Dxx 的行）。
SECTION_ANCHOR = "## 决策记录"
# D-条目行：行首 `- D<数字>` 后接空格 / 全角冒号 / `[`（覆盖 `- D46 [..]` 与 `- D1：` 两种历史格式）。
ENTRY_RE = re.compile(r"^- (D\d+)[ ：\[]")


def main() -> int:
    if not CLAUDE_MD.is_file():
        print(f"[d-index-size] skip: {CLAUDE_MD} 不存在", file=sys.stderr)
        return 0

    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == SECTION_ANCHOR)
    except StopIteration:
        print(f"[d-index-size] skip: 未找到「{SECTION_ANCHOR}」段", file=sys.stderr)
        return 0

    violations: list[tuple[str, int]] = []
    for ln in lines[start:]:
        m = ENTRY_RE.match(ln)
        if m and len(ln) > MAX_CHARS:
            violations.append((m.group(1), len(ln)))

    if violations:
        print(
            f"[d-index-size] FAIL：{len(violations)} 条 D-索引条目超长（> {MAX_CHARS} 字符）——"
            "索引膨胀回潮，违背段头「一句裁决 + 锚点 + 指针、prose essay 不进索引」契约：",
            file=sys.stderr,
        )
        for d, n in violations:
            print(f"  - {d}: {n} 字符", file=sys.stderr)
        print(
            "\n修复：把该条的 Why/How 移到外部全文（docs/decisions/* / docs/acceptance/* /"
            " feature Landing-Note），索引仅留日期+scope+一句裁决 + 被引用的子决策锚点(如 D46.g)"
            "速记 + 全文指针。参照 #202 收口 D46–D49 的做法。",
            file=sys.stderr,
        )
        return 1

    n_entries = sum(1 for ln in lines[start:] if ENTRY_RE.match(ln))
    print(f"[d-index-size] OK：{n_entries} 条 D-索引条目均 ≤ {MAX_CHARS} 字符（无 essay 回潮）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
