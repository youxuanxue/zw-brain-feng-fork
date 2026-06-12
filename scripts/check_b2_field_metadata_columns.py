#!/usr/bin/env python3
"""check_b2_field_metadata_columns — debt predicate for B2 field-metadata 10-col gap.

现算依据（不需 live DB，纯源码静态检查，确定性）：字段级元数据的实际承载处 =
注册写端键字典 `FIELD_METADATA_SNAPSHOT_KEYS`（zw_brain/command/handlers/j1/resource_mount.py，
方案 A：逐列落 ResourceSchemaSnapshotRecord.schema_json，与 legacy 导入快照同源同形）。
锚点迁移记录：原扫 `ResourceSchemaMappingRecord` 类块（记债时的假定承载处）；2026-06-12
b2-field-metadata-10col 提前本期落地后，按债 yaml 自述口径（「锚点宽松……下期实现可用
不同命名，只要承载语义即关债」）把扫描锚点指向实际承载常量块——属账本维护，非绕守卫。

predicate `field_metadata_debt_open()`:
  True  (debt OPEN)  ⇔ 承载的字段级元数据维度数 < 10
  False (stale-fixed) ⇔ 已覆盖 ≥10 个字段级元数据维度（自动关债）

判定方法：解析键字典常量块，对 10 类字段级元数据各给一组同义锚点（列名/语义关键字），
命中即记一类。锚点是宽松的（任意同义命中即算），避免要求精确列名。关债后本脚本被
tests/test_resource_mount.py 引用作回潮守卫（10 列承载缩水即红）。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CARRIER = REPO_ROOT / "zw_brain" / "command" / "handlers" / "j1" / "resource_mount.py"
CONSTANT_NAME = "FIELD_METADATA_SNAPSHOT_KEYS"

# 10 类字段级元数据，每类一组同义锚点（小写匹配常量块文本）。命中任一即认为该类已承载。
FIELD_METADATA_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "field_name": ("name_en", "field_name", "column_name", "name_cn"),
    # 注：用字段级专名 `catalog_item_id`（对标 dc_resource_table_column 的「目录信息项」列）+
    # 同义 `info_item`，不用宽松的 `catalog_item` / `item_code`（映射级键子串假阳，见记债期注）。
    "catalog_item": ("catalog_item_id", "info_item"),
    # `format` 是 legacy db_meta_column 快照及读端 normalizeSchemaColumns 的字段类型承载键，
    # 属债 yaml「同义命中即关债」口径内的合法同义锚点。
    "field_type": ("field_type", "data_type", "col_type", "format"),
    "length_precision": ("length", "precision", "col_size", "size"),
    "primary_key": ("is_pk", "pk_flag", "is_primary"),
    "nullable": ("is_null", "is_nullable", "allow_null"),
    "update_pk": ("is_up_id", "update_pk", "update_primary", "up_id"),
    "update_time": ("is_up_time", "update_time_flag", "up_time", "update_flag"),
    "data_standard": ("data_standard", "standard_column", "std_column", "meta_standard"),
    "data_dict": ("data_dict", "dict_code", "code_table", "dictionary"),
}


def _constant_block(source: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*(?::[^=]+)?=\s*\((.*?)\)", source, re.S)
    return m.group(1) if m else ""


def covered_dimension_count() -> int:
    if not CARRIER.exists():
        return 0
    block = _constant_block(CARRIER.read_text(encoding="utf-8"), CONSTANT_NAME).lower()
    if not block:
        return 0
    count = 0
    for anchors in FIELD_METADATA_DIMENSIONS.values():
        if any(a in block for a in anchors):
            count += 1
    return count


def field_metadata_debt_open() -> bool:
    """True ⇔ fewer than 10 field-level metadata dimensions are carried (debt open)."""
    return covered_dimension_count() < 10


if __name__ == "__main__":
    n = covered_dimension_count()
    print(f"[b2-field-metadata] {CONSTANT_NAME} 承载字段级元数据维度 {n}/10 → debt {'OPEN' if field_metadata_debt_open() else 'stale-fixed'}")
