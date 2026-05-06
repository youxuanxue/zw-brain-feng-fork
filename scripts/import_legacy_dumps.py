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

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "parse-stats":
        return cmd_parse_stats(args)
    if args.command == "cache":
        return cmd_cache(args)
    if args.command == "import":
        return cmd_import(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
