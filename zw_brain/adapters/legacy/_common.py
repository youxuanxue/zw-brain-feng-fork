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


@dataclass
class ImportStats:
    schema: str
    dump_path: Path
    counts: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def bump(self, table: str, key: str = "imported") -> None:
        self.counts[f"{table}.{key}"] = self.counts.get(f"{table}.{key}", 0) + 1

    def skip(self, table: str) -> None:
        self.skipped[table] = self.skipped.get(table, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "dump_path": str(self.dump_path),
            "counts": dict(self.counts),
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
    """
    schema = schema_from_dump_name(dump_path.name)
    finished_at = datetime.now(UTC)
    failure_count = sum(v for k, v in stats.counts.items() if k.endswith(".errors"))
    imported_count = sum(v for k, v in stats.counts.items() if k.endswith(".imported"))
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
            "finished_at": finished_at,
        },
        tenant_id=tenant_id,
    )
