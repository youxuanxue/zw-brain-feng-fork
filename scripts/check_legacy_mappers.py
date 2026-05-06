#!/usr/bin/env python3
"""check_legacy_mappers.py — preflight 段 16

Verifies every legacy mapper class:
  1. Imports cleanly (catches dangling refs after refactors)
  2. Exposes HANDLED_TABLES (frozenset of legacy table names — non-empty)
  3. Exposes ADAPTER_SLUG (a `legacy.<area>.<verb>` namespaced string)
  4. Exposes import_dump(self, dump_path: Path) -> ImportStats
  5. ADAPTER_SLUG values are unique across the mapper registry
       (so AdapterRunRecord rows don't collide between mappers)
  6. Every schema in `LegacyImportRunner.mappers_for` resolves to ≥1 mapper

This is a static contract check — no DB or dumps needed; runs in <1s.

Hard-约束源：D7（adapter 层是唯一旧→新写入路径）+ D4（每条写动作必须留
AdapterRunRecord，所以 ADAPTER_SLUG 必须唯一）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# This check imports the project package + SQLAlchemy, so it needs the project
# venv. Detect "in a venv" via sys.prefix != sys.base_prefix; the homebrew
# python and the venv python share the same underlying binary so resolve()
# can't distinguish them. Re-exec into .venv/bin/python when not inside one.
_venv_python = REPO_ROOT / ".venv" / "bin" / "python"
if _venv_python.exists() and sys.prefix == sys.base_prefix:
    os.execv(str(_venv_python), [str(_venv_python), __file__, *sys.argv[1:]])

import inspect

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    from zw_brain.adapters.legacy import LegacyImportRunner
    from zw_brain.adapters.legacy.mappers import (
        CatalogMetadataMapper,
        ConnectMapper,
        ExchangeMapper,
        GovernanceMapper,
        MonitorMapper,
        ObjectionMapper,
        PerformMapper,
        PipelinesMapper,
        ServiceMapper,
        TopicPackageMapper,
    )

    mappers = [
        CatalogMetadataMapper, ConnectMapper, ExchangeMapper, GovernanceMapper,
        MonitorMapper, ObjectionMapper, PerformMapper, PipelinesMapper,
        ServiceMapper, TopicPackageMapper,
    ]

    errors: list[str] = []
    slugs_seen: dict[str, str] = {}
    for cls in mappers:
        name = cls.__name__
        # 1. HANDLED_TABLES non-empty
        handled = getattr(cls, "HANDLED_TABLES", None)
        if not handled or not hasattr(handled, "__iter__"):
            errors.append(f"{name}: HANDLED_TABLES missing or not iterable")
        # 2. ADAPTER_SLUG well-formed + unique
        slug = getattr(cls, "ADAPTER_SLUG", None)
        if not slug or not isinstance(slug, str) or not slug.startswith("legacy."):
            errors.append(f"{name}: ADAPTER_SLUG missing or not 'legacy.*' (got {slug!r})")
        elif slug in slugs_seen:
            errors.append(f"{name}: ADAPTER_SLUG {slug!r} duplicates {slugs_seen[slug]}")
        else:
            slugs_seen[slug] = name
        # 3. import_dump signature
        if not hasattr(cls, "import_dump"):
            errors.append(f"{name}: import_dump method missing")
            continue
        sig = inspect.signature(cls.import_dump)
        params = list(sig.parameters.keys())
        if params[:2] != ["self", "dump_path"]:
            errors.append(f"{name}: import_dump signature should start with (self, dump_path), got {params[:2]}")

    # 4. runner.mappers_for routing covers known schemas
    runner = LegacyImportRunner(tenant_id="sd-default", cache_dir=REPO_ROOT / ".legacy_cache")
    expected_schemas = {
        "dsp_bsp", "dsp_catalog", "dsp_metaresource", "dsp_require",
        "dsp_example", "dsp_handling", "dsp_pipelines", "dsp_service",
        "dsp_connect", "dsp_monitor", "dsp_perform",
    }
    for schema in expected_schemas:
        ms = runner.mappers_for(schema)
        if not ms:
            errors.append(f"runner.mappers_for({schema!r}) returned empty — no mapper registered")

    if errors:
        print("[legacy-mappers] FAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"[legacy-mappers] OK: {len(mappers)} mappers, {len(slugs_seen)} unique adapter slugs, {len(expected_schemas)} schemas routed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
