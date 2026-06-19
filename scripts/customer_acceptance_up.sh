#!/usr/bin/env bash
# Rebuilds the canonical PostgreSQL DB from real customer dumps + datastructure XMLs.
#
# Backend = PostgreSQL only. The target DB is whatever `ZW_BRAIN_DATABASE_URL`
# resolves to (defaults to the local dev PG `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain`);
# bring one up with `docker compose up -d postgres`. Schema is built/migrated by
# `ensure_runtime_schema()` (alembic forward-migration, D58) before the import runs.
#
# Default mode is **non-strict**: missing-manifest rows in dsp_bsp governance
# (~15% of 52241) are business-level fail-closed (D6/D14 IAF baseline absent)
# and don't kill the seed rebuild. The adapter still writes one
# `adapter_run_record` per dump with `error_summary` non-None so the skip is
# auditable (no silent swallow). Canonical projection integrity is still
# enforced separately (`verify --strict --require-zero-conflicts`).
#
# Pass `--strict` (or set ZW_BRAIN_ACCEPTANCE_STRICT=1) when dumps are
# expected to be conflict-free (CI smoke / synthetic fixtures).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
DUMPS_DIR="${ZW_BRAIN_LEGACY_DUMPS_DIR:-$REPO_ROOT/old/10示例数据}"
DATASTRUCTURE_DIR="${ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR:-$REPO_ROOT/old/12-datastructure}"
REPORT_DIR="${ZW_BRAIN_ACCEPTANCE_REPORT_DIR:-$REPO_ROOT/.data/customer-acceptance}"

STRICT=0
if [[ "${ZW_BRAIN_ACCEPTANCE_STRICT:-0}" == "1" ]]; then
  STRICT=1
fi
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --help|-h)
      cat <<'USAGE'
customer_acceptance_up.sh — rebuild PostgreSQL seed DB from real customer dumps

Usage: bash scripts/customer_acceptance_up.sh [--strict]

  --strict    Fail on any partial_failure adapter run (synthetic-dump mode).
              Default is non-strict: warn-level business fail-closed allowed,
              technical errors still fail. Canonical verify is always strict.

DB target: ZW_BRAIN_DATABASE_URL (defaults to local dev PostgreSQL).
           Start it with `docker compose up -d postgres`.
USAGE
      exit 0
      ;;
    *) echo "[customer-acceptance] WARN: unknown arg $arg (use --help)" >&2 ;;
  esac
done

REQUIRED_SCHEMAS=(dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example)
REQUIRED_XMLS=(dsp_catalog.xml dsp_metaresource.xml dsp_connect.xml dsp_handling.xml dsp_bsp.xml)

step() { printf '\n[customer-acceptance] === %s ===\n' "$1"; }
ok() { printf '[customer-acceptance] ok: %s\n' "$1"; }
fail() {
  printf '[customer-acceptance] FAIL: %s\n' "$1" >&2
  if [[ -n "${2:-}" ]]; then
    printf '[customer-acceptance] next-step: %s\n' "$2" >&2
  fi
  exit 1
}

[[ -x "$PYTHON" ]] || fail "missing virtualenv python at $PYTHON" \
  "run: python3 -m venv .venv && .venv/bin/pip install -e '.[postgres]'"
mkdir -p "$REPORT_DIR"

step "resolve + reset target PostgreSQL schema"
# PG-only: build/reset the schema on the resolved ZW_BRAIN_DATABASE_URL before
# importing. A full rebuild needs a clean schema, so we go through the explicit
# destructive reset path (reset_and_upgrade gated by ZW_BRAIN_ALLOW_SCHEMA_RESET,
# D58). The acceptance rebuild is by definition data-disposable.
ZW_BRAIN_ALLOW_SCHEMA_RESET=1 "$PYTHON" - <<'PY' || fail "schema reset failed" \
  "确认 PostgreSQL 已起（docker compose up -d postgres）且 ZW_BRAIN_DATABASE_URL 可连"
from zw_brain.shared.db import get_database_url, reset_engine_cache
from zw_brain.shared.migrate import reset_and_upgrade

