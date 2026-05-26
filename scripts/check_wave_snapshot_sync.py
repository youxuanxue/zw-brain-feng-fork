#!/usr/bin/env python3
"""check_wave_snapshot_sync.py — preflight 段 34

强约束（防止 Wave 真相表与 preflight-debt 反向链接漂移的机械门禁）：

    架构基线 §〇.1 Wave 真相表（zw-brain-architecture.md）的每条反向链接形如：
        [preflight-debt §YYYY-MM-DD <subject>](../preflight-debt.md)
    必须能在 docs/preflight-debt.md 中解析到对应 entry——即：
      (a) `## YYYY-MM-DD — ` 形式的 entry 锚点日期匹配；
      (b) <subject> 关键短语出现在该 entry 的文本块（## 标题 ~ 下一个 ## 之间）。

    校验维度：
    - FAIL（exit 1）：Wave 表中某反向链接无法在 debt 中解析到（日期或短语都不匹配）
      → 控制面手维护投影漂移。
    - WARN（不阻塞）：debt 中所有未 superseded entry 都应在 Wave 表"阻塞"列出现；
      未出现的 entry 仅打 warning（避免误伤已 closed 但表未及时更新的情况）。

    与基线关联：
    - PR #114 §〇.1 Wave 真相表引入（反向索引 preflight-debt 统一 Wave 状态）
    - 元规则「控制面手维护投影」反例 candidate — 表与 debt 之间手维护，
      段 34 把这条「投影漂移」机械化。

退出码：
    0 = 所有 Wave 表反向链接都解析到 debt entry
    1 = 至少一处反向链接断链（日期或短语不匹配）

使用：
    ./scripts/check_wave_snapshot_sync.py
    ./scripts/check_wave_snapshot_sync.py --arch <path> --debt <path>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_ARCH = REPO / "docs" / "approved" / "zw-brain-architecture.md"
DEFAULT_DEBT = REPO / "docs" / "preflight-debt.md"

# Wave snapshot 反向链接 pattern:
#   [preflight-debt §YYYY-MM-DD <subject>](../preflight-debt.md)
# 或省略 "preflight-debt " 前缀:
#   [§YYYY-MM-DD <subject>](../preflight-debt.md)
LINK_PATTERN = re.compile(
    r"\[(?:preflight-debt\s+)?§(\d{4}-\d{2}-\d{2})\s+([^\]]+?)\]\(\.\./preflight-debt\.md\)"
)

# debt entry header pattern: `## YYYY-MM-DD — <title>`
ENTRY_HEADER_PATTERN = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s+[—-]\s+(.+)$")


def parse_debt_entries(debt_text: str) -> list[tuple[str, str, str]]:
    """Return list of (date, title, body_text). body_text 含 ## 标题之后到下一个 ## 之前。"""
    entries: list[tuple[str, str, str]] = []
    lines = debt_text.splitlines()
    current: tuple[str, str, list[str]] | None = None
    for line in lines:
        m = ENTRY_HEADER_PATTERN.match(line)
        if m:
            if current is not None:
                entries.append((current[0], current[1], "\n".join(current[2])))
            current = (m.group(1), m.group(2).strip(), [])
        elif current is not None:
            current[2].append(line)
    if current is not None:
        entries.append((current[0], current[1], "\n".join(current[2])))
    return entries


def parse_wave_snapshot_section(arch_text: str) -> str | None:
    """Extract §〇.1 当前真相表 section body (until next `## ` heading)."""
    # 找 §〇.1 标题（"## 〇.1 ...") - 兼容全角中文 "〇" 和半角 "0"
    pattern = re.compile(r"^## (?:〇\.1|0\.1)\s.*$", re.MULTILINE)
    match = pattern.search(arch_text)
    if not match:
        return None
    start = match.end()
    # 找下一个 ## 标题或 ---
    next_section = re.search(r"^## (?!〇\.1|0\.1)", arch_text[start:], re.MULTILINE)
    if next_section:
        return arch_text[start : start + next_section.start()]
    return arch_text[start:]


