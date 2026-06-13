#!/usr/bin/env python3
"""check_no_retired_features.py — preflight 段 20（薄 shim → guard_lib 批量器）.

R-019⑤/R-020 库化：与段 19/21 同构守卫已迁到 ``check_grep_guards_batch.py`` 的
``no-retired-features`` GuardSpec（三段共享一次 git ls-files 枚举）。本文件保留为
独立可运行入口；逐字语义、退役 token 正则、ALLOWED_FILES / ALLOWED_LINE_MARKERS
见批量器中该段的常量定义。

强约束：K12 dashboard 退役（D15 二次反转）+ alembic 删除（D23 二次升级）相关
token 不得回潮。

使用：
    ./scripts/check_no_retired_features.py
"""
from __future__ import annotations

import sys

from check_grep_guards_batch import run_section


def main() -> int:
    return run_section("no-retired-features")


if __name__ == "__main__":
    sys.exit(main())
