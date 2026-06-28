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


def cmd_verify(args: argparse.Namespace) -> int:
    from zw_brain.adapters.legacy.verification import verify_legacy_migration
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    tenant = args.tenant or "sd-default"
    report = verify_legacy_migration(
        tenant_id=tenant,
        require_zero_conflicts=getattr(args, "require_zero_conflicts", False),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"verify tenant={tenant}  total_mappings={report['total_mappings']}  total_unresolved={report['total_unresolved']}  total_conflicted={report['total_conflicted']}")
        print(f"{'canonical_type':<36} {'mapped':>8} {'resolved':>10} {'unresolved':>12} {'conflicted':>12}  sample_missing")
        for row in report["by_type"]:
            sample_str = ", ".join(row["sample_unresolved"]) if row["sample_unresolved"] else ""
            print(f"  {row['canonical_type']:<34} {row['mapped']:>8} {row['resolved']:>10} {row['unresolved']:>12} {row['conflicted']:>12}  {sample_str}")
    if args.strict and report["failed"]:
        return 2
    return 0


# P0-C：现场最常需要补 manifest 的 issue 类型（其他 issue 是数据/流程问题，落 csv 帮助小）
_DEFAULT_UNMAPPED_ISSUE_TYPES: tuple[str, ...] = (
    "unmapped_permission",  # 旧权限未在 capability-mapping-manifest 命中 → 补 manifest
    "missing_role_mapping",  # 旧 role 未在 role-mapping-manifest 命中 → 补 manifest
    "iam_account_missing",  # IAM 未注入 / 占位 sub fail-closed → 走 ingest 流程或催 IAM
    "missing_org_relationship",  # 用户无组织绑定 → 补 pub_user_organ 数据或人工裁决
)


def _filter_issues(issues: list[dict], allowed_types: set[str]) -> list[dict]:
    if "all" in allowed_types:
        return list(issues)
    return [i for i in issues if str(i.get("type") or "") in allowed_types]


def _write_unmapped_csv(path: Path, issues: list[dict]) -> int:
    """落 csv，按 (type, table, legacy_ref) 排序便于 diff。返回行数。"""
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        issues,
        key=lambda i: (str(i.get("type") or ""), str(i.get("table") or ""), str(i.get("legacy_ref") or "")),
    )
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["issue_type", "table", "legacy_ref", "detail_json"], lineterminator="\n")
        writer.writeheader()
        for issue in rows:
            writer.writerow(
                {
                    "issue_type": str(issue.get("type") or ""),
                    "table": str(issue.get("table") or ""),
                    "legacy_ref": str(issue.get("legacy_ref") or ""),
                    "detail_json": json.dumps(issue.get("detail") or {}, ensure_ascii=False),
                }
            )
    return len(rows)


def cmd_import(args: argparse.Namespace) -> int:
    from zw_brain.shared.migrate import ensure_runtime_schema

    ensure_runtime_schema()
    runner = LegacyImportRunner(only_clean=getattr(args, "only_clean", False))
    result = runner.import_schema(args.schema)
    if result is None:
        print(f"no mapper registered for schema: {args.schema}", file=sys.stderr)
        return 1
    stats_list = result if isinstance(result, list) else [result]
    payloads = [(s.to_dict() if hasattr(s, "to_dict") else s) for s in stats_list]

    # P0-C：可选落 unmapped csv 供现场补 manifest
    if args.unmapped_csv is not None:
        allowed_types = set((args.issue_types or ",".join(_DEFAULT_UNMAPPED_ISSUE_TYPES)).split(","))
        allowed_types = {t.strip() for t in allowed_types if t.strip()}
        all_issues: list[dict] = []
        for payload in payloads:
            all_issues.extend(_filter_issues(list(payload.get("issues") or []), allowed_types))
        count = _write_unmapped_csv(args.unmapped_csv, all_issues)
        print(
            f"unmapped csv: {args.unmapped_csv} ({count} issue(s); types={sorted(allowed_types)})",
            file=sys.stderr,
        )

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
    p_import.add_argument(
        "--only-clean",
        action="store_true",
        help="只导入符合 zw-brain 标准的干净业务记录（目录/资源/申请）；不达标的跳过并记 stats.skip(<table>.unclean:<reason>)。治理基线（机构/区划/字典/actor）不过滤。",
    )
    p_import.add_argument(
        "--unmapped-csv",
        type=Path,
        default=None,
        help="把 mapper 产出的 issue 落 csv 方便现场补 manifest（默认范围：unmapped_permission / missing_role_mapping / iam_account_missing / missing_org_relationship）",
    )
    p_import.add_argument(
        "--issue-types",
        default=None,
        help="逗号分隔的 issue type（覆盖默认范围）；写 'all' 输出全部 issue。仅当 --unmapped-csv 设置时生效。",
    )

    p_verify = sub.add_parser("verify", help="Sample legacy_object_mapping → confirm canonical_ref resolves")
    p_verify.add_argument("--tenant", default="sd-default", help="Tenant id (default: sd-default)")
    p_verify.add_argument("--strict", action="store_true", help="Exit non-zero when verification fails")
    p_verify.add_argument("--require-zero-conflicts", action="store_true", help="Treat conflicted mappings as verification failures")
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
