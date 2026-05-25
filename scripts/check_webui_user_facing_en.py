#!/usr/bin/env python3
"""扫 zw-brain-web 页面模板：用户可见中文句子里不得夹带典型英文枚举/状态词。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "zw-brain-web" / "src" / "pages"

# 中文 UI 句子里不应出现的片段（技术 id 应放在 tech-id / 纯 ASCII 行）
BAD_IN_CN = (
    "denied 链",
    "denied链",
    "sha1:",
    "待 land",
    ">live<",
    "source-pill",
    "{{ packages.source.value }}",
    "{{ matrix.source.value }}",
    "{{ statistics.source.value }}",
)

# 整行仅英文枚举直出（无中文、在 template 文本节点）
BAD_PLAIN = re.compile(
    r">\s*(live|fixture|idle|loading|approved|in_delivery|denied)\s*<",
    re.IGNORECASE,
)


def main() -> int:
    errors: list[str] = []
    for path in sorted(PAGES.glob("*.vue")):
        text = path.read_text(encoding="utf-8")
        for bad in BAD_IN_CN:
            if bad in text:
                errors.append(f"{path.relative_to(ROOT)}: contains {bad!r}")
        for i, line in enumerate(text.splitlines(), 1):
            if BAD_PLAIN.search(line) and "tech-id" not in line:
                errors.append(f"{path.relative_to(ROOT)}:{i}: plain enum in template")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("[OK] user-facing EN leak scan: zw-brain-web/src/pages/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
