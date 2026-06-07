#!/usr/bin/env python3
"""check_b2_field_metadata_columns — debt predicate for B2 field-metadata 10-col gap.

现算依据（不需 live DB，纯源码静态检查，确定性）：zw-brain 的库表资源字段挂接由
`ResourceSchemaMappingRecord`（zw_brain/domain/models.py）承载。当前它只携带 `source_schema_ref`
（源字段引用）+ `mapping_rule_json`（映射规则）≈ 源字段→目标字段 2 列映射，**不承载字段级元数据
10 列**（对标旧 `dc_resource_table_column`：字段名 / 目录信息项 / 字段类型 / 长度精度 / 主键 /
可空 / 更新主键 / 更新时间 / 数据标准 / 数据字典）。

predicate `field_metadata_debt_open()`:
  True  (debt OPEN)  ⇔ ResourceSchemaMappingRecord 承载的字段级元数据列数 < 10
  False (stale-fixed) ⇔ 模型已覆盖 ≥10 个字段级元数据列（下期补齐后自动关债）

判定方法：解析模型类块，对 10 类字段级元数据各给一组同义锚点（列名/语义关键字），命中即记一类。
锚点是宽松的（任意同义命中即算），避免要求精确列名——下期实现可用不同命名，只要承载该语义即关债。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS = REPO_ROOT / "zw_brain" / "domain" / "models.py"
CLASS_NAME = "ResourceSchemaMappingRecord"

# 10 类字段级元数据，每类一组同义锚点（小写匹配类块文本）。命中任一即认为该类已承载。
FIELD_METADATA_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "field_name": ("name_en", "field_name", "column_name", "name_cn"),
    # 注：用字段级专名 `catalog_item_id`（对标 dc_resource_table_column 的「目录信息项」列）+ 同义
    # `info_item`，**不**用宽松的 `catalog_item` / `item_code`——后者会子串命中 ResourceSchemaMapping
    # 自身**映射级**的 `catalog_item_code`（标识整条映射归属哪个目录项，非逐字段元数据），造成永久假阳，
    # 与本债叙述「不承载字段级 10 列元数据」（=0 承载）相矛盾。
    "catalog_item": ("catalog_item_id", "info_item"),
    "field_type": ("field_type", "data_type", "col_type", "\"type\"", "_type"),
    "length_precision": ("length", "precision", "col_size", "size"),
    # 注：避开 SQLAlchemy DDL 关键字 primary_key=/nullable= 的假阳——这里要的是「被映射字段
    # 是否主键 / 是否可空」这一**业务元数据列**，不是 ORM 列定义关键字。
    "primary_key": ("is_pk", "pk_flag", "is_primary"),
    "nullable": ("is_null", "is_nullable", "allow_null"),
    "update_pk": ("is_up_id", "update_pk", "update_primary", "up_id"),
    "update_time": ("is_up_time", "update_time_flag", "up_time", "update_flag"),
    "data_standard": ("data_standard", "standard_column", "std_column", "meta_standard"),
    "data_dict": ("data_dict", "dict_code", "code_table", "dictionary"),
}


def _class_block(source: str, class_name: str) -> str:
    m = re.search(rf"class {re.escape(class_name)}\(Base\):(.*?)(?:\nclass |\Z)", source, re.S)
    return m.group(1) if m else ""


def covered_dimension_count() -> int:
    if not MODELS.exists():
        return 0
    block = _class_block(MODELS.read_text(encoding="utf-8"), CLASS_NAME).lower()
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
    print(f"[b2-field-metadata] {CLASS_NAME} 承载字段级元数据维度 {n}/10 → debt {'OPEN' if field_metadata_debt_open() else 'stale-fixed'}")
