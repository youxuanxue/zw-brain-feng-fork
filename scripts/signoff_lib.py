"""signoff_lib.py — sign-off 检查器族共享工具（D37 抽取）

被 check_signoff_package.py（段 53）/ check_signoff_landed.py（段 54）/
check_acceptance_package.py（段 55）共用。原先三处各自复制 `BANNED_NUMBER_PATTERNS`
/ `read_frontmatter` / `parse_tables`,改一处忘另一处必漂移（Jobs 重复维护）——统一到此。

注：检查器以 `python3 scripts/check_*.py` 调用,scripts/ 即 sys.path[0],故 `import signoff_lib` 直接可达。
"""
from __future__ import annotations

import re

# 过程/估算数字（漂移 + 逼读者心算,且不改变决策）——禁。决策签字与验收签字共用同一纪律。
BANNED_NUMBER_PATTERNS = [
    (re.compile(r"\d+\s*分钟"), "会议/过程时长（N 分钟）"),
    (re.compile(r"(?<![A-Za-z])\d+\s*min(?![A-Za-z])"), "过程时长（N min）"),
    (re.compile(r"\d+\s*[-–~]\s*\d+\s*(?:天|工作日|人天|worker)"), "估算工期（N-M 天/worker）"),
    (re.compile(r"\d+\s*[-–]?\s*\d*\s*worker[··•]?day", re.IGNORECASE), "worker·day 估算"),
    (re.compile(r"(?<![\w>])\d+\s*态(?!\s*-->)"), "未 stat-wrap 的状态计数（N 态）"),
]


def read_frontmatter(text: str) -> dict:
    """解析文首 --- ... --- 之间的简单 key: value。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip()
    return fm


def parse_tables(text: str) -> list[dict]:
    """提取 markdown 表：返回 [{header:[...], rows:[[cells...]]}]。"""
    tables: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cur is None:
                cur = {"header": cells, "rows": []}
            elif re.fullmatch(r"[:\-\s|]+", line.strip().strip("|").replace("|", "")):
                continue  # 分隔行
            elif set("".join(cells)) <= set(":- "):
                continue
            else:
                cur["rows"].append(cells)
        elif cur is not None:
            tables.append(cur)
            cur = None
    if cur is not None:
        tables.append(cur)
    return tables
