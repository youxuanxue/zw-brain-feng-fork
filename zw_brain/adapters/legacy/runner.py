"""Orchestrator for the legacy importer.

Phase-1 scope: parse-only stats + per-schema row counts. Mapper plumbing (governance,
catalog, exchange, …) is added in subsequent commits and registered into
`LegacyImportRunner.MAPPERS` without changing this file's public surface.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from zw_brain.adapters.legacy.parser import MysqldumpParser
from zw_brain.adapters.legacy.schema_index import dump_path_for, list_dumps
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT


@dataclass
class ParseStats:
    schema: str
    dump_path: Path
    table_row_counts: dict[str, int] = field(default_factory=dict)
    skipped_tables: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(self.table_row_counts.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "dump_path": str(self.dump_path),
            "tables": self.table_row_counts,
            "total_rows": self.total_rows,
            "skipped_tables": self.skipped_tables,
        }


def _cache_root() -> Path:
    override = os.environ.get("ZW_BRAIN_LEGACY_CACHE_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / ".legacy_cache"


class LegacyImportRunner:
    """Coordinates parse → cache → map → verify across schemas."""

    def __init__(self, *, tenant_id: str = DEFAULT_TENANT, cache_dir: Path | None = None):
        self.tenant_id = tenant_id
        self.cache_dir = (cache_dir or _cache_root()).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def mappers_for(self, schema: str) -> list[object]:
        """Return all mappers that should run on `schema`.

        Multiple mappers can subscribe to the same schema (e.g. dsp_catalog hosts both
        the catalog-metadata aggregate and the application/approval aggregate). Each
        mapper writes its own AdapterRunRecord and only handles its own subset of
        tables; other tables are reported in stats.skipped.
        """
        out: list[object] = []
        if schema == "dsp_bsp":
            from zw_brain.adapters.legacy.mappers.governance import GovernanceMapper

            out.append(GovernanceMapper(tenant_id=self.tenant_id))
        if schema in {"dsp_catalog", "dsp_metaresource"}:
            from zw_brain.adapters.legacy.mappers.catalog_metadata import CatalogMetadataMapper

            out.append(CatalogMetadataMapper(tenant_id=self.tenant_id))
        if schema in {"dsp_require", "dsp_catalog"}:
            from zw_brain.adapters.legacy.mappers.exchange import ExchangeMapper

            out.append(ExchangeMapper(tenant_id=self.tenant_id))
        if schema == "dsp_example":
            from zw_brain.adapters.legacy.mappers.topic_package import TopicPackageMapper

            out.append(TopicPackageMapper(tenant_id=self.tenant_id))
        if schema == "dsp_handling":
            from zw_brain.adapters.legacy.mappers.objection import ObjectionMapper

            out.append(ObjectionMapper(tenant_id=self.tenant_id))
        return out

    # Backwards-compat shim — returns the FIRST mapper, or None.
    def mapper_for(self, schema: str) -> object | None:
        mappers = self.mappers_for(schema)
        return mappers[0] if mappers else None

    def import_schema(self, schema: str) -> list[object] | object | None:
        """Run all mappers registered for `schema`.

        Returns a list of stats (one per mapper) when 2+ mappers exist; falls back to
        a single stats object when exactly one mapper handles the schema (preserves
        previous single-mapper callers). None when no mapper applies.
        """
        mappers = self.mappers_for(schema)
        if not mappers:
            return None
        path = dump_path_for(schema)
        results = [m.import_dump(path) for m in mappers]
        return results[0] if len(results) == 1 else results

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse_schema(self, schema: str) -> ParseStats:
        dump_path = dump_path_for(schema)
        parser = MysqldumpParser(dump_path)
        stats = ParseStats(schema=schema, dump_path=dump_path)
        for table, _row in parser.iter_rows():
            stats.table_row_counts[table] = stats.table_row_counts.get(table, 0) + 1
        # Tables defined in CREATE TABLE but with zero INSERTs become skipped (informational)
        for table in parser.columns_by_table:
            if table not in stats.table_row_counts:
                stats.skipped_tables.append(table)
        return stats

    def parse_all(self, schemas: Iterable[str] | None = None) -> dict[str, ParseStats]:
        targets = list(schemas) if schemas else sorted(list_dumps().keys())
        return {schema: self.parse_schema(schema) for schema in targets}

    def write_jsonl_cache(self, schema: str, *, max_rows_per_table: int | None = None) -> Path:
        """Stream rows from a single schema into per-table JSONL files under .legacy_cache/.

        File layout: `<cache_dir>/<schema>/<table>.jsonl` (one JSON object per line).
        Returns the schema directory path. Uses safe truncation when max_rows_per_table is set.
        """
        dump_path = dump_path_for(schema)
        out_dir = self.cache_dir / schema
        out_dir.mkdir(parents=True, exist_ok=True)
        # Open file handles lazily; avoids creating files for tables with zero rows.
        open_handles: dict[str, object] = {}
        row_counts: dict[str, int] = {}
        try:
            for table, row in MysqldumpParser(dump_path).iter_rows():
                if max_rows_per_table is not None and row_counts.get(table, 0) >= max_rows_per_table:
                    continue
                fh = open_handles.get(table)
                if fh is None:
                    fh = (out_dir / f"{table}.jsonl").open("w", encoding="utf-8")
                    open_handles[table] = fh
                fh.write(json.dumps(_make_jsonable(row), ensure_ascii=False))
                fh.write("\n")
                row_counts[table] = row_counts.get(table, 0) + 1
        finally:
            for fh in open_handles.values():
                fh.close()  # type: ignore[union-attr]
        return out_dir


def _make_jsonable(row: dict[str, object]) -> dict[str, object]:
    """Coerce non-JSON-serializable values (bytes from hex literals) into base16 strings."""
    out: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, bytes):
            out[key] = value.hex()
        else:
            out[key] = value
    return out
