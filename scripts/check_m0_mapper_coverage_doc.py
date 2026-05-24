#!/usr/bin/env python3
# docs/deployment/m0-mapper-coverage.md mapper 表数 ↔ 实际 HANDLED_TABLES 机械化交叉校验。
# Triggered after PR #88 review: 文档手维护 mapper count drift 与代码（4 处 off-by-one）。
# 本检查 parse 文档中形如 "<mapper_name>.py HANDLED_TABLES = N 表" 或 "<mapper>（N <bucket>）" 的 count claim，
# 与各 mapper.HANDLED_TABLES 集合 cardinality 对比。任一不一致 → fail。

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "deployment" / "m0-mapper-coverage.md"
MAPPERS_DIR = REPO_ROOT / "zw_brain" / "adapters" / "legacy" / "mappers"

# 文档中典型 claim 模式：
#   - "connect（44 dc_* 表）" — §1 矩阵行
#   - "objection（8 data_objection_* 表）" — §1 矩阵行
#   - "ObjectionMapper 8 表" — §2 章节标题
#   - "governance.py HANDLED_TABLES = 23 表" — §2.5 paragraph
#   - "catalog_metadata（24 表）" — §1 矩阵行
#   - "projections.MonitorMapper HANDLED_TABLES = 8 表" — §2.9 paragraph
# 提取规则：找形如 "<word>（<digit>+ ... 表）" 或 "<word>.py HANDLED_TABLES = <digit>+ 表" 的整数
# mapper 名 → HANDLED_TABLES 实际通过 AST 读取（避免拉依赖）。

_CLAIM_PATTERNS = [
    # "connect.py HANDLED_TABLES = 44 表" 或 "governance.py HANDLED_TABLES = 23 表"
    re.compile(r"`?(?P<name>[a-z_]+)\.py`?\s+HANDLED_TABLES\s*=\s*(?P<n>\d+)\s*表"),
    # "ConnectMapper 全覆盖" 不含数字；跳过
    # "catalog_metadata（24 表）" / "connect（44 dc_* 表）" / "objection（8 data_objection_* 表）"
    # 紧跟 mapper 名后是「（数字 ... 表）」
    re.compile(r"\b(?P<name>catalog_metadata|connect|exchange|governance|objection|pipelines|service|topic_package)（(?P<n>\d+)[^）]*表"),
    # "ObjectionMapper 8 表" — §2 章节标题（仅这种唯一指代 mapper 的形式）
    re.compile(r"\b(?P<cls>[A-Z][a-zA-Z]*Mapper)\s+(?P<n>\d+)\s*表"),
    # "projections.MonitorMapper HANDLED_TABLES = 8 表"
    re.compile(r"`?projections\.(?P<cls>[A-Z][a-zA-Z]*Mapper)`?\s+HANDLED_TABLES\s*=\s*(?P<n>\d+)\s*表"),
]

_MAPPER_FILE_TO_CLASS = {
    "catalog_metadata": "CatalogMetadataMapper",
    "connect": "ConnectMapper",
    "exchange": "ExchangeMapper",
    "governance": "GovernanceMapper",
    "objection": "ObjectionMapper",
    "pipelines": "PipelinesMapper",
    "projections.MonitorMapper": "MonitorMapper",
    "projections.PerformMapper": "PerformMapper",
    "service": "ServiceMapper",
    "topic_package": "TopicPackageMapper",
}


def _parse_mapper_handled_tables() -> dict[str, int]:
    """Read each mapper .py via AST and extract HANDLED_TABLES cardinality.

    Supports:
      - HANDLED_TABLES = {"a", "b", ...}  (Set literal)
      - HANDLED_TABLES = set(_TABLE_CONFIG.keys())  → counts _TABLE_CONFIG dict literal in same file
    """
    import ast

    counts: dict[str, int] = {}
    for py in MAPPERS_DIR.glob("*.py"):
        if py.name.startswith("__"):
            continue
        source = py.read_text()
        tree = ast.parse(source)

        module_dict_sizes: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                        module_dict_sizes[target.id] = len(node.value.keys)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and isinstance(node.value, ast.Dict):
                module_dict_sizes[node.target.id] = len(node.value.keys)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if not isinstance(stmt, ast.Assign):
                        continue
                    for target in stmt.targets:
                        if not (isinstance(target, ast.Name) and target.id == "HANDLED_TABLES"):
                            continue
                        value = stmt.value
                        if isinstance(value, ast.Set):
                            counts[f"{py.stem}.{node.name}"] = len(value.elts)
                        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "set":
                            if value.args and isinstance(value.args[0], (ast.Set, ast.List, ast.Tuple)):
                                counts[f"{py.stem}.{node.name}"] = len(value.args[0].elts)
                            elif value.args and isinstance(value.args[0], ast.Call):
                                # set(X.keys()) — look up X.keys()
                                call = value.args[0]
                                if isinstance(call.func, ast.Attribute) and call.func.attr == "keys" and isinstance(call.func.value, ast.Name):
                                    src_name = call.func.value.id
                                    if src_name in module_dict_sizes:
                                        counts[f"{py.stem}.{node.name}"] = module_dict_sizes[src_name]
    return counts


def _resolve_mapper_key(name: str | None, cls: str | None) -> str | None:
    """Map a doc claim ref (file stem or class name) to internal counts key (`<stem>.<ClassName>`)."""
    counts_keys = list(_handled_table_counts.keys())
    if cls:
        for k in counts_keys:
            if k.endswith(f".{cls}"):
                return k
    if name:
        for k in counts_keys:
            stem, klass = k.split(".", 1)
            if stem == name:
                return k
    return None


_handled_table_counts: dict[str, int] = {}


def main() -> int:
    global _handled_table_counts
    if not DOC.is_file():
        print(f"[m0-mapper-doc] skip: {DOC} not present")
        return 0
    _handled_table_counts = _parse_mapper_handled_tables()
    if not _handled_table_counts:
        print(f"[m0-mapper-doc] skip: no mappers under {MAPPERS_DIR}")
        return 0

    text = DOC.read_text()
    claims: list[tuple[str, int, str, int]] = []  # (mapper_key, claimed_n, doc_line_context, actual_n)
    for pattern in _CLAIM_PATTERNS:
        for m in pattern.finditer(text):
            name = m.groupdict().get("name")
            cls = m.groupdict().get("cls")
            n_str = m.group("n")
            try:
                n = int(n_str)
            except ValueError:
                continue
            key = _resolve_mapper_key(name, cls)
            if key is None:
                continue
            actual = _handled_table_counts.get(key)
            if actual is None:
                continue
            # Snippet for error context
            line_start = max(0, text.rfind("\n", 0, m.start()) + 1)
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            snippet = text[line_start:line_end][:120]
            claims.append((key, n, snippet, actual))

    if not claims:
        print(f"[m0-mapper-doc] skip: no countable mapper claims parsed from {DOC.name}")
        return 0

    drifts = [(k, n, s, a) for k, n, s, a in claims if n != a]
    if drifts:
        print(f"[m0-mapper-doc] FAIL: {len(drifts)}/{len(claims)} mapper count claim drifted vs actual HANDLED_TABLES")
        for k, n, s, a in drifts[:10]:
            print(f"  - {k}: doc claims {n} but actual {a}")
            print(f"    ↳ {s}")
        return 1

    print(f"[m0-mapper-doc] OK: {len(claims)} mapper count claim 与 HANDLED_TABLES 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
