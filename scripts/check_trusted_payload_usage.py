#!/usr/bin/env python3
# F6 防回潮：tests/ 内除 _trusted_payload.py 自身外，不允许 brain.invoke_skill 直接调用
# 必须走 invoke_trusted（走 build_trusted_skill_payload 信任哨兵路径，与生产 BFF 一致）。
# 触发事件：PR #79 类哨兵序列化 bug — 集成测试 bypass trust-stamp 导致与生产路径分歧。

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"

# 允许例外文件
_ALLOWLIST = {
    "_trusted_payload.py",  # helper 自身需 import build_trusted_skill_payload
    "test_trusted_session_context.py",  # 信任哨兵不变量测试本身就是负向测试
}

# 实际 call 的 pattern（排除 docstring / 注释引用）
# 形态: `brain.invoke_skill(` 出现在非注释非字符串行
_CALL_PATTERN = re.compile(r"brain\.invoke_skill\(")


def _is_in_comment_or_docstring(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''") or stripped.startswith('"') or stripped.startswith("'")


def main() -> int:
    if not TESTS_DIR.is_dir():
        print(f"[trusted-payload-usage] skip: {TESTS_DIR} not present")
        return 0

    violations: list[tuple[Path, int, str]] = []
    for py in TESTS_DIR.rglob("*.py"):
        if py.name in _ALLOWLIST or "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for idx, line in enumerate(text.splitlines(), 1):
            if not _CALL_PATTERN.search(line):
                continue
            if _is_in_comment_or_docstring(line):
                continue
            violations.append((py.relative_to(REPO_ROOT), idx, line.strip()[:120]))

    if violations:
        print(f"[trusted-payload-usage] FAIL: {len(violations)} 处 brain.invoke_skill 直接调用 bypass trust-stamp")
        print("  集成测试 mutate skill 必须走 tests/_trusted_payload.invoke_trusted（PR #79 类 bug 回归护栏）")
        for path, line_no, snippet in violations[:10]:
            print(f"  - {path}:{line_no}: {snippet}")
        if len(violations) > 10:
            print(f"  ... 共 {len(violations)} 处")
        return 1

    print("[trusted-payload-usage] OK: tests/ 内全部 mutate skill 调用走 invoke_trusted (PR #79 类回归护栏生效)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
