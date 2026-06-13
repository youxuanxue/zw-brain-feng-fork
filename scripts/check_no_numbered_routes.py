#!/usr/bin/env python3
"""check_no_numbered_routes.py — preflight 段 21（薄 shim → guard_lib 批量器）.

R-019⑤/R-020 库化：与段 19/20 同构守卫已迁到 ``check_grep_guards_batch.py`` 的
``no-numbered-routes`` GuardSpec（三段共享一次 git ls-files 枚举）。本文件保留为
独立可运行入口；逐字语义与 ALLOWED_FILES 见批量器中该段的常量定义。

强约束：前端 SPA 路由禁 IA 编号烙进 URL（``#/p<N>-...`` 反模式已整体退役）。

使用：
    ./scripts/check_no_numbered_routes.py
"""
from __future__ import annotations

import sys

from check_grep_guards_batch import run_section


def main() -> int:
    return run_section("no-numbered-routes")


if __name__ == "__main__":
    sys.exit(main())
