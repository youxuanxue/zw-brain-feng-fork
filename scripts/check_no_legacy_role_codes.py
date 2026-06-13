#!/usr/bin/env python3
"""check_no_legacy_role_codes.py — preflight 段 19（薄 shim → guard_lib 批量器）.

R-019⑤/R-020 库化：本守卫与段 20/21 同构（grep 一遍全树 + 行级豁免），已迁到
``check_grep_guards_batch.py`` 的 ``no-legacy-role-codes`` GuardSpec，三段共享一次
``git ls-files`` 文件枚举。本文件保留为独立可运行入口（doc 引用 / 单段调试），
逐字语义与豁免清单见批量器中该段的常量定义。

强约束（D23 retrofit）：R1-R8 用户角色码已退役；仓库内不得出现 r1-r8 / R1-R8
独立 token 字面值（豁免见批量器 LEGACY_ALLOWED_FILES / LEGACY_ALLOWED_LINE_MARKERS）。

使用：
    ./scripts/check_no_legacy_role_codes.py
"""
from __future__ import annotations

import sys

from check_grep_guards_batch import run_section


def main() -> int:
    return run_section("no-legacy-role-codes")


if __name__ == "__main__":
    sys.exit(main())
