#!/usr/bin/env python3
"""
check_read_path_scan_to_one.py — preflight 段 32c

强约束（god's-eye 详情页 N+1 机械化）：
    读路径上「取**单条**实体」时，禁止 `repo.list_*(...)` 全表/全租户拉进内存后
    再用 Python `==` 逐行筛到一条。这类「scan-to-one」是 O(N) 每请求的 N+1，
    而仓储层通常已有 O(log N) 的索引 getter（`get_record` / `get_case` / `get_task`
    …，由 #191 引入「替代 next(...list_records()...) 全表扫」）。

    与 **段 32**（repo SQL 层 `select(HotModel).where(tenant-only)` 不分页）互补：
    段 32 拦「仓储把热表整张吐给调用方」；本段拦「调用方拿到 list 后 Python 筛到一条」。

两类被拦反模式（scope = handler / domain service 读路径）：
    (a) next-scan：
            next((x for x in <expr>.list_<name>(...) if x.<attr> == <id>), None)
        → 改为 <expr>.<indexed getter>(<id>, tenant_id=...)
    (b) loop-scan-to-one：
            for x in <expr>.list_<name>(...):
                if x.<attr> == <id>:
                    return / break ...
        → 改为索引 getter。
        注意：聚合循环（首句 `if ...: continue` 后继续收集多条）**不**算 scan-to-one，
        本检查只在 if 体含 `return` / `break` 时判定（取到一条即止 = 单实体查询语义）。

豁免：同行或上一行 `# scan-to-one-ok: <理由>`（禁裸豁免，必须给理由）。

引用：
    - 架构基线 §九（聚合是查询单位、读热点禁全量扫）
    - docs/preflight-debt.md「详情页 N+1」god's-eye 体检
    - 索引 getter：zw_brain/domain/repositories/{application,approval,delivery}.py

退出码：0 = PASS；1 = 违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (
    REPO / "zw_brain" / "command" / "handlers",
    REPO / "zw_brain" / "domain" / "services",
)
EXEMPT_MARKER = "# scan-to-one-ok:"


def _is_repo_receiver(value: ast.AST) -> bool:
    """receiver 链是否指向仓储层（有索引 getter 可替代）？

    只拦 repo 层 `list_*()`——`deps.repos.<x>` / `store.<x>_repo` / 名为 `repo`/`repository`
    的接收者，以及内联实例化 `XRepository().list_*()`（receiver 是 `*Repository` 构造调用）。
    视图门面（`deps.view.*.list_all()`，内存快照、无 getter）与 `brain.list_zones()`
    （有界引用集）不在范围，避免误报。
    """
    for sub in ast.walk(value):
        if isinstance(sub, ast.Name) and (
            sub.id in {"repo", "repository"} or sub.id.endswith("_repo") or sub.id.endswith("Repository")
        ):
            return True
        if isinstance(sub, ast.Attribute) and (
            sub.attr in {"repos", "repo", "repository"} or sub.attr.endswith("_repo") or sub.attr.endswith("Repository")
        ):
            return True
    return False


def _iter_is_list_call(node: ast.AST) -> bool:
    """node 是仓储层 `<repo>.list_<name>(...)` 调用？"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith("list_")
        and _is_repo_receiver(node.func.value)
    )


def _has_eq_compare(node: ast.AST | None) -> bool:
    """表达式子树里出现 `==` 比较？（区分 scan-to-one 与无条件遍历）"""
    if node is None:
        return False
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare) and any(isinstance(op, ast.Eq) for op in sub.ops):
            return True
    return False


def _exempt(lines: list[str], lineno: int) -> bool:
    same = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    prev = lines[lineno - 2] if 1 < lineno <= len(lines) + 1 else ""
    return EXEMPT_MARKER in same or EXEMPT_MARKER in prev


def _check_file(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:  # pragma: no cover - 语法错误另有 ruff 拦
        return [f"{path}: 解析失败 {exc}"]

    rel = path.relative_to(REPO)
    out: list[str] = []

    for node in ast.walk(tree):
        # (a) next-scan: next((x for x in <...>.list_*() if x.. == ..), default)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "next"
            and node.args
            and isinstance(node.args[0], ast.GeneratorExp)
        ):
            gen = node.args[0].generators[0] if node.args[0].generators else None
            if gen is not None and _iter_is_list_call(gen.iter) and any(_has_eq_compare(c) for c in gen.ifs):
                if not _exempt(lines, node.lineno):
                    out.append(
                        f"{rel}:{node.lineno}: scan-to-one（next 全表筛一条）— "
                        f"改用索引 getter（get_record/get_case/get_task…）或加 `{EXEMPT_MARKER} 理由`"
                    )

        # (b) loop-scan-to-one: for x in <...>.list_*(): if x.. == ..: return/break
        if isinstance(node, ast.For) and _iter_is_list_call(node.iter) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.If)
                and _has_eq_compare(first.test)
                and any(isinstance(s, (ast.Return, ast.Break)) for s in ast.walk(first))
            ):
                if not _exempt(lines, node.lineno):
                    out.append(
                        f"{rel}:{node.lineno}: scan-to-one（for 循环筛一条即 return/break）— "
                        f"改用索引 getter 或加 `{EXEMPT_MARKER} 理由`"
                    )
    return out


def main() -> int:
    violations: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            violations.extend(_check_file(path))

    if violations:
        print("段 32c read-path-scan-to-one FAIL — 详情页 N+1（list_*() 全表筛一条）：")
        for v in violations:
            print(f"  ✗ {v}")
        print(
            "\n修复：用仓储层索引 getter（get_record/get_case/get_task），"
            "或就地加 `# scan-to-one-ok: <理由>`（禁裸豁免）。"
        )
        return 1

    print("段 32c read-path-scan-to-one PASS（无 list_*() 全表筛一条反模式）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
