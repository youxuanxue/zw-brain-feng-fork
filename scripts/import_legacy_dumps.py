#!/usr/bin/env python3
"""Legacy mysqldump → zw-brain importer CLI.

Subcommands:
    parse-stats  — quickly count rows per table for one or all schemas (no DB writes)
    cache        — stream-parse a schema's dump into `.legacy_cache/<schema>/<table>.jsonl`
                   for inspection / audit (gitignored, contains real PII per [2026-05-06]
                   sensitive policy)
    list         — show discovered schema → dump path mapping

The mapper subcommands (`import`, `verify`) are wired in subsequent commits.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make repo root importable when invoked as a standalone script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zw_brain.adapters.legacy import LegacyImportRunner, list_dumps  # noqa: E402


def cmd_list(args: argparse.Namespace) -> int:
    dumps = list_dumps()
    if not dumps:
        print("(no dumps discovered)", file=sys.stderr)
        return 1
    for schema, path in dumps.items():
        size = path.stat().st_size
        print(f"{schema:<25} {size:>13,} B  {path}")
    return 0


def cmd_parse_stats(args: argparse.Namespace) -> int:
    runner = LegacyImportRunner()
    schemas = [args.schema] if args.schema else None
    stats_by_schema = runner.parse_all(schemas)
    grand_total = 0
    for schema, stats in stats_by_schema.items():
        grand_total += stats.total_rows
        if args.json:
            print(json.dumps(stats.to_dict(), ensure_ascii=False))
        else:
            print(f"{schema}  rows={stats.total_rows:,}  tables_with_rows={len(stats.table_row_counts)}  skipped={len(stats.skipped_tables)}")
    if not args.json:
        print(f"--- total rows: {grand_total:,}")
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    runner = LegacyImportRunner()
    out_dir = runner.write_jsonl_cache(args.schema, max_rows_per_table=args.max_rows_per_table)
    print(f"wrote: {out_dir}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Sample LegacyObjectMappingRecord rows, resolve canonical_ref via repos, report.

    For each canonical_type, the repo lookup table below tells verify how to
    enumerate the canonical entities; the legacy_object_mapping must point at
    something that exists, otherwise the mapper either left an `unresolved` row
    or canonical state was wiped after import. The exit code is non-zero when
    `--strict` is set and any unresolved/missing rows surface — preflight
    legacy-import smoke uses --strict against a tiny synthetic dump.
    """
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    from zw_brain.domain.repositories.application import ApplicationRepository
    from zw_brain.domain.repositories.catalog import CatalogRepository
    from zw_brain.domain.repositories.compliance_ops import ComplianceOpsRepository
    from zw_brain.domain.repositories.delivery import DeliveryRepository
    from zw_brain.domain.repositories.governance_projection import GovernanceProjectionRepository
    from zw_brain.domain.repositories.legacy_mapping import LegacyObjectMappingRepository
    from zw_brain.domain.repositories.objection import ObjectionRepository
    from zw_brain.domain.repositories.resource_api import ResourceApiRepository
    from zw_brain.domain.repositories.topic_package import TopicPackageRepository

    tenant = args.tenant or "sd-default"
    gov = GovernanceProjectionRepository()
    compliance = ComplianceOpsRepository()

    # canonical_type → set of canonical_refs that exist in this DB
    resolvers: dict[str, set[str]] = {
        "OrgProjectionRecord": {o.org_code for o in gov.list_orgs(tenant_id=tenant)},
        "RegionProjectionRecord": {r.region_code for r in gov.list_regions(tenant_id=tenant)},
        "ActorProjectionRecord": {a.external_actor_id for a in gov.list_actors(tenant_id=tenant)},
        "RoleProjectionRecord": {r.role_code for r in gov.list_roles(tenant_id=tenant)},
        "catalog_entry": {e.catalog_code for e in CatalogRepository().list_entries()},
        "catalog_item": {i.item_code for i in CatalogRepository().list_items()},
        "resource_asset": {a.resource_code for a in ResourceApiRepository().list_assets(tenant_id=tenant)},
        "application_record": {a.application_code for a in ApplicationRepository().list_records()},
        "ObjectionCaseRecord": {c.id for c in ObjectionRepository().list_cases()},
        "TopicPackageRecord": {p.package_code for p in TopicPackageRepository().list_packages(tenant_id=tenant)},
        "DeliveryTaskRecord": {t.delivery_code for t in DeliveryRepository().list_tasks()},
        "DeliveryAttemptRecord": {a.attempt_code for a in DeliveryRepository().list_attempts()},
        "ComplianceCaseRecord": {c.case_code for c in compliance.list_cases(tenant_id=tenant)},
        "ComplianceRuleRecord": {r.rule_code for r in compliance.list_rules(tenant_id=tenant)},
        "MetricDefinitionProjectionRecord": {m.metric_code for m in compliance.list_metric_definitions(tenant_id=tenant)},
    }
    # Types we don't enumerate (registry-only / external mappings) — always treated as
    # "weak resolved" since the mapping itself is the canonical answer.
    weak_resolved = {"DeliveryChannelRegistry", "ExternalApplicationMapping"}

    legacy_repo = LegacyObjectMappingRepository()
    all_mappings = legacy_repo.list_mappings(tenant_id=tenant)
    by_type: dict[str, list[Any]] = {}
    for m in all_mappings:
        by_type.setdefault(m.canonical_type, []).append(m)

    rows: list[tuple[str, int, int, int, list[str]]] = []
    total_unresolved = 0
    for canonical_type, mappings in sorted(by_type.items()):
        if canonical_type in weak_resolved:
            rows.append((canonical_type, len(mappings), len(mappings), 0, []))
            continue
        known = resolvers.get(canonical_type)
        if known is None:
            # Unknown canonical_type — count as unresolved with note
            rows.append((canonical_type, len(mappings), 0, len(mappings), ["UNKNOWN_TYPE"]))
            total_unresolved += len(mappings)
            continue
        resolved = sum(1 for m in mappings if m.canonical_ref in known)
        unresolved = len(mappings) - resolved
        sample = [m.canonical_ref for m in mappings if m.canonical_ref not in known][:3]
        rows.append((canonical_type, len(mappings), resolved, unresolved, sample))
        total_unresolved += unresolved

    if args.json:
        print(json.dumps({
            "tenant_id": tenant,
            "total_mappings": len(all_mappings),
            "total_unresolved": total_unresolved,
            "by_type": [
                {"canonical_type": t, "mapped": m, "resolved": r, "unresolved": u, "sample_unresolved": s}
                for (t, m, r, u, s) in rows
            ],
        }, ensure_ascii=False))
    else:
        print(f"verify tenant={tenant}  total_mappings={len(all_mappings)}  total_unresolved={total_unresolved}")
        print(f"{'canonical_type':<32} {'mapped':>8} {'resolved':>10} {'unresolved':>12}  sample_missing")
        for t, m, r, u, s in rows:
            sample_str = ", ".join(s) if s else ""
            print(f"  {t:<30} {m:>8} {r:>10} {u:>12}  {sample_str}")

    if args.strict and total_unresolved > 0:
        return 2
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    runner = LegacyImportRunner()
    result = runner.import_schema(args.schema)
    if result is None:
        print(f"no mapper registered for schema: {args.schema}", file=sys.stderr)
        return 1
    stats_list = result if isinstance(result, list) else [result]
    payloads = [(s.to_dict() if hasattr(s, "to_dict") else s) for s in stats_list]
    if args.json:
        print(json.dumps(payloads if len(payloads) > 1 else payloads[0], ensure_ascii=False))
        return 0
    print(f"imported schema={args.schema} ({len(payloads)} mapper(s))")
    for idx, payload in enumerate(payloads, start=1):
        if len(payloads) > 1:
            print(f"--- mapper #{idx} ---")
        for table, count in sorted(payload.get("counts", {}).items()):
            print(f"  {table}: {count}")
        if payload.get("skipped"):
            for table, count in sorted(payload["skipped"].items()):
                print(f"  skipped {table}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legacy mysqldump importer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List discovered schema → dump path mapping")

    p_stats = sub.add_parser("parse-stats", help="Count rows per table (no DB writes)")
    p_stats.add_argument("--schema", help="Restrict to one schema (e.g. dsp_example)")
    p_stats.add_argument("--json", action="store_true", help="Emit JSONL instead of human text")

    p_cache = sub.add_parser("cache", help="Stream parse → JSONL fixtures under .legacy_cache/")
    p_cache.add_argument("schema", help="Schema name (e.g. dsp_example)")
    p_cache.add_argument(
        "--max-rows-per-table",
        type=int,
        default=None,
        help="Cap rows per table (useful for fast smoke runs on dsp_message etc)",
    )

    p_import = sub.add_parser("import", help="Run the registered mapper for one schema")
    p_import.add_argument("schema", help="Schema name (currently: dsp_bsp)")
    p_import.add_argument("--json", action="store_true", help="Emit JSON instead of human text")

    p_verify = sub.add_parser("verify", help="Sample legacy_object_mapping → confirm canonical_ref resolves")
    p_verify.add_argument("--tenant", default="sd-default", help="Tenant id (default: sd-default)")
    p_verify.add_argument("--strict", action="store_true", help="Exit non-zero when any unresolved row found")
    p_verify.add_argument("--json", action="store_true", help="Emit JSON instead of human text")

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "parse-stats":
        return cmd_parse_stats(args)
    if args.command == "cache":
        return cmd_cache(args)
    if args.command == "import":
        return cmd_import(args)
    if args.command == "verify":
        return cmd_verify(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
