#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
DUMPS_DIR="${ZW_BRAIN_LEGACY_DUMPS_DIR:-$REPO_ROOT/old/10示例数据}"
DATASTRUCTURE_DIR="${ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR:-$REPO_ROOT/old/12-datastructure}"
DB_PATH="${ZW_BRAIN_DB_PATH:-$REPO_ROOT/.data/customer_acceptance.db}"
REPORT_DIR="${ZW_BRAIN_ACCEPTANCE_REPORT_DIR:-$REPO_ROOT/.data/customer-acceptance}"

REQUIRED_SCHEMAS=(dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example)
REQUIRED_XMLS=(dsp_catalog.xml dsp_metaresource.xml dsp_connect.xml dsp_handling.xml dsp_bsp.xml)

step() { printf '\n[customer-acceptance] === %s ===\n' "$1"; }
ok() { printf '[customer-acceptance] ok: %s\n' "$1"; }
fail() { printf '[customer-acceptance] FAIL: %s\n' "$1" >&2; exit 1; }

[[ -x "$PYTHON" ]] || fail "missing virtualenv python at $PYTHON"
mkdir -p "$REPORT_DIR"

step "validate input artifacts"
[[ -d "$DUMPS_DIR" ]] || fail "legacy dumps dir not found: $DUMPS_DIR"
[[ -d "$DATASTRUCTURE_DIR" ]] || fail "legacy datastructure dir not found: $DATASTRUCTURE_DIR"
for schema in "${REQUIRED_SCHEMAS[@]}"; do
  compgen -G "$DUMPS_DIR/dump-${schema}-*.sql" >/dev/null || fail "missing dump for schema ${schema} under $DUMPS_DIR"
done
for xml in "${REQUIRED_XMLS[@]}"; do
  [[ -f "$DATASTRUCTURE_DIR/$xml" ]] || fail "missing datastructure file: $DATASTRUCTURE_DIR/$xml"
done
ok "required dumps + datastructure files are present"

step "collect parse stats"
ZW_BRAIN_LEGACY_DUMPS_DIR="$DUMPS_DIR" \
  "$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" parse-stats --json \
  > "$REPORT_DIR/parse-stats.jsonl"
ok "parse stats saved to $REPORT_DIR/parse-stats.jsonl"

step "run strict acceptance migration"
ZW_BRAIN_LEGACY_DUMPS_DIR="$DUMPS_DIR" ZW_BRAIN_DB_PATH="$DB_PATH" REPORT_PATH="$REPORT_DIR/migration-report.json" \
  "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path
from zw_brain.adapters.legacy.migration_batch import MigrationOptions, run_acceptance_migration

dumps_dir = Path(os.environ["ZW_BRAIN_LEGACY_DUMPS_DIR"])
db_path = Path(os.environ["ZW_BRAIN_DB_PATH"])
report_path = Path(os.environ["REPORT_PATH"])
report = run_acceptance_migration(MigrationOptions(dumps_dir=dumps_dir, db_path=db_path, strict=True))
report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
if report.get("status") != "succeeded":
    raise SystemExit(2)
PY
ok "strict acceptance migration passed"

step "verify canonical mapping integrity"
ZW_BRAIN_DB_PATH="$DB_PATH" \
  "$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" verify --strict --require-zero-conflicts --json \
  > "$REPORT_DIR/verify-report.json"
ok "verification report saved to $REPORT_DIR/verify-report.json"

step "runtime smoke on imported DB with offline legacy source"
OFFLINE_SOURCE="$REPORT_DIR/legacy-source-offline"
mkdir -p "$OFFLINE_SOURCE"
ZW_BRAIN_DB_PATH="$DB_PATH" ZW_BRAIN_LEGACY_DUMPS_DIR="$OFFLINE_SOURCE" \
  "$PYTHON" - <<'PY' > "$REPORT_DIR/runtime-smoke.json"
import json
from zw_brain.command.runtime import get_service, reset_service

reset_service()
service = get_service()
results = {
    "catalog_browse": service.invoke_skill("catalog.browse", {"lifecycle": "all", "role": "r1"}),
    "catalog_detail": service.invoke_skill("catalog.resource_view", {"resource_id": "BASE-POP-001", "role": "r1"}),
    "metadata": service.invoke_skill("metadata.catalog_item.query", {"catalog_code": "BASE-POP-001", "role": "r7"}),
    "provider": service.invoke_skill("provider.view", {"role": "r7"}),
    "zone": service.invoke_skill("zone.view", {"zone_id": "business", "role": "r7"}),
    "stats": service.invoke_skill("ops.catalog.statistics.query", {"role": "r8"}),
}
assert results["catalog_browse"]["items"], "empty catalog browse"
assert results["catalog_detail"]["fieldBindingSummary"]["diagnosis"] == "ok"
assert results["metadata"]["summary"]["diagnosis"] == "ok"
assert results["provider"]["repository"]["resourceCatalogCode"] == results["zone"]["repository"]["resourceCatalogCode"]
assert results["stats"]["summary"]["projection_only"] is True
print(json.dumps(results, ensure_ascii=False))
PY
ok "runtime smoke passed with offline legacy source"

step "done"
echo "db:      $DB_PATH"
echo "reports: $REPORT_DIR"
