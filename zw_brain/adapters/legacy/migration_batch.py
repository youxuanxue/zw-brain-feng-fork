from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy.runner import LegacyImportRunner
from zw_brain.adapters.legacy.schema_index import list_dump_candidates, list_dumps
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT
from zw_brain.adapters.legacy.verification import verify_legacy_migration
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.shared.db import ensure_parent_dir
from zw_brain.shared.migrate import ensure_runtime_schema, reset_and_upgrade

CUSTOMER_CORE_V1_SCHEMAS = ("dsp_bsp", "dsp_catalog", "dsp_metaresource", "dsp_require", "dsp_handling", "dsp_example")
PROFILE_SCHEMAS = {"customer-core-v1": CUSTOMER_CORE_V1_SCHEMAS}


@dataclass(frozen=True)
class MigrationOptions:
    dumps_dir: Path
    db_path: Path | None = None
    tenant_id: str = DEFAULT_TENANT
    profile: str = "customer-core-v1"
    reset_db: bool = False
    strict: bool = False
    require_zero_conflicts: bool = False
    dry_run: bool = False


class MigrationError(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(json.dumps(report, ensure_ascii=False))


def run_migration(options: MigrationOptions) -> dict[str, Any]:
    if options.profile not in PROFILE_SCHEMAS:
        report = _base_report(options) | {"status": "failed", "errors": [f"unknown profile: {options.profile}"]}
        raise MigrationError(report)
    if options.db_path is not None:
        os.environ["ZW_BRAIN_DB_PATH"] = str(options.db_path)
    os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"] = str(options.dumps_dir)
    schemas = list(PROFILE_SCHEMAS[options.profile])
    report = _base_report(options)
    report["schemas"] = schemas
    report["dumps"] = _dump_report(schemas)
    missing = [schema for schema, info in report["dumps"].items() if not info.get("present")]
    duplicates = [schema for schema, info in report["dumps"].items() if len(info.get("candidates", [])) > 1]
    if missing and options.strict:
        report["status"] = "failed"
        report["errors"].append(f"missing required dump(s): {', '.join(missing)}")
        raise MigrationError(report)
    if duplicates and options.strict:
        report["status"] = "failed"
        report["errors"].append(f"duplicate required dump(s): {', '.join(duplicates)}")
        raise MigrationError(report)

    if not options.dry_run:
        ensure_parent_dir()
        if options.reset_db:
            reset_and_upgrade()
        else:
            ensure_runtime_schema()

    runner = LegacyImportRunner(tenant_id=options.tenant_id)
    imports: list[dict[str, Any]] = []
    for schema in schemas:
        handled_tables = _handled_tables_for_schema(runner, schema)
        if schema in missing:
            imports.append({"schema": schema, "status": "skipped", "reason": "missing_dump", "handled_tables": handled_tables})
            continue
        try:
            result = runner.import_schema(schema, dry_run=True) if options.dry_run else runner.import_schema(schema)
        except Exception as exc:  # noqa: BLE001
            imports.append({"schema": schema, "status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})
            report["errors"].append(f"import failed for {schema}: {exc}")
            if options.strict:
                break
            continue
        stats_list = result if isinstance(result, list) else [result]
        imports.append(
            {
                "schema": schema,
                "status": "succeeded" if result is not None else "no_mapper",
                "handled_tables": handled_tables,
                "mappers": [item.to_dict() if hasattr(item, "to_dict") else item for item in stats_list if item is not None],
            }
        )
    report["imports"] = imports
    report["adapter_runs"] = [] if options.dry_run else _adapter_run_report(options.tenant_id)
    report["table_accounting"] = _table_accounting(report["dumps"], imports)
    report["verification"] = {"skipped": True, "reason": "dry_run_no_db_writes"} if options.dry_run else verify_legacy_migration(
        tenant_id=options.tenant_id,
        require_zero_conflicts=options.require_zero_conflicts,
    )
    failed_imports = [item for item in imports if item["status"] not in {"succeeded", "skipped"}]
    failed_runs = [item for item in report["adapter_runs"] if item["status"] not in {"succeeded", "replayed"}]
    mapper_errors = _mapper_errors(imports)
    dump_parse_errors = [schema for schema, info in report["dumps"].items() if info.get("parse_error")]
    unaccounted_tables = [item for item in report["table_accounting"] if item["unaccounted_rows"] > 0]
    unmapped_tables = [item for item in report["table_accounting"] if not item["declared"] and item["source_rows"] > 0]
    if failed_imports:
        report["errors"].append(f"failed import(s): {', '.join(item['schema'] for item in failed_imports)}")
    if failed_runs:
        report["errors"].append(f"failed adapter run(s): {len(failed_runs)}")
    if mapper_errors:
        report["errors"].append(f"mapper error row(s): {mapper_errors}")
    if dump_parse_errors:
        report["errors"].append(f"dump parse error(s): {', '.join(dump_parse_errors)}")
    if unmapped_tables:
        table_refs = ", ".join(f"{item['schema']}.{item['table']}" for item in unmapped_tables[:10])
        report["errors"].append(f"unmapped source row table(s): {table_refs}")
    if unaccounted_tables:
        table_refs = ", ".join(f"{item['schema']}.{item['table']}" for item in unaccounted_tables[:10])
        report["errors"].append(f"unaccounted source row table(s): {table_refs}")
    if report["verification"].get("failed"):
        report["errors"].append("legacy mapping verification failed")
    if options.strict and report["errors"]:
        report["status"] = "failed"
        raise MigrationError(report)
    report["status"] = "failed" if report["errors"] else "succeeded"
    return report


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _base_report(options: MigrationOptions) -> dict[str, Any]:
    return {
        "migration": "legacy-one-shot",
        "profile": options.profile,
        "tenant_id": options.tenant_id,
        "dumps_dir": str(options.dumps_dir),
        "db_path": str(options.db_path) if options.db_path else None,
        "reset_db": options.reset_db,
        "strict": options.strict,
        "require_zero_conflicts": options.require_zero_conflicts,
        "dry_run": options.dry_run,
        "status": "pending",
        "errors": [],
    }


def _dump_report(schemas: list[str]) -> dict[str, dict[str, Any]]:
    discovered = list_dumps()
    candidates = list_dump_candidates()
    out: dict[str, dict[str, Any]] = {}
    for schema in schemas:
        path = discovered.get(schema)
        schema_candidates = candidates.get(schema, [])
        if path is None:
            out[schema] = {"present": False, "candidates": []}
            continue
        out[schema] = {
            "present": True,
            "path": str(path),
            "candidates": [str(item) for item in schema_candidates],
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        try:
            stats = LegacyImportRunner().parse_schema(schema)
            out[schema]["row_count"] = stats.total_rows
            out[schema]["tables"] = stats.table_row_counts
        except Exception as exc:  # noqa: BLE001
            out[schema]["parse_error"] = f"{exc.__class__.__name__}: {exc}"
    return out


def _mapper_errors(imports: list[dict[str, Any]]) -> int:
    total = 0
    for item in imports:
        for mapper in item.get("mappers", []):
            counts = mapper.get("counts", {}) if isinstance(mapper, dict) else {}
            total += sum(int(value) for key, value in counts.items() if key.endswith(".errors"))
    return total


def _table_accounting(dumps: dict[str, dict[str, Any]], imports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    imports_by_schema = {item["schema"]: item for item in imports}
    rows: list[dict[str, Any]] = []
    for schema, dump in dumps.items():
        tables = dump.get("tables") or {}
        imported = imports_by_schema.get(schema, {})
        mappers = imported.get("mappers") or []
        declared_tables = set(imported.get("handled_tables") or _declared_tables_for_schema(mappers))
        handled_tables = _handled_table_totals(mappers)
        for table, source_rows in sorted(tables.items()):
            source_count = int(source_rows)
            declared = table in declared_tables
            handled_rows = handled_tables.get(table, 0) if declared else 0
            rows.append(
                {
                    "schema": schema,
                    "table": table,
                    "declared": declared,
                    "source_rows": source_count,
                    "accounted_rows": handled_rows,
                    "unaccounted_rows": max(source_count - handled_rows, 0) if declared else source_count,
                }
            )
    return rows


def _handled_tables_for_schema(runner: LegacyImportRunner, schema: str) -> list[str]:
    tables: set[str] = set()
    for mapper in runner.mappers_for(schema):
        handled = getattr(mapper, "HANDLED_TABLES", set())
        tables.update(str(item) for item in handled)
    return sorted(tables)


def _declared_tables_for_schema(mappers: list[dict[str, Any]]) -> set[str]:
    tables: set[str] = set()
    for mapper in mappers:
        tables.update(str(key).split(".", 1)[0] for key in (mapper.get("counts") or {}))
        tables.update(str(key).split(".", 1)[0] for key in (mapper.get("skipped") or {}) if "." in str(key))
    return tables


def _handled_table_totals(mappers: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for mapper in mappers:
        for key, value in (mapper.get("counts") or {}).items():
            if "." not in str(key):
                continue
            table, kind = str(key).split(".", 1)
            if kind in {"imported", "errors"}:
                totals[table] = totals.get(table, 0) + int(value)
        for key, value in (mapper.get("skipped") or {}).items():
            if "." not in str(key):
                continue
            table, reason = str(key).split(".", 1)
            if reason.startswith("missing_field:"):
                continue
            totals[table] = totals.get(table, 0) + int(value)
    return totals


def _adapter_run_report(tenant_id: str) -> list[dict[str, Any]]:
    rows = [
        {
            "adapter_slug": item.adapter_slug,
            "operation": item.operation,
            "source_ref": item.source_ref,
            "idempotency_key": item.idempotency_key,
            "status": item.status,
            "target_count": item.target_count,
            "success_count": item.success_count,
            "failure_count": item.failure_count,
            "error_summary": item.error_summary,
        }
        for item in ExternalAdapterRepository().list_run_records(tenant_id=tenant_id)
    ]
    return sorted(
        rows,
        key=lambda item: (
            item["adapter_slug"],
            item["operation"],
            item["idempotency_key"],
            item["source_ref"] or "",
        ),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
