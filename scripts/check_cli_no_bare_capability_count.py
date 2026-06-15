#!/usr/bin/env python3
"""check_cli_no_bare_capability_count.py — preflight 段 69（D2 契约一致性硬化）

CLI 自报能力数曾以裸字面量「159 capability」写死在 ``zw_brain/entry/cli/main.py``
的 module docstring / argparse ``description`` / ``--list`` epilog 里——而同文件
``cmd_list`` 运行时 ``print len(commands)`` 实测 180、``commands.generated.json`` 由
``scripts/export_agent_contract.py`` 现算。两数对不上 = 文档撒谎，且无机械防线阻止
回潮（对比鲜明：同文件「200 manifest」用了 ``<!-- stat:... -->`` 守卫块）。

本守卫（**可机械化项**，承 CLAUDE.md「可机械化边界」原则——计数对账是纯正则查表，
不是语义判断）：扫 ``zw_brain/entry/cli/main.py`` 全文，禁止出现裸的能力计数字面量
（``\\d+`` 紧跟 ``capabilit`` / ``command``），除非该数字被 ``<!-- stat:... -->`` 块包裹
（stat 块有 ``sync-stats --check`` 单独守新鲜度，是合法的「现算并对账」写法）。

落点收敛在 CLI entry 文件：能力总数由 ``--list`` 输出行尾现算呈现、由
``export_agent_contract`` 派生，docstring/帮助文本不得再硬编码副本。

退出码：
    0 = 无裸能力计数（或被 stat 块包裹）
    1 = 检出未被 stat 包裹的裸能力计数字面量
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "zw_brain" / "entry" / "cli" / "main.py"

# 裸能力计数：一个数字紧跟（可有一个空格）「capabilit(y/ies)」或「command(s)」。
# 用词义锚定到「能力/命令」总数语境，避免误伤 exit-code 数字（"unknown skill = 2"）
# 或端口号等无关数字。
_BARE_COUNT = re.compile(r"\b\d+\s*(?:capabilit(?:y|ies)|commands?)\b", re.IGNORECASE)

# stat 包裹块：``<!-- stat:NAME -->数字<!-- /stat -->`` —— 合法「现算并对账」写法，
# 由 sync-stats --check 单独守新鲜度，本守卫放行。先把这些区段从文本里抠掉再扫。
_STAT_BLOCK = re.compile(r"<!--\s*stat:[^>]*-->.*?<!--\s*/stat\s*-->", re.DOTALL)


def main() -> int:
    if not TARGET.exists():
        sys.stderr.write(f"[cli-bare-count] target missing: {TARGET}\n")
        return 1
    text = TARGET.read_text(encoding="utf-8")
    stripped = _STAT_BLOCK.sub("", text)

    hits = []
    for lineno, line in enumerate(stripped.splitlines(), start=1):
        for m in _BARE_COUNT.finditer(line):
            hits.append((lineno, m.group(0), line.strip()))

    if hits:
        sys.stderr.write(
            "[cli-bare-count] FAIL: zw_brain/entry/cli/main.py 含裸能力计数字面量"
            "（会随注册表漂移撒谎）。删裸数字 → 由 --list 输出现算 / export_agent_contract 派生，"
            "或用 <!-- stat:... -->N<!-- /stat --> 包裹并注册 sync-stats：\n"
        )
        for lineno, frag, line in hits:
            sys.stderr.write(f"  line {lineno}: {frag!r}  in: {line}\n")
        return 1

    print("[cli-bare-count] ok: CLI docstring/帮助文本无裸能力计数（capability 数现算呈现）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
