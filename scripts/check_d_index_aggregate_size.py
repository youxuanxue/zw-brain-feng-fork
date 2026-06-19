#!/usr/bin/env python3
"""check_d_index_aggregate_size.py — preflight 段 72（D-索引聚合上限·净零策展棘轮）.

段 68 ``check_d_index_entry_size.py`` 只限**单条** D-条目 ≤900 字符，**对总量无上限**。
而「## 决策记录」段聚合已 ~1.7 万字符、D1→D61 一路只增不减，且 **CLAUDE.md 每会话整份入
上下文**——索引膨胀=持续稀释/烧 token（CLAUDE.md §6 净零压力、§5 靠自觉的问题须硬化）。
本守卫给该段加一道**聚合字符棘轮**：上限 = 当前实测聚合值（登记为常量），判据 `聚合 > 上限
→ FAIL`，当前态 `== 上限` 算通过。

语义 = **净零策展**：想加一条新 D 条目，得先把等量老条目归档/收口腾出字符（如把已上线、
point-in-time 的条目翻成结论删掉、或把 essay 收回锚点），聚合不许净增长。这与段 68 互补——
段 68 防单条长成 essay，本段防条目数无限堆积。

**段边界与 check_d_index_entry_size.py 完全一致**：同 ``SECTION_ANCHOR = "## 决策记录"``，
从该锚行（含）到文件末为聚合区间（照搬那个脚本的边界逻辑，保证两守卫口径一致、不漂移）。

**本守卫绝不编辑 CLAUDE.md**，只量 + 棘轮比较。OK 时报「当前 X 字符 / 上限 Y」。
要上调上限须人工改 MAX_AGGREGATE_CHARS 常量（= 一次显式的「我决定让索引再长一点」决策，
不许自动放水）。

Exit 0 = 聚合 ≤ 上限；1 = 聚合超限。``--show`` 只打印当前聚合值不做判定（便于校准）。
接入：scripts/preflight.sh 段 72。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO / "CLAUDE.md"

# 聚合字符上限（棘轮）。= 实测「## 决策记录」段（含锚行到 EOF）聚合字符数。
# 净零策展：加新 D 条目须先归档等量老条目，此值不许靠累积 D 条目悄悄上调；
# 要放宽须人工显式改这里（一次「让索引再长一点」的决策），并在 commit message 说明缘由。
# [2026-06-19] 17527→18361：上游 #303（D62 iam-role-governance，已签 GATE）合法新增一条 D-条目
# 入 main 决策段（净增 834），属上游签字决策的合理增长，棘轮随之上调到 post-#303 实值；本 PR（D63
# 供数详情路由）自身的 CLAUDE.md 索引行仍按 D63 §六 deferred、不在此计入。
MAX_AGGREGATE_CHARS = 18361

# 段边界锚——与 check_d_index_entry_size.py 完全一致（照搬，保两守卫口径同源不漂移）。
SECTION_ANCHOR = "## 决策记录"


def _aggregate_chars() -> int | None:
    """量「## 决策记录」段（锚行含→EOF）聚合字符数；段缺失/文件缺失返回 None。"""
    if not CLAUDE_MD.is_file():
        return None
    lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == SECTION_ANCHOR)
    except StopIteration:
        return None
    # 与 splitlines 逆操作一致：行间以单个 \n 复原（不含文件末尾换行），口径稳定可复算。
    return len("\n".join(lines[start:]))


def main(argv: list[str]) -> int:
    agg = _aggregate_chars()
    if agg is None:
        print(
            f"[d-index-aggregate] skip: {CLAUDE_MD} 不存在或未找到「{SECTION_ANCHOR}」段",
            file=sys.stderr,
        )
        return 0

    if "--show" in argv:
        print(f"[d-index-aggregate] 当前聚合 = {agg} 字符（上限 {MAX_AGGREGATE_CHARS}）")
        return 0

    if agg > MAX_AGGREGATE_CHARS:
        print(
            f"[d-index-aggregate] FAIL：「{SECTION_ANCHOR}」段聚合 {agg} 字符 > 上限 "
            f"{MAX_AGGREGATE_CHARS}（净增 {agg - MAX_AGGREGATE_CHARS}）——D-索引只增不减回潮，"
            "违背 CLAUDE.md §6 净零策展。",
            file=sys.stderr,
        )
        print(
            "\n修复（净零）：加新 D 条目前先归档等量老条目腾字符——把已上线/point-in-time 的条目"
            "翻成一句结论或删、把残留 essay 收回锚点+全文指针（参照 #202 收口 D46–D49）。"
            "确需上调上限，则人工显式改 MAX_AGGREGATE_CHARS 常量并在 commit message 说明缘由"
            "（一次「让索引再长一点」的决策，不许靠累积悄悄放水）。",
            file=sys.stderr,
        )
        return 1

    print(
        f"[d-index-aggregate] OK：「{SECTION_ANCHOR}」段聚合 {agg} 字符 ≤ 上限 "
        f"{MAX_AGGREGATE_CHARS}（headroom {MAX_AGGREGATE_CHARS - agg}）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
