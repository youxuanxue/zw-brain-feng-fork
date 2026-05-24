#!/usr/bin/env python3
# 三处一致性校验：DISPATCH_TABLE + handler 模块导出 + _CATEGORIZATION.md
#
# AST-parse 避免 importlib（dispatch 模块导入会拉满 sqlalchemy 等业务依赖，
# 与 preflight 轻量原则冲突）。三处任一不一致 → fail：
# 1. _CATEGORIZATION.md cap 集合 == DISPATCH_TABLE.keys()（无遗漏、无超额）
# 2. DISPATCH_TABLE 中每个 cap → handler module 名所在桶 与 _CATEGORIZATION.md 声明 bucket 一致
# 3. handler module 文件实际存在且 export 对应 handler fn 名

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATEGORIZATION = REPO_ROOT / "zw_brain" / "command" / "handlers" / "_CATEGORIZATION.md"
DISPATCH = REPO_ROOT / "zw_brain" / "command" / "dispatch.py"
HANDLERS_PKG = REPO_ROOT / "zw_brain" / "command" / "handlers"

_TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(j1|j2|b1|infra)\s*\|", re.MULTILINE)


def _parse_categorization() -> dict[str, str]:
    text = CATEGORIZATION.read_text()
    return {m.group(1): m.group(2) for m in _TABLE_ROW.finditer(text)}


def _parse_dispatch() -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Return (cap → (module_alias, fn_name)) and list of _PASSTHROUGH_CAPS.

    Handles both `x = ...` (Assign) and `x: T = ...` (AnnAssign) forms.
    """
    tree = ast.parse(DISPATCH.read_text())
    table: dict[str, tuple[str, str]] = {}
    passthrough_caps: list[str] = []

    def _consume(name: str, value: ast.AST) -> None:
        if name == "DISPATCH_TABLE" and isinstance(value, ast.Dict):
            for key, val in zip(value.keys, value.values, strict=True):
                if isinstance(key, ast.Constant) and isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                    table[key.value] = (val.value.id, val.attr)
        elif name == "_PASSTHROUGH_CAPS" and isinstance(value, ast.Tuple):
            for elt in value.elts:
                if isinstance(elt, ast.Constant):
                    passthrough_caps.append(elt.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _consume(target.id, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            _consume(node.target.id, node.value)
    return table, passthrough_caps


def _parse_imports() -> dict[str, str]:
    """Return alias → fully qualified module path from dispatch.py imports."""
    tree = ast.parse(DISPATCH.read_text())
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local_name = alias.asname or alias.name
                aliases[local_name] = f"{node.module}.{alias.name}"
    return aliases


def _bucket_from_module_path(module_path: str) -> str | None:
    for bucket in ("j1", "j2", "b1", "infra"):
        if f".handlers.{bucket}." in module_path:
            return bucket
    return None


def _handler_file_exports(module_path: str, fn_name: str) -> bool:
    parts = module_path.split(".")
    rel = Path(*parts).with_suffix(".py")
    file_path = REPO_ROOT / rel
    if not file_path.is_file():
        return False
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == fn_name for n in ast.walk(tree))


def main() -> int:
    if not CATEGORIZATION.is_file() or not DISPATCH.is_file():
        print("[capability-registration] skip: _CATEGORIZATION.md or dispatch.py not present")
        return 0
    cats = _parse_categorization()
    table_explicit, passthrough_caps = _parse_dispatch()
    aliases = _parse_imports()

    # _PASSTHROUGH_CAPS 注入 via DISPATCH_TABLE.update; 它们都 route 到 adapter_passthrough.handler
    for cap in passthrough_caps:
        if cap not in table_explicit:
            table_explicit[cap] = ("adapter_passthrough", "handler")

    errors: list[str] = []

    missing_in_table = set(cats) - set(table_explicit)
    if missing_in_table:
        errors.append(f"_CATEGORIZATION 列了 {len(missing_in_table)} cap 但 DISPATCH_TABLE 未注册：{sorted(missing_in_table)[:5]}")

    extra_in_table = set(table_explicit) - set(cats)
    if extra_in_table:
        errors.append(f"DISPATCH_TABLE 注册 {len(extra_in_table)} cap 但 _CATEGORIZATION 未列：{sorted(extra_in_table)[:5]}")

    bucket_mismatch: list[str] = []
    export_missing: list[str] = []
    for cap, declared_bucket in cats.items():
        if cap not in table_explicit:
            continue
        alias, fn = table_explicit[cap]
        module_path = aliases.get(alias)
        if module_path is None:
            bucket_mismatch.append(f"{cap}: DISPATCH_TABLE 用 alias `{alias}` 但 dispatch.py imports 未找到")
            continue
        actual_bucket = _bucket_from_module_path(module_path)
        if actual_bucket != declared_bucket:
            bucket_mismatch.append(f"{cap}: _CATEGORIZATION 声明 {declared_bucket} 但 handler 在 {actual_bucket}（{module_path}）")
        if not _handler_file_exports(module_path, fn):
            export_missing.append(f"{cap}: {module_path} 未 export 函数 `{fn}`")

    if bucket_mismatch:
        errors.append("bucket 不一致：\n  - " + "\n  - ".join(bucket_mismatch[:5]))
    if export_missing:
        errors.append("handler 函数缺失：\n  - " + "\n  - ".join(export_missing[:5]))

    if errors:
        print("[capability-registration] FAIL:")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"[capability-registration] OK: {len(cats)} cap × 3 处一致（_CATEGORIZATION.md + DISPATCH_TABLE + handler module export）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
