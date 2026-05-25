"""Shared guard for M0 真灌库 (real-data seed) tests.

14 test modules each copy-pasted a `_seed_ready()` that checked only row COUNT,
not whether the seed's schema matched the current ORM models. A populated-but-
stale seed (e.g. after a model adds a column) therefore slipped past the guard
and produced cryptic `no such column` ERRORs at fixture setup instead of a
clean skip. This helper checks BOTH schema currency and data presence, and
skips cleanly with a rebuild hint when either fails.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pytest

from zw_brain.domain.models import Base

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DB = REPO_ROOT / ".data" / "zw_brain.db"
DEFAULT_TENANT = "sd-default"

REBUILD_HINT = (
    "重建真灌库（M0 一次性迁移路径，含审计证据写入）："
    '.venv/bin/python -m zw_brain.entry.legacy_migration.main '
    '--dumps-dir "old/10示例数据" --db-path .data/zw_brain.db --reset-db '
    "--report /tmp/migration-report.json"
)


def schema_drift_reason() -> str | None:
    """Reason the seed schema is behind the current ORM models, else None.

    For every model table that exists in the seed, every model column must be
    present. Extra seed columns are ignored — the seed may legitimately predate
    a column drop. This is exactly the check the old per-file `_seed_ready()`
    lacked.
    """
    with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
        seeded = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in Base.metadata.sorted_tables:
            if table.name not in seeded:
                continue
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{table.name}")')}
            missing = {c.name for c in table.columns} - cols
            if missing:
                return f"{table.name} 缺列 {sorted(missing)}"
    return None


def _normalize(checks: object, tenant: str) -> list[tuple[str, int, str, tuple]]:
    if checks is None:
        return []
    if isinstance(checks, dict):
        items: Iterable = list(checks.items())
    elif isinstance(checks, tuple) and checks and isinstance(checks[0], str):
        items = [checks]
    else:
        items = list(checks)  # type: ignore[arg-type]
    out: list[tuple[str, int, str, tuple]] = []
    for it in items:
        if len(it) == 3:
            table, min_rows, where = it
            out.append((table, min_rows, where, ()))
        else:
            table, min_rows = it
            out.append((table, min_rows, "tenant_id = ?", (tenant,)))
    return out


def require_real_seed(checks: object = None, *, tenant: str = DEFAULT_TENANT) -> None:
    """Skip the calling module cleanly unless the M0 真灌库 seed exists, matches
    the current model schema, and meets row thresholds. Call at module top level.

    `checks` accepts:
      - dict  {table: min_rows}              — tenant-scoped count
      - tuple (table, min_rows)              — tenant-scoped count
      - tuple (table, min_rows, where_sql)   — custom WHERE (no auto tenant filter)
      - an iterable of the above tuples
    """
    if not SEED_DB.exists():
        pytest.skip(
            f"M0 真灌库缺位（无 {SEED_DB.name}）；{REBUILD_HINT}",
            allow_module_level=True,
        )
    drift = schema_drift_reason()
    if drift is not None:
        pytest.skip(
            f"M0 真灌库 schema 落后于模型（{drift}）；{REBUILD_HINT}",
            allow_module_level=True,
        )
    for table, min_rows, where, params in _normalize(checks, tenant):
        with sqlite3.connect(f"file:{SEED_DB}?mode=ro", uri=True) as conn:
            try:
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {where}", params
                ).fetchone()
            except sqlite3.OperationalError as exc:
                pytest.skip(
                    f"M0 真灌库表 {table} 不可用（{exc}）；{REBUILD_HINT}",
                    allow_module_level=True,
                )
            got = row[0] if row else 0
            if got < min_rows:
                pytest.skip(
                    f"M0 真灌库 {table} 行数不足（需 ≥{min_rows}，实 {got}）；{REBUILD_HINT}",
                    allow_module_level=True,
                )
