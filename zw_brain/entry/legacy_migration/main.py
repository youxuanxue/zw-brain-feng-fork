from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from zw_brain.adapters.legacy.migration_batch import MigrationError, MigrationOptions, run_acceptance_migration, run_migration, write_report
from zw_brain.adapters.legacy.tenant_normalizer import DEFAULT_TENANT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot legacy dump migration into the zw-brain canonical DB. "
            "The target PostgreSQL connection is taken from the ZW_BRAIN_DATABASE_URL "
            "environment variable (no per-run DB path/URL flag)."
        )
    )
    parser.add_argument("--dumps-dir", required=True, help="Directory containing dump-<schema>-<timestamp>.sql files")
    parser.add_argument("--tenant", default=DEFAULT_TENANT, help=f"Tenant id (default: {DEFAULT_TENANT})")
    parser.add_argument("--profile", default="customer-core-v1", help="Versioned migration profile")
    parser.add_argument("--reset-db", action="store_true", help="Drop and recreate the target DB before importing")
    parser.add_argument("--strict", action="store_true", help="Fail on missing required dumps, import failures, or unresolved mappings")
    parser.add_argument("--require-zero-conflicts", action="store_true", help="Treat conflicted legacy mappings as failures")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report planned target changes without writing projection tables")
    parser.add_argument("--acceptance", action="store_true", help="Run dry-run, apply, repeat apply, and write one acceptance report")
    parser.add_argument("--report", required=True, help="Path to write migration report JSON")
    args = parser.parse_args(argv)

    options = MigrationOptions(
        dumps_dir=Path(args.dumps_dir),
        tenant_id=args.tenant,
        profile=args.profile,
        reset_db=args.reset_db,
        strict=args.strict,
        require_zero_conflicts=args.require_zero_conflicts,
        dry_run=args.dry_run,
    )
    report_path = Path(args.report)
    try:
        report = run_acceptance_migration(options) if args.acceptance else run_migration(options)
    except MigrationError as exc:
        write_report(exc.report, report_path)
        print(json.dumps(exc.report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    write_report(report, report_path)
    print(json.dumps({"status": report["status"], "report": str(report_path)}, ensure_ascii=False))
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
