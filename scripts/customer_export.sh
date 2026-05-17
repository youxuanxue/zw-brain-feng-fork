#!/usr/bin/env bash
# customer_export.sh — one-click legacy database export for zw-brain migration
#
# Modes
#   live mode  : mysqldump against a real MySQL host, then redact + bundle.
#                Requires ZW_BRAIN_DB_PASSWORD env var to be set.
#   dry-run    : skip mysqldump; postprocess a pre-existing dump directory
#                (typically `old/10示例数据/`). Used by tests and for
#                rehearsing the workflow before client-site rollout.
#
# Usage
#   ./scripts/customer_export.sh \
#       --db-host=192.0.2.10 --db-user=zw_export \
#       --output-dir=/var/zw-brain/export/B-2026-05-16-01 \
#       --batch-id=B-2026-05-16-01 --tenant=sd-default \
#       --schemas="dsp_catalog,dsp_metaresource,..."
#
#   ./scripts/customer_export.sh \
#       --from-dir=old/10示例数据 \
#       --output-dir=.data/export-dryrun/B-2026-05-16-01 \
#       --batch-id=B-2026-05-16-01 --tenant=sd-default
#
# Exit codes
#   0   success; manifest.json + redacted dumps in --output-dir
#   2   bad input / missing prerequisites
#   3   mysqldump or post-processing failure for one or more schemas
#   4   verify step failed after bundle
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

# Default schema set tracks what the in-repo mappers actually consume.
DEFAULT_SCHEMAS="dsp_app_center dsp_basesubject dsp_block dsp_bsp dsp_catalog dsp_connect dsp_example dsp_handling dsp_message dsp_metaresource dsp_monitor dsp_pdf dsp_perform dsp_pipelines dsp_require dsp_service data_resource"

DB_HOST=""
DB_PORT="3306"
DB_USER=""
OUTPUT_DIR=""
BATCH_ID=""
TENANT="sd-default"
FROM_DIR=""
SCHEMAS=""
DATASTRUCTURE_DIR="$REPO_ROOT/old/12-datastructure"
FORCE=0

usage() {
  grep '^# ' "$0" | sed 's/^# \{0,1\}//'
}

die() {
  echo "FATAL: $1" >&2
  exit "${2:-2}"
}

for arg in "$@"; do
  case "$arg" in
    --db-host=*) DB_HOST="${arg#*=}" ;;
    --db-port=*) DB_PORT="${arg#*=}" ;;
    --db-user=*) DB_USER="${arg#*=}" ;;
    --output-dir=*) OUTPUT_DIR="${arg#*=}" ;;
    --batch-id=*) BATCH_ID="${arg#*=}" ;;
    --tenant=*) TENANT="${arg#*=}" ;;
    --from-dir=*) FROM_DIR="${arg#*=}" ;;
    --schemas=*) SCHEMAS="${arg#*=}" ;;
    --datastructure-dir=*) DATASTRUCTURE_DIR="${arg#*=}" ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

[[ -n "$OUTPUT_DIR" ]] || die "--output-dir is required"
[[ -n "$BATCH_ID" ]] || die "--batch-id is required"

if [[ -n "$FROM_DIR" ]]; then
  echo "[customer-export] dry-run mode from: $FROM_DIR"
  [[ -d "$FROM_DIR" ]] || die "--from-dir not found: $FROM_DIR"
  RAW_DIR="$FROM_DIR"
else
  echo "[customer-export] live mode against: $DB_USER@$DB_HOST:$DB_PORT"
  [[ -n "$DB_HOST" ]] || die "--db-host is required in live mode (omit only with --from-dir)"
  [[ -n "$DB_USER" ]] || die "--db-user is required in live mode"
  [[ -n "${ZW_BRAIN_DB_PASSWORD:-}" ]] || die "ZW_BRAIN_DB_PASSWORD env var must be set in live mode"
  command -v mysqldump >/dev/null 2>&1 || die "mysqldump not found in PATH"
  RAW_DIR="$(mktemp -d -t zw-brain-export-raw-XXXXXX)"
  trap 'rm -rf "$RAW_DIR"' EXIT
  if [[ -z "$SCHEMAS" ]]; then SCHEMAS="$DEFAULT_SCHEMAS"; fi
  SCHEMAS="${SCHEMAS//,/ }"
  TS="$(date +%Y%m%d%H%M)"
  for schema in $SCHEMAS; do
    OUT="$RAW_DIR/dump-${schema}-${TS}.sql"
    echo "[customer-export] dumping schema $schema → $OUT"
    if ! MYSQL_PWD="$ZW_BRAIN_DB_PASSWORD" mysqldump \
        --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" \
        --single-transaction --quick --skip-lock-tables \
        --hex-blob --routines --no-tablespaces \
        --extended-insert \
        --skip-comments \
        "$schema" > "$OUT"; then
      die "mysqldump failed for schema $schema" 3
    fi
  done
fi

FORCE_FLAG=""
if [[ "$FORCE" == "1" ]]; then FORCE_FLAG="--force"; fi

mkdir -p "$OUTPUT_DIR"

echo "[customer-export] bundling + redacting → $OUTPUT_DIR"
"$PYTHON" "$REPO_ROOT/scripts/customer_export.py" bundle \
  --input-dir="$RAW_DIR" \
  --output-dir="$OUTPUT_DIR" \
  --batch-id="$BATCH_ID" \
  --tenant-id="$TENANT" \
  --datastructure-dir="$DATASTRUCTURE_DIR" \
  $FORCE_FLAG \
  || die "bundle step failed" 3

echo "[customer-export] verifying manifest hashes"
"$PYTHON" "$REPO_ROOT/scripts/customer_export.py" verify --batch-dir="$OUTPUT_DIR" \
  || die "verify step failed — manifest hashes do not match files on disk" 4

echo "[customer-export] OK"
echo "  batch_id=$BATCH_ID"
echo "  output_dir=$OUTPUT_DIR"
echo "  manifest=$OUTPUT_DIR/manifest.json"
