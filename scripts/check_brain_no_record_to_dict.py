#!/usr/bin/env python3
"""check_brain_no_record_to_dict.py — preflight invariant for Phase 1.1.

Pure ``record → dict`` mappers must live in ``zw_brain/command/serializers/``,
not on BrainService. Once a ``_X_record_to_dict`` migrates into
``serializers/<aggregate>.py``, re-introducing it on BrainService (out of
muscle memory or copy-paste) would silently bring back the god-object surface.

Allowed exceptions:
- ``_topic_package_detail_to_dict`` — aggregate view that orchestrates the
  topic_package repo; not a pure record-to-dict mapper.

退出码：0 = PASS；1 = 违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRAIN_PY = REPO / "zw_brain" / "command" / "brain.py"

ALLOWED = {"_topic_package_detail_to_dict"}


def _is_record_to_dict_method(node: ast.AST) -> bool:
    """class 内 method 名以 _to_dict 结尾 + 首参为 self + 不在白名单。"""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if not (node.name.endswith("_record_to_dict") or node.name.endswith("_to_dict")):
        return False
    if node.name in ALLOWED:
        return False
    args = node.args.args
    return bool(args) and args[0].arg == "self"


def main() -> int:
    source = BRAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(BRAIN_PY))

    # 单次走树：只看 ClassDef 直接 body 里的方法（包内嵌套 class 也覆盖，
    # 这里 BrainService 是顶级，body 一层就够）。
    flagged: list[tuple[int, str]] = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for member in cls.body:
            if _is_record_to_dict_method(member):
                flagged.append((member.lineno, member.name))

    if flagged:
        print(
            f"[brain-no-record-to-dict] FAIL: BrainService 不应再持有 record_to_dict 方法 "
            f"({len(flagged)} violation(s)):"
        )
        for lineno, name in flagged:
            print(f"  zw_brain/command/brain.py:{lineno}: {name}")
        print()
        print("  policy: 纯 record → dict 映射必须住在 zw_brain/command/serializers/<aggregate>.py")
        print("  fix: 把方法体迁到对应 serializer 模块，按签名 def <name>_to_dict(item) -> dict")
        print(f"  exempt: {sorted(ALLOWED)}")
        return 1

    print(
        f"[brain-no-record-to-dict] OK: BrainService 无 record_to_dict 残留 "
        f"(exempt: {sorted(ALLOWED)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
