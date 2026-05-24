"""dsp_metaresource graphdb_* → LineageRelationProjectionRecord mapper (F3 turn 3 漏做补齐).

Step 9 (graph lineage branch) of the bridging chain. 元数据图谱（graphdb = 资源/字段
之间的多跳血缘关系）5 表映射到 LineageRelationProjectionRecord 主线，让
`MetaRelation` 的单表多对一血缘升级为多跳图血缘。

mapping 设计（5 表 → LineageRelationProjectionRecord + relation_rule_json 嵌入）:
  graphdb_relation         → 1 LineageRelationProjectionRecord
  graphdb_node             → 节点 metadata buffer → join 进 relation rule_json 的 nodes
  graphdb_node_column      → 节点 column metadata → join 进 relation rule_json.nodes[].columns
  graphdb_relation_attr    → 关系属性 → join 进 relation rule_json.attrs
  graphdb_relation_column  → 关系列绑定 → join 进 relation rule_json.columns

不复造表（基线 §1.3 forbidden zone）：etl_meta_* / es_index_* / file_meta_* /
database_manage_history —— 这些是数据治理任务运行细节，由集团数据治理中心统一。

Sensitive fields:
  - 图血缘是表/字段级元数据，不含真 secret / PII；无敏感字段处理。
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy._common import (
    ImportStats,
    coerce_time,
    finish_run,
    schema_from_dump_name,
)
from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT, legacy_system_for
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.domain.repositories.metadata_evidence import MetadataEvidenceRepository


class GraphLineageMapper:
    """Maps dsp_metaresource graphdb_* tables onto LineageRelationProjectionRecord.

    一个 graphdb_relation 行 → 一个 LineageRelationProjectionRecord，子表数据 join
    进 relation_rule_json 嵌入。parser 按 dump 顺序 yield row，所以 mapper 先 buffer
    全量行，再以 graphdb_relation 为主体重组装。
    """

    HANDLED_TABLES = {
        "graphdb_node",
        "graphdb_node_column",
        "graphdb_relation",
        "graphdb_relation_attr",
        "graphdb_relation_column",
    }
    ADAPTER_SLUG = "legacy.graph_lineage.import"

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT):
        self.tenant_id = tenant_id
        self.metadata_repo = MetadataEvidenceRepository()
        self.legacy_repo = LegacyObjectMappingRepository()
        self.adapter_repo = ExternalAdapterRepository()

    def import_dump(self, dump_path: Path) -> ImportStats:
        schema = schema_from_dump_name(dump_path.name)
        legacy_system = legacy_system_for(schema)
        stats = ImportStats(schema=schema, dump_path=dump_path)
        started_at = datetime.now(UTC)

        # Pass 1: buffer all rows
        buffers: dict[str, list[dict[str, Any]]] = {t: [] for t in self.HANDLED_TABLES}
        for table, row in MysqldumpParser(dump_path).iter_rows():
            if table not in self.HANDLED_TABLES:
                stats.skip(table)
                continue
            buffers[table].append(row)
            stats.bump_source(table)

        # Pass 2: index children by parent key
        nodes_by_id: dict[Any, dict[str, Any]] = {n.get("id"): n for n in buffers["graphdb_node"] if n.get("id")}
        columns_by_node = _group_by(buffers["graphdb_node_column"], "node_id")
        attrs_by_relation = _group_by(buffers["graphdb_relation_attr"], "relation_id")
        columns_by_relation = _group_by(buffers["graphdb_relation_column"], "relation_id")

        # Pass 3: write one LineageRelationProjectionRecord per graphdb_relation row
        for relation in buffers["graphdb_relation"]:
            try:
                self._import_one(
                    relation,
                    legacy_system=legacy_system,
                    nodes_by_id=nodes_by_id,
                    columns_by_node=columns_by_node,
                    attrs_by_relation=attrs_by_relation,
                    columns_by_relation=columns_by_relation,
                )
                stats.bump("graphdb_relation")
            except (KeyError, ValueError) as exc:
                stats.bump("graphdb_relation", "errors")
                key = f"graphdb_relation.error:{type(exc).__name__}"
                stats.skipped[key] = stats.skipped.get(key, 0) + 1

        # Bookkeeping: child rows attached count
        for table in ("graphdb_node", "graphdb_node_column", "graphdb_relation_attr", "graphdb_relation_column"):
            count = len(buffers[table])
            if count:
                stats.counts[f"{table}.buffered"] = count

        finish_run(
            self.adapter_repo,
            stats,
            adapter_slug=self.ADAPTER_SLUG,
            dump_path=dump_path,
            started_at=started_at,
            tenant_id=self.tenant_id,
        )
        return stats

    # ------------------------------------------------------------------
    # one-relation pipeline
    # ------------------------------------------------------------------

    def _import_one(
        self,
        relation: dict[str, Any],
        *,
        legacy_system: str,
        nodes_by_id: dict[Any, dict[str, Any]],
        columns_by_node: dict[Any, list[dict[str, Any]]],
        attrs_by_relation: dict[Any, list[dict[str, Any]]],
        columns_by_relation: dict[Any, list[dict[str, Any]]],
    ) -> None:
        raw_id = relation.get("id")
        # R-017 fail-closed: NULL id 不能 silent collision 进同一 record
        if raw_id is None or str(raw_id).strip() == "":
            raise ValueError("graphdb_relation row missing id")
        relation_id = str(raw_id)
        relation_ref = f"graphdb:{relation_id}"

        start_node = nodes_by_id.get(relation.get("start_node_id"), {})
        end_node = nodes_by_id.get(relation.get("end_node_id"), {})

        def _node_payload(node: dict[str, Any]) -> dict[str, Any]:
            if not node:
                return {}
            return {
                "node_id": node.get("id"),
                "node_name": node.get("node_name"),
                "node_name_cn": node.get("node_name_cn"),
                "node_desc": node.get("node_desc"),
                "database_id": node.get("database_id"),
                "meta_id": node.get("meta_id"),
                "source_table_meta_id": node.get("source_table_meta_id"),
                "source_database_meta_id": node.get("source_database_meta_id"),
                "status": node.get("status"),
                "columns": [
                    {
                        "id": col.get("id"),
                        "column_name": col.get("column_name"),
                        "column_name_en": col.get("column_name_en"),
                        "column_type": col.get("column_type"),
                        "source_column_meta_id": col.get("source_column_meta_id"),
                        "table_column_name": col.get("table_column_name"),
                        "order_id": col.get("order_id"),
                    }
                    for col in columns_by_node.get(node.get("id"), [])
                ],
            }

        attrs_payload = [
            {
                "id": a.get("id"),
                "relate_condition": a.get("relate_condition"),
                "start_node_code": a.get("start_node_code"),
                "start_node_name": a.get("start_node_name"),
                "relation_attr_operator": a.get("relation_attr_operator"),
                "end_node_code": a.get("end_node_code"),
                "end_node_name": a.get("end_node_name"),
            }
            for a in attrs_by_relation.get(raw_id, [])
        ]
        relation_columns_payload = [
            {
                "id": c.get("id"),
                "column_name": c.get("column_name"),
                "column_type": c.get("column_type"),
            }
            for c in columns_by_relation.get(raw_id, [])
        ]

        # 写 LineageRelationProjectionRecord —— 图血缘多跳关系
        source_resource_code = str(start_node.get("source_table_meta_id") or start_node.get("meta_id") or "") or None
        target_resource_code = str(end_node.get("source_table_meta_id") or end_node.get("meta_id") or "") or None

        self.metadata_repo.upsert_lineage_relation(
            {
                "relation_ref": relation_ref,
                "relation_scope": "graphdb",
                "source_resource_code": source_resource_code,
                "source_schema_ref": start_node.get("node_name") if start_node else None,
                "target_resource_code": target_resource_code,
                "target_schema_ref": end_node.get("node_name") if end_node else None,
                "relation_type": str(relation.get("relation_name") or "graphdb_relation"),
                "relation_rule_json": {
                    "relation_id": relation_id,
                    "relation_name": relation.get("relation_name"),
                    "database_id": relation.get("database_id"),
                    "relation_attr": relation.get("relation_attr"),
                    "node_columns": relation.get("node_columns"),
                    "status": relation.get("status"),
                    "create_time": coerce_time(relation.get("create_time")),
                    "publish_time": coerce_time(relation.get("publish_time")),
                    "start_node": _node_payload(start_node),
                    "end_node": _node_payload(end_node),
                    "attrs": attrs_payload,
                    "columns": relation_columns_payload,
                },
                "source_evidence_ref": f"{legacy_system}:graphdb_relation:{relation_id}",
                "source_ref": f"{legacy_system}:graphdb_relation:{relation_id}",
                "legacy_object_ref": relation_id,
            },
            tenant_id=self.tenant_id,
        )

        # legacy mapping for D4 审计可追溯 —— upsert_lineage_relation 内部已 upsert_legacy_mapping，
        # 此处不再重复 upsert（避免双重 mapping 行）。


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[Any, list[dict[str, Any]]]:
    out: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        k = row.get(key)
        if k is None:
            continue
        out.setdefault(k, []).append(row)
    return out
