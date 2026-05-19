#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
DUMPS_DIR="${ZW_BRAIN_LEGACY_DUMPS_DIR:-$REPO_ROOT/old/10示例数据}"
DATASTRUCTURE_DIR="${ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR:-$REPO_ROOT/old/12-datastructure}"
DB_PATH="${ZW_BRAIN_DB_PATH:-$REPO_ROOT/.data/zw_brain.db}"
REPORT_DIR="${ZW_BRAIN_ACCEPTANCE_REPORT_DIR:-$REPO_ROOT/.data/customer-acceptance}"

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
  "run: python3 -m venv .venv && .venv/bin/pip install -e ."
mkdir -p "$REPORT_DIR"

step "validate input artifacts"
[[ -d "$DUMPS_DIR" ]] || fail "legacy dumps dir not found: $DUMPS_DIR" \
  "set ZW_BRAIN_LEGACY_DUMPS_DIR or place dumps under old/10示例数据/"
[[ -d "$DATASTRUCTURE_DIR" ]] || fail "legacy datastructure dir not found: $DATASTRUCTURE_DIR" \
  "set ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR or place xmls under old/12-datastructure/"
for schema in "${REQUIRED_SCHEMAS[@]}"; do
  compgen -G "$DUMPS_DIR/dump-${schema}-*.sql" >/dev/null || fail \
    "missing dump for schema ${schema} under $DUMPS_DIR" \
    "客户机房 DBA 用 mysqldump 拉 dsp_${schema}.sql 放入 $DUMPS_DIR；样例见 old/10示例数据/"
done
for xml in "${REQUIRED_XMLS[@]}"; do
  [[ -f "$DATASTRUCTURE_DIR/$xml" ]] || fail \
    "missing datastructure file: $DATASTRUCTURE_DIR/$xml" \
    "从 dev-rules 仓 sync 最新 12-datastructure 或客户 IT 部门提供"
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
ok "db:      $DB_PATH"
ok "reports: $REPORT_DIR"
printf '\n[customer-acceptance] 下一步：\n'
printf '  - 跑 5 分钟客户演示：bash scripts/customer_demo_5min.sh\n'
printf '  - 详细验收 41 项：docs/deployment/handover-checklist.md\n'
printf '  - 启动完整服务（含 dashboard）：bash scripts/start-local.sh\n'
