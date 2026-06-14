from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from zw_brain.adapters.legacy.profiles.customer_core_v1_coverage import audit_only_skip_for
from zw_brain.adapters.legacy.runner import LegacyImportRunner
from zw_brain.adapters.legacy.schema_index import list_dump_candidates, list_dumps
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT
from zw_brain.adapters.legacy.verification import verify_legacy_migration
from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
from zw_brain.shared.db import create_session_factory, ensure_parent_dir, get_database_url, reset_engine_cache
from zw_brain.shared.migrate import ensure_runtime_schema, reset_and_upgrade
from zw_brain.shared.sanitization import safe_json

CUSTOMER_CORE_V1_SCHEMAS = (
    "dsp_bsp",
    "dsp_catalog",
    "dsp_metaresource",
    "dsp_require",
    "dsp_handling",
    "dsp_example",
    "dsp_connect",
    "dsp_service",
    "dsp_pipelines",
    "dsp_monitor",
    "dsp_perform",
)
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


def run_acceptance_migration(options: MigrationOptions) -> dict[str, Any]:
    dry_run = _run_stage("dry_run", replace(options, dry_run=True, reset_db=False, strict=True))
    if dry_run.get("status") == "succeeded":
        apply = _run_stage("apply", replace(options, dry_run=False, reset_db=options.reset_db, strict=True))
    else:
        apply = _skipped_stage("apply", "dry_run_failed")
    if apply.get("status") == "succeeded":
        repeat_apply = _run_stage("repeat_apply", replace(options, dry_run=False, reset_db=False, strict=True))
    else:
        repeat_apply = _skipped_stage("repeat_apply", "apply_failed")
    report = safe_json(
        {
            "migration": "legacy-one-shot-acceptance",
            "profile": options.profile,
            "tenant_id": options.tenant_id,
            "dumps_dir": str(options.dumps_dir),
            "db_path": str(options.db_path) if options.db_path else None,
            "status": "pending",
            "stages": {"dry_run": dry_run, "apply": apply, "repeat_apply": repeat_apply},
            "acceptance": _acceptance_summary(dry_run, apply, repeat_apply),
            "errors": [],
        }
    )
    report["errors"] = _acceptance_errors(report)
    report["status"] = "failed" if report["errors"] else "succeeded"
    if report["status"] == "failed" and options.strict:
        raise MigrationError(report)
    return report


def _run_stage(stage: str, options: MigrationOptions) -> dict[str, Any]:
    try:
        report = run_migration(options)
    except MigrationError as exc:
        report = exc.report
    return safe_json(report | {"stage": stage})