reset_engine_cache()
reset_and_upgrade()  # drop + alembic upgrade head (gated by ZW_BRAIN_ALLOW_SCHEMA_RESET)
print(f"[customer-acceptance] schema rebuilt on {get_database_url()}")
PY
ok "target schema rebuilt on resolved ZW_BRAIN_DATABASE_URL"

step "collect parse stats"
ZW_BRAIN_LEGACY_DUMPS_DIR="$DUMPS_DIR" \
  "$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" parse-stats --json \
  > "$REPORT_DIR/parse-stats.jsonl"
ok "parse stats saved to $REPORT_DIR/parse-stats.jsonl"

if [[ $STRICT -eq 1 ]]; then
  step "run STRICT acceptance migration (any partial_failure run fails)"
else
  step "run acceptance migration (warn-only partial_failure allowed; technical errors fail)"
fi
ZW_BRAIN_LEGACY_DUMPS_DIR="$DUMPS_DIR" \
  REPORT_PATH="$REPORT_DIR/migration-report.json" \
  ZW_BRAIN_ACCEPTANCE_STRICT="$STRICT" \
  "$PYTHON" - <<'PY'
import json
import os
import sys
from pathlib import Path
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_acceptance_migration

dumps_dir = Path(os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"])
report_path = Path(os.environ["REPORT_PATH"])
strict = os.environ.get("ZW_BRAIN_ACCEPTANCE_STRICT") == "1"

# PG-only: do not pin db_path (that was the SQLite file knob). Leaving it None
# makes the migration honor the resolved ZW_BRAIN_DATABASE_URL. The schema was
# already (re)built above, so the import targets a clean PG schema.
#
# Non-strict mode runs `run_acceptance_migration(strict=False)` so the outer
# wrapper doesn't raise MigrationError. Each stage internally still uses
# strict=True (hardcoded in migration_batch._run_stage) — its MigrationError
# is caught and folded into stage["errors"]. We classify those errors below.
report = run_acceptance_migration(
    MigrationOptions(dumps_dir=dumps_dir, strict=strict)
)
report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def _mapper_counts(report_dict: dict) -> tuple[int, int, int, dict[str, int]]:
    """Walk imports → mappers → counts/issues; return technical/warn totals."""
    technical_error_rows = 0
    technical_issues = 0
    warn_issues = 0
    warn_rows_breakdown: dict[str, int] = {}
    for stage_name, stage in (report_dict.get("stages") or {}).items():
        for imp in stage.get("imports") or []:
            for mapper in imp.get("mappers") or []:
                for key, value in (mapper.get("counts") or {}).items():
                    if str(key).endswith(".errors"):
                        technical_error_rows += int(value)
                for issue in mapper.get("issues") or []:
                    severity = str(issue.get("severity") or "error")
                    if severity == "warn":
                        warn_issues += 1
                        detail = issue.get("detail") or {}
                        row_count = int(detail.get("row_count") or 1)
                        key = (
                            f"{stage_name}.{imp.get('schema')}."
                            f"{issue.get('table')}.{issue.get('type')}"
                        )
                        warn_rows_breakdown[key] = warn_rows_breakdown.get(key, 0) + row_count
                    else:
                        technical_issues += 1
    return technical_error_rows, technical_issues, warn_issues, warn_rows_breakdown


tech_rows, tech_issues, warn_issues, warn_rows_breakdown = _mapper_counts(report)

if warn_issues:
    total_skipped_rows = sum(warn_rows_breakdown.values())
    print(
        f"[customer-acceptance] WARN: {warn_issues} business-level fail-closed issue(s)"
        f" — ~{total_skipped_rows} rows skipped on purpose:",
        file=sys.stderr,
    )
    top = sorted(warn_rows_breakdown.items(), key=lambda kv: kv[1], reverse=True)[:5]
    for key, rows in top:
        print(f"[customer-acceptance] WARN:   {rows} rows — {key}", file=sys.stderr)
    print(
        "[customer-acceptance] WARN:   detail: query adapter_run_record.error_summary"
        f" or read {report_path}",
        file=sys.stderr,
    )

# Strict: any non-succeeded status fails.
# Non-strict: only technical errors (counts[*.errors] > 0 OR error-severity issues > 0) fail.
status = report.get("status")
if strict:
    if status != "succeeded":
        print(f"[customer-acceptance] FAIL: strict mode status={status}", file=sys.stderr)
        raise SystemExit(2)
else:
    if tech_rows or tech_issues:
        print(
            f"[customer-acceptance] FAIL: {tech_rows} technical-error rows +"
            f" {tech_issues} error-severity issues across stages",
            file=sys.stderr,
        )
        for stage_name, stage in (report.get("stages") or {}).items():
            for err in stage.get("errors") or []:
                print(f"[customer-acceptance] FAIL:   {stage_name}: {err}", file=sys.stderr)
        raise SystemExit(2)
PY
if [[ $STRICT -eq 1 ]]; then
  ok "strict acceptance migration passed"
else
  ok "acceptance migration passed (warn-level business skips logged above are by design)"
fi

step "verify canonical mapping integrity"
"$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" verify --strict --require-zero-conflicts --json \
  > "$REPORT_DIR/verify-report.json"
ok "verification report saved to $REPORT_DIR/verify-report.json"

step "runtime smoke on imported DB with offline legacy source"
OFFLINE_SOURCE="$REPORT_DIR/legacy-source-offline"
mkdir -p "$OFFLINE_SOURCE"
ZW_BRAIN_LEGACY_DUMPS_DIR="$OFFLINE_SOURCE" \
  "$PYTHON" - <<'PY' > "$REPORT_DIR/runtime-smoke.json"
import json
from zw_brain.command.runtime import get_service, reset_service

# Role codes follow D23 (2026-05-19): r1-r8 retired, BSP 7-code system in use.
# See zw_brain/domain/policy.py: ROLE_ORGAN_OPERATER=普通用户, ROLE_ORGAN_MANAGER=机构管理者,
# ROLE_BUSIAUDIT=业务审计员.

reset_service()
service = get_service()
browse = service.invoke_skill("catalog.browse", {"lifecycle": "all", "role": "ROLE_ORGAN_OPERATER"})
assert browse.get("items"), "empty catalog browse — seed DB has no catalog entries"

# Pick the first browse item's catalog_code so the per-resource probes work on
# whatever dump corpus we built (real customer dump OR synthetic test fixtures).
# Previously these probed hardcoded "BASE-POP-001" which only exists in the
# `customer_demo_5min.sh` synthetic fixtures and breaks on real dumps.
first = browse["items"][0]
probe_code = first.get("catalog_code") or first.get("resource_code")
assert probe_code, f"first catalog browse item has no catalog_code/resource_code: {first}"

results = {
    "catalog_browse": browse,
    "catalog_detail": service.invoke_skill("catalog.resource_view", {"resource_id": probe_code, "role": "ROLE_ORGAN_OPERATER"}),
    "metadata": service.invoke_skill("metadata.catalog_item.query", {"catalog_code": probe_code, "role": "ROLE_ORGAN_MANAGER"}),
    "provider": service.invoke_skill("provider.view", {"role": "ROLE_ORGAN_MANAGER"}),
    "zone": service.invoke_skill("zone.view", {"zone_id": "business", "role": "ROLE_ORGAN_OPERATER"}),
    "stats": service.invoke_skill("ops.catalog.statistics.query", {"role": "ROLE_BUSIAUDIT"}),
}
# Loose invariants — runtime serves requests, not specific synthetic states:
assert "fieldBindingSummary" in (results["catalog_detail"] or {}), "catalog_detail missing fieldBindingSummary"
assert "summary" in (results["metadata"] or {}), "metadata missing summary"
assert results["provider"]["repository"]["resourceCatalogCode"] == results["zone"]["repository"]["resourceCatalogCode"]
assert results["stats"]["summary"]["projection_only"] is True
print(json.dumps(results, ensure_ascii=False))
PY
ok "runtime smoke passed with offline legacy source"

step "done"
ok "db:      resolved ZW_BRAIN_DATABASE_URL (PostgreSQL)"
ok "reports: $REPORT_DIR"
printf '\n[customer-acceptance] 下一步：\n'
printf '  - 跑 5 分钟客户演示：bash scripts/customer_demo_5min.sh\n'
printf '  - 详细验收 41 项：docs/deployment/handover-checklist.md\n'
printf '  - 启动完整服务：bash scripts/start-local.sh\n'
