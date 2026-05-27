"""Shared utilities for legacy dump mappers.

All mapper modules import from here; nothing is redefined per-mapper.
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zw_brain.domain.repositories.external_adapter import ExternalAdapterRepository
from zw_brain.shared.sanitization import safe_json


@dataclass
class ImportStats:
    schema: str
    dump_path: Path
    counts: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    target_counts: dict[str, int] = field(default_factory=dict)
    issues: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "apply"

    def bump(self, table: str, key: str = "imported") -> None:
        self.counts[f"{table}.{key}"] = self.counts.get(f"{table}.{key}", 0) + 1

    def bump_source(self, table: str) -> None:
        self.source_counts[table] = self.source_counts.get(table, 0) + 1

    def bump_target(self, target: str) -> None:
        self.target_counts[target] = self.target_counts.get(target, 0) + 1

    def add_issue(
        self,
        issue_type: str,
        table: str,
        legacy_ref: Any,
        detail: dict[str, Any] | None = None,
        *,
        severity: str = "error",
    ) -> None:
        # severity="warn" means business-level fail-closed (e.g. missing_manifest rows skipped on
        # purpose); these don't contribute to adapter_run_record.failure_count and don't bump the
        # run to partial_failure, but they DO appear in error_summary so the receipt is never silent.
        # severity="error" is the default (technical issues — malformed row, unmapped permission).
        if severity not in {"error", "warn"}:
            raise ValueError(f"invalid issue severity: {severity!r}")
        self.issues.append(
            safe_json(
                {
                    "type": issue_type,
                    "table": table,
                    "legacy_ref": str(legacy_ref or ""),
                    "detail": detail or {},
                    "severity": severity,
                }
            )
        )

    def skip(self, table: str) -> None:
        self.skipped[table] = self.skipped.get(table, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "dump_path": str(self.dump_path),
            "mode": self.mode,
            "counts": dict(self.counts),
            "source_counts": dict(self.source_counts),
            "target_counts": dict(self.target_counts),
            "issues": safe_json(self.issues),
            "skipped": dict(self.skipped),
        }


def schema_from_dump_name(name: str) -> str:
    """Extract schema name from a mysqldump filename.

    e.g. ``dump-dsp_catalog-202604271409.sql`` → ``dsp_catalog``
    """
    if name.startswith("dump-") and "-" in name[5:]:
        body = name[5:]
        return body[: body.rfind("-")]
    return name


def coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return default


def coerce_time(value: Any) -> str | None:
    if not value:
        return None
    return str(value)


def coerce_datetime(value: Any) -> datetime | None:
    """Parse legacy mysqldump time strings into a real datetime.

    SQLite's DateTime column rejects raw strings; canonical / projection records
    that have a typed datetime column (RiskEventProjection.detected_at,
    HealthSignalProjection.last_observed_at, ComplianceCase.closed_at, …) need
    a real datetime object. mysqldump emits 'YYYY-MM-DD HH:MM:SS', which becomes
    ISO-8601 once the space is replaced with 'T'.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return None
    return None


def parse_json_blob(value: Any) -> dict[str, Any]:
    """Parse a mysqldump string-or-dict blob into a dict.

    Some columns store JSON as a VARCHAR (e.g. data_example_file.file_path stores
    ``'{"file_name":"x.pdf","file_size":"1MB",...}'``).  Returns {} on any failure.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = _json.loads(value)
        return parsed if isinstance(parsed, dict) else {"raw": value}
    except (ValueError, TypeError):
        return {"raw": value}


def finish_run(
    adapter_repo: ExternalAdapterRepository,
    stats: ImportStats,
    *,
    adapter_slug: str,
    dump_path: Path,
    started_at: datetime,
    tenant_id: str,
) -> None:
    """Write the AdapterRunRecord that closes a mapper's import batch.

    Identical block repeated in every mapper before this helper existed.

    `error_summary` is **always** populated when any issue exists (errors OR warns),
    so partial_failure runs never carry `error_summary=None` (silent swallow ban —
    CLAUDE.md §2). warn-level issues (business-level fail-closed, e.g. missing_manifest
    rows skipped on purpose) DO NOT contribute to failure_count and the run stays
    `succeeded`; they appear in error_summary's `business_skips` section for audit.
    """
    schema = schema_from_dump_name(dump_path.name)
    finished_at = datetime.now(UTC)
    error_issues = [item for item in stats.issues if item.get("severity", "error") == "error"]
    warn_issues = [item for item in stats.issues if item.get("severity", "error") == "warn"]
    technical_error_rows = sum(v for k, v in stats.counts.items() if k.endswith(".errors"))
    failure_count = technical_error_rows + len(error_issues)
    imported_count = sum(v for k, v in stats.counts.items() if k.endswith(".imported"))
    error_summary = _build_error_summary(error_issues, warn_issues, technical_error_rows)
    adapter_repo.upsert_run_record(
        {
            "adapter_slug": adapter_slug,
            "operation": "import",
            "direction": "inbound",
            "source_ref": f"{schema}:{dump_path.name}",
            "idempotency_key": f"{adapter_slug}:{dump_path.name}",
            "status": "succeeded" if failure_count == 0 else "partial_failure",
            "target_count": imported_count + failure_count,
            "failure_count": failure_count,
            "receipt_json": stats.to_dict()
            | {
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
            },
            "error_summary": error_summary,
            "finished_at": finished_at,
        },
        tenant_id=tenant_id,
    )


def _build_error_summary(
    error_issues: list[dict[str, Any]],
    warn_issues: list[dict[str, Any]],
    technical_error_rows: int,
) -> str | None:
    """Compose a text breakdown for adapter_run_record.error_summary.

    Returns None only when nothing is wrong (no issues + zero .errors rows).
    Otherwise returns multi-line text with two sections so downstream can tell
    "rows silently dropped fail-closed" from "rows failed to import":

        technical_errors: <N> (<table>.<type>=<count>, ...)
        business_skips: <M> (<table>.<type>=<count>, ...)
    """
    if not error_issues and not warn_issues and technical_error_rows == 0:
        return None

    def _breakdown(items: list[dict[str, Any]]) -> str:
        if not items:
            return ""
        counts: dict[str, int] = {}
        for item in items:
            key = f"{item.get('table', '?')}.{item.get('type', '?')}"
            counts[key] = counts.get(key, 0) + 1
        parts = [f"{key}={value}" for key, value in sorted(counts.items())]
        return ", ".join(parts)

    error_line = f"technical_errors: {technical_error_rows + len(error_issues)}"
    error_detail = _breakdown(error_issues)
    if error_detail:
        error_line = f"{error_line} ({error_detail})"
    warn_line = f"business_skips: {len(warn_issues)}"
    warn_detail = _breakdown(warn_issues)
    if warn_detail:
        warn_line = f"{warn_line} ({warn_detail})"
    return f"{error_line}\n{warn_line}"