def _skipped_stage(stage: str, reason: str) -> dict[str, Any]:
    return {"stage": stage, "status": "skipped", "reason": reason, "errors": [reason]}


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
        _attach_empty_fail_closed(report)
        raise MigrationError(report)
    if duplicates and options.strict:
        report["status"] = "failed"
        report["errors"].append(f"duplicate required dump(s): {', '.join(duplicates)}")
        _attach_empty_fail_closed(report)
        raise MigrationError(report)

    if not options.dry_run:
        ensure_parent_dir()
        if options.reset_db:
            # --reset-db = 显式破坏性重置（drop_all+create_all）。D58 起 reset_and_upgrade()
            # 闸在 ZW_BRAIN_ALLOW_SCHEMA_RESET=1 之后（M5 fail-closed），这条迁移批路径是
            # 唯一仍合法的显式重置入口 → 在此显式承认后调用。
            os.environ["ZW_BRAIN_ALLOW_SCHEMA_RESET"] = "1"
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
    report["fail_closed"] = _fail_closed_summary(report["dumps"], imports, report["table_accounting"])
    if not options.dry_run:
        report["coverage_skip_writes"] = _write_audit_only_skip_evidence(
            report["table_accounting"], options.tenant_id
        )
    report["sanitization"] = _sanitization_summary(report)
    report["verification"] = {"skipped": True, "reason": "dry_run_no_db_writes"} if options.dry_run else verify_legacy_migration(
        tenant_id=options.tenant_id,
        require_zero_conflicts=options.require_zero_conflicts,
    )
    failed_imports = [item for item in imports if item["status"] not in {"succeeded", "skipped"}]
    failed_runs = [item for item in report["adapter_runs"] if item["status"] not in {"succeeded", "replayed"}]
    mapper_errors = _mapper_errors(imports)
    dump_parse_errors = [schema for schema, info in report["dumps"].items() if info.get("parse_error")]
    unmapped_rows = [
        item for item in report["table_accounting"]
        if item.get("bucket") == "mapped" and item["unaccounted_rows"] > 0
    ]
    unknown_rows = [
        item for item in report["table_accounting"]
        if item.get("bucket") == "unknown" and item["source_rows"] > 0
    ]
    if failed_imports:
        report["errors"].append(f"failed import(s): {', '.join(item['schema'] for item in failed_imports)}")
    if failed_runs:
        report["errors"].append(f"failed adapter run(s): {len(failed_runs)}")
    if mapper_errors:
        report["errors"].append(f"mapper error row(s): {mapper_errors}")
    if dump_parse_errors:
        report["errors"].append(f"dump parse error(s): {', '.join(dump_parse_errors)}")
    if unmapped_rows:
        table_refs = ", ".join(f"{item['schema']}.{item['table']}" for item in unmapped_rows[:10])
        report["errors"].append(f"unaccounted source row table(s) in declared mapper: {table_refs}")
    if unknown_rows:
        table_refs = ", ".join(f"{item['schema']}.{item['table']}" for item in unknown_rows[:10])
        report["errors"].append(f"unknown source row table(s) (declare mapper or add to coverage manifest): {table_refs}")
    if report["verification"].get("failed"):
        report["errors"].append("legacy mapping verification failed")
    if options.strict and report["errors"]:
        report["status"] = "failed"
        raise MigrationError(report)
    if not options.dry_run:
        _checkpoint_seed_file()
    report["status"] = "failed" if report["errors"] else "succeeded"
    return report


