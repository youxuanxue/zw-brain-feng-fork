"""Resolve legacy schema name → mysqldump file path.

Discovery rule: any file matching `dump-<schema>-*.sql` under the dumps root is treated
as authoritative for that schema. The dumps root defaults to `old/10示例数据/` relative
to the repo root, overridable via `ZW_BRAIN_LEGACY_DUMPS_DIR` for tests.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DUMP_FILENAME_RE = re.compile(r"^dump-([A-Za-z0-9_]+)-\d+\.sql$")
DEFAULT_DUMPS_DIR_CANDIDATES = [
    "old/10示例数据",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def dumps_dir() -> Path:
    override = os.environ.get("ZW_BRAIN_LEGACY_DUMPS_DIR")
    if override:
        return Path(override)
    root = _repo_root()
    for candidate in DEFAULT_DUMPS_DIR_CANDIDATES:
        path = root / candidate
        if path.is_dir():
            return path
    return root / DEFAULT_DUMPS_DIR_CANDIDATES[0]


def list_dump_candidates() -> dict[str, list[Path]]:
    """Return all discovered dump candidates grouped by schema name."""
    out: dict[str, list[Path]] = {}
    base = dumps_dir()
    if not base.is_dir():
        return out
    for entry in sorted(base.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".sql"):
            continue
        match = DUMP_FILENAME_RE.match(entry.name)
        if not match:
            continue
        schema = match.group(1)
        out.setdefault(schema, []).append(entry)
    return out


def list_dumps() -> dict[str, Path]:
    """Return {schema_name: dump_path} discovered under the dumps directory."""
    return {schema: paths[-1] for schema, paths in list_dump_candidates().items()}


def dump_path_for(schema: str) -> Path:
    dumps = list_dumps()
    if schema not in dumps:
        raise FileNotFoundError(f"no dump file for schema '{schema}' under {dumps_dir()}")
    return dumps[schema]


# Lazy-evaluated alias used by callers that just want a snapshot.
LEGACY_DUMPS = list_dumps()