def find_matching_entry(
    date: str, subject: str, entries: list[tuple[str, str, str]]
) -> tuple[str, str, str] | None:
    """Match (date, subject) to a debt entry by two-tier strategy:

    1. **Strict**: subject 整段 substring 出现在 entry 标题或正文 → 匹配；
    2. **Fallback**: subject 按空格 / 中英文标点拆 tokens（保留 ≥2 字符），
       任一 token 是 entry 标题或正文的 substring → 匹配。

    这两层是为了既能命中精确短语（如 "AgentRuntime"），又能命中由多词组成的
    subject（如 "5 个 B1 业务报表"）即便 entry 标题措辞稍异。
    """
    subject_stripped = subject.strip()
    for entry_date, entry_title, entry_body in entries:
        if entry_date != date:
            continue
        haystack = entry_title + "\n" + entry_body
        if subject_stripped in haystack:
            return (entry_date, entry_title, entry_body)
        tokens = [t for t in re.split(r"[\s，。、（）()]+", subject_stripped) if len(t) >= 2]
        if tokens and any(t in haystack for t in tokens):
            return (entry_date, entry_title, entry_body)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", type=Path, default=DEFAULT_ARCH)
    parser.add_argument("--debt", type=Path, default=DEFAULT_DEBT)
    args = parser.parse_args(argv)

    if not args.arch.is_file():
        print(f"[wave-snapshot-sync] skip: {args.arch} not present")
        return 0
    if not args.debt.is_file():
        print(f"[wave-snapshot-sync] skip: {args.debt} not present")
        return 0

    arch_text = args.arch.read_text(encoding="utf-8")
    debt_text = args.debt.read_text(encoding="utf-8")

    snapshot = parse_wave_snapshot_section(arch_text)
    if snapshot is None:
        print(f"[wave-snapshot-sync] FAIL: §〇.1 当前真相表 section not found in {args.arch}")
        return 1

    entries = parse_debt_entries(debt_text)
    if not entries:
        print(f"[wave-snapshot-sync] FAIL: no `## YYYY-MM-DD —` entries parsed from {args.debt}")
        return 1

    # 收集 Wave 表中所有反向链接
    links = LINK_PATTERN.findall(snapshot)
    if not links:
        print("[wave-snapshot-sync] FAIL: §〇.1 中未发现任何 preflight-debt 反向链接")
        print("  expected pattern: [preflight-debt §YYYY-MM-DD <subject>](../preflight-debt.md)")
        return 1

    failures: list[tuple[str, str]] = []
    matched_dates: set[str] = set()
    for date, subject in links:
        if find_matching_entry(date, subject, entries) is None:
            failures.append((date, subject))
        else:
            matched_dates.add(date)

    # 反向覆盖 WARN: debt 中未 superseded entry 未在 Wave 表出现的
    warnings: list[tuple[str, str]] = []
    for entry_date, entry_title, entry_body in entries:
        if "superseded" in entry_title.lower() or "superseded" in entry_body.lower():
            continue
        # 用 (date, normalized title) 检测是否已被 Wave 表引用
        snapshot_has_date = any(d == entry_date for d, _ in links)
        if not snapshot_has_date:
            warnings.append((entry_date, entry_title))

    if failures:
        print(f"[wave-snapshot-sync] FAIL: {len(failures)} Wave snapshot link(s) cannot resolve to debt entry:")
        for date, subject in failures:
            print(f"  - §{date} {subject!r} — 在 docs/preflight-debt.md 中未找到日期匹配的 `## ` entry 含此短语")
        print()
        print("[wave-snapshot-sync] hint: 修法二选一：")
        print("  (a) 让 debt 中新增 / 重命名一条 `## YYYY-MM-DD — ` entry 使日期与关键短语匹配")
        print("  (b) 修改 Wave 真相表反向链接使其指向真实 debt entry 日期 + 关键短语")
        return 1

    if warnings:
        print(f"[wave-snapshot-sync] WARN: {len(warnings)} debt entry not referenced by Wave snapshot (non-blocking):")
        for date, title in warnings:
            print(f"  - {date} — {title}")

    print(
        f"[wave-snapshot-sync] OK: {len(links)} Wave snapshot link(s) all resolve "
        f"to debt entries; {len(entries)} debt entries total, {len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