def _checkpoint_seed_file() -> None:
    """Merge the WAL into the main DB file so the built seed is self-contained.

    SQLite runs in WAL mode (shared/db.py), so writes land in a side `-wal` file
    that is only folded into the main `.db` on checkpoint. The cached engines
    hold connections open, so without this the migration would exit leaving a
    stray `-wal`. Anything that copies only the main file then sees a stale
    snapshot — e.g. the real-data test fixtures' `shutil.copy(SEED_DB, ...)`,
    whose first run after a rebuild missed freshly-imported rows, or an ops file
    transfer of a customer migration. Dispose engines (closes their connections)
    then TRUNCATE-checkpoint via a fresh connection so the `-wal` is removed.
    """
    url = get_database_url()
    reset_engine_cache()
    if not url.startswith("sqlite:///"):
        return
    import sqlite3

    db_path = url.removeprefix("sqlite:///")
    if not Path(db_path).exists():
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_audit_only_skip_evidence(table_accounting: list[dict[str, Any]], tenant_id: str) -> dict[str, Any]:
    """For each audit-only-skip table in the manifest, write one legacy_object_mapping
    row + one audit_event row so the skipped source is auditable without entering
    business canonical tables (catalog_entry/catalog_item/resource_asset/...).
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from zw_brain.domain.models import AuditEventRecord

    skip_rows = [item for item in table_accounting if item.get("bucket") == "audit-only-skip"]
    SessionLocal = create_session_factory()
    legacy_mapping_repo = LegacyObjectMappingRepository()
    mapping_written = 0
    audit_written = 0
    for row in skip_rows:
        schema = row["schema"]
        table = row["table"]
        reason = row.get("skip_reason") or "audit_only_skip"
        source_rows = int(row.get("source_rows") or 0)
        legacy_system = legacy_system_for_schema(schema)
        canonical_ref = f"{schema}.{table}"
        legacy_mapping_repo.upsert_mapping(
            {
                "source_ref": f"{legacy_system}:legacy_only_evidence:{schema}.{table}",
                "legacy_system": legacy_system,
                "legacy_object_type": table,
                "legacy_object_ref": canonical_ref,
                "canonical_type": "legacy_only_evidence",
                "canonical_ref": canonical_ref,
                "evidence_json": {
                    "reason": reason,
                    "source_rows": source_rows,
                    "schema": schema,
                    "table": table,
                },
            },
            tenant_id=tenant_id,
        )
        mapping_written += 1
        with SessionLocal() as session:
            # Idempotent: only insert when no prior receipt for (skill_id, schema.table).
            existing = session.execute(
                select(AuditEventRecord).where(
                    AuditEventRecord.skill_id == "legacy.coverage.skip",
                    AuditEventRecord.request_id == canonical_ref,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    AuditEventRecord(
                        request_id=canonical_ref,
                        actor="legacy.migration",
                        skill_id="legacy.coverage.skip",
                        phase="audit_only_skip",
                        payload_json=safe_json(
                            {
                                "schema": schema,
                                "table": table,
                                "reason": reason,
                                "rows": source_rows,
                                "tenant_id": tenant_id,
                            }
                        ),
                        occurred_at=datetime.now(UTC),
                    )
                )
                session.commit()
                audit_written += 1
    return {
        "skip_table_count": len(skip_rows),
        "legacy_only_evidence_written": mapping_written,
        "audit_events_written": audit_written,
    }


def legacy_system_for_schema(schema: str) -> str:
    from zw_brain.adapters.legacy.tenant_normalizer import legacy_system_for

    return legacy_system_for(schema)


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


def _attach_empty_fail_closed(report: dict[str, Any]) -> None:
    report["imports"] = []
    report["adapter_runs"] = []
    report["table_accounting"] = []
    report["fail_closed"] = _fail_closed_summary(report["dumps"], [], [])
    report["sanitization"] = _sanitization_summary(report)


def _mapper_errors(imports: list[dict[str, Any]]) -> int:
    total = 0
    for item in imports:
        for mapper in item.get("mappers", []):
            counts = mapper.get("counts", {}) if isinstance(mapper, dict) else {}
            total += sum(int(value) for key, value in counts.items() if key.endswith(".errors"))
    return total


def _acceptance_summary(dry_run: dict[str, Any], apply: dict[str, Any], repeat_apply: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow": ["dry_run", "apply", "repeat_apply"],
        "stage_statuses": {stage["stage"]: stage["status"] for stage in (dry_run, apply, repeat_apply)},
        "mapped_total": int((repeat_apply.get("verification") or {}).get("total_mappings") or 0),
        "unmapped_tables": (repeat_apply.get("fail_closed") or {}).get("unmapped_tables", []),
        "missing_dumps": (dry_run.get("fail_closed") or {}).get("missing_dumps", []),
        "sensitive_policy": _sanitization_summary(repeat_apply, include_policy=True),
        "idempotency": _idempotency_summary(apply, repeat_apply),
        "legacy_runtime_dependency": "not_required_after_apply",
    }


def _acceptance_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for stage_name, stage in report["stages"].items():
        if stage.get("status") != "succeeded":
            errors.append(f"{stage_name} failed")
        errors.extend(str(item) for item in stage.get("errors", []))
    idempotency = report["acceptance"]["idempotency"]
    if not idempotency["verified"]:
        errors.append(f"repeat apply idempotency failed: {idempotency['reason']}")
    return sorted(set(errors))


def _idempotency_summary(apply: dict[str, Any], repeat_apply: dict[str, Any]) -> dict[str, Any]:
    apply_counts = (apply.get("verification") or {}).get("canonical_counts") or {}
    repeat_counts = (repeat_apply.get("verification") or {}).get("canonical_counts") or {}
    run_count_delta = len(repeat_apply.get("adapter_runs") or []) - len(apply.get("adapter_runs") or [])
    verified = apply_counts == repeat_counts and run_count_delta == 0
    reason = "canonical_counts_and_adapter_run_records_stable" if verified else "canonical_counts_or_adapter_run_records_changed"
    return {"verified": verified, "reason": reason, "canonical_counts": repeat_counts, "adapter_run_record_delta": run_count_delta}


def _fail_closed_summary(dumps: dict[str, dict[str, Any]], imports: list[dict[str, Any]], accounting: list[dict[str, Any]]) -> dict[str, Any]:
    mapper_issues: dict[str, int] = {}
    for item in imports:
        for mapper in item.get("mappers", []):
            for issue in mapper.get("issues", []) if isinstance(mapper, dict) else []:
                issue_type = str(issue.get("type", "unknown"))
                mapper_issues[issue_type] = mapper_issues.get(issue_type, 0) + 1
    unknown_tables = [
        f"{item['schema']}.{item['table']}"
        for item in accounting
        if item.get("bucket") == "unknown" and item["source_rows"] > 0
    ]
    # `unmapped` = mapper declared the table but failed to consume all rows.
    unmapped_tables = [
        f"{item['schema']}.{item['table']}"
        for item in accounting
        if item.get("bucket") == "mapped" and item["unaccounted_rows"] > 0
    ]
    declared_audit_only_skip = [
        f"{item['schema']}.{item['table']}"
        for item in accounting
        if item.get("bucket") == "audit-only-skip"
    ]
    return {
        "missing_dumps": [schema for schema, info in dumps.items() if not info.get("present")],
        "unmapped_tables": unmapped_tables,
        "unknown_tables": unknown_tables,
        "audit_only_skip_tables": declared_audit_only_skip,
        # Legacy field kept for backwards-compat: list both unmapped + unknown so
        # callers that still expect a single set still see every row that did NOT
        # enter canonical state.
        "unaccounted_tables": unmapped_tables + unknown_tables,
        "mapper_issues": dict(sorted(mapper_issues.items())),
    }


def _sanitization_summary(report: dict[str, Any], *, include_policy: bool = False) -> dict[str, Any]:
    policy = ["password", "passwd", "token", "session", "client_secret", "permission_sql", "service_sql", "menu"]
    scrubbed = safe_json({key: value for key, value in report.items() if key != "sanitization"})
    leaked = sorted(_sensitive_value_markers(scrubbed, policy))
    summary: dict[str, Any] = {"report_sanitized": not leaked, "forbidden_markers": leaked}
    if include_policy:
        summary["excluded_legacy_facts"] = policy
    return summary


def _sensitive_value_markers(value: Any, policy: list[str]) -> set[str]:
    if isinstance(value, dict):
        markers: set[str] = set()
        for key, item in value.items():
            if str(key) in {"excluded_legacy_facts", "forbidden_markers", "audit_only_skip_tables", "table", "skip_reason"}:
                continue
            markers.update(_sensitive_value_markers(item, policy))
        return markers
    if isinstance(value, list):
        markers: set[str] = set()
        for item in value:
            markers.update(_sensitive_value_markers(item, policy))
        return markers
    if not isinstance(value, str):
        return set()
    return {item for item in policy if _looks_like_sensitive_literal(value, item)}


def _looks_like_sensitive_literal(value: str, marker: str) -> bool:
    lowered = value.lower().strip()
    if marker not in lowered:
        return False
    if lowered == marker:
        return True
    separators = ("=", ":", '"', "'", "{", "[", " ")
    return any(f"{marker}{separator}" in lowered or f"{separator}{marker}" in lowered for separator in separators)


def _table_accounting(dumps: dict[str, dict[str, Any]], imports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    imports_by_schema = {item["schema"]: item for item in imports}
    rows: list[dict[str, Any]] = []
    for schema, dump in dumps.items():
        tables = dump.get("tables") or {}
        imported = imports_by_schema.get(schema, {})
        mappers = imported.get("mappers") or []
        declared_tables = set(imported.get("handled_tables") or _declared_tables_for_schema(mappers))
        handled_tables = _handled_table_totals(mappers)
        skip_for_schema = audit_only_skip_for(schema)
        for table, source_rows in sorted(tables.items()):
            source_count = int(source_rows)
            declared = table in declared_tables
            skip_reason = skip_for_schema.get(table)
            if declared:
                handled_rows = handled_tables.get(table, 0)
                bucket = "mapped"
            elif skip_reason:
                handled_rows = source_count
                bucket = "audit-only-skip"
            else:
                handled_rows = 0
                bucket = "unknown"
            unaccounted = (
                max(source_count - handled_rows, 0)
                if bucket == "mapped"
                else (0 if bucket == "audit-only-skip" else source_count)
            )
            row = {
                "schema": schema,
                "table": table,
                "declared": declared,
                "bucket": bucket,
                "source_rows": source_count,
                "accounted_rows": handled_rows,
                "unaccounted_rows": unaccounted,
            }
            if skip_reason:
                row["skip_reason"] = skip_reason
            rows.append(row)
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
            if kind in {"imported", "errors", "attached", "merged"}:
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
