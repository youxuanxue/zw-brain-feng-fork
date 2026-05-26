#!/usr/bin/env bash
# trial-up.sh — one-command internal env for product polish iterations
#
# 确定性自动化运营和运维杠杆点： every internal walkthrough, real-data regression, or
# trial dry-run goes through this script instead of being rebuilt by hand.
#
# Default flow:
#   1. clean SQLite DB at .data/zw_brain.db
#   2. legacy import for J1+J2+J3 schemas (skipping any whose dump is absent)
#   3. regenerate seed_snapshot.json from imported DB
#   4. start REST in background, wait for /health
#   5. main-link smoke (J1/J2/J3 minimum-set skills)
#   6. all-skill health check (callability + JSON-shape; no whitelist)
#   7. write JSON report to .data/trial-up-report.json
#   8. stop REST on exit
#
# Flags:
#   --no-reset      don't wipe DB before importing — exposes mapper-level
#                   non-idempotency by stacking imports onto existing rows.
#                   trial-up.sh itself stays repeatable; this is the probe.
#   --reset-cache   also wipe .legacy_cache/ on top of DB
#   --skip-import   reuse existing DB, just start + smoke
#   --skip-health   skip step 6 (all-skill health check)
#   -h, --help      this help

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
DB_PATH="$REPO_ROOT/.data/zw_brain.db"
STATE_PATH="$REPO_ROOT/.data/brain_state.json"
REPORT_PATH="$REPO_ROOT/.data/trial-up-report.json"
REST_LOG="$REPO_ROOT/.data/trial-up-rest.log"
REST_HOST="${ZW_BRAIN_REST_HOST:-127.0.0.1}"
REST_PORT="${ZW_BRAIN_REST_PORT:-8800}"
DUMPS_DIR="$REPO_ROOT/old/10示例数据"

# Schemas covering J1 (catalog) + J2 (apply/approve) + J3 (delivery/objection)
# + governance baseline + topic packages. Order matters: governance must
# precede catalog/exchange so org/region projections exist when downstream
# adapters resolve them.
DEFAULT_SCHEMAS="dsp_bsp dsp_catalog dsp_metaresource dsp_require dsp_handling dsp_example"
SCHEMAS="${ZW_BRAIN_TRIAL_SCHEMAS:-$DEFAULT_SCHEMAS}"

DO_RESET=1
RESET_CACHE=0
DO_IMPORT=1
DO_HEALTH=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-reset)     DO_RESET=0; shift ;;
        --reset-cache)  RESET_CACHE=1; shift ;;
        --skip-import)  DO_IMPORT=0; shift ;;
        --skip-health)  DO_HEALTH=0; shift ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "[trial-up] unknown arg: $1" >&2
            exit 64 ;;
    esac
done

REST_PID=""

cleanup() {
    local rc=$?
    if [[ -n "$REST_PID" ]] && kill -0 "$REST_PID" 2>/dev/null; then
        kill "$REST_PID" 2>/dev/null || true
        wait "$REST_PID" 2>/dev/null || true
    fi
    exit "$rc"
}
trap cleanup INT TERM EXIT

step() { printf '\n[trial-up] === %s ===\n' "$1"; }
ok()   { printf '[trial-up] ok: %s\n' "$1"; }
warn() { printf '[trial-up] WARN: %s\n' "$1" >&2; }
fail() { printf '[trial-up] FAIL: %s\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------

if [[ ! -x "$PYTHON" ]]; then
    fail "missing virtualenv python at $PYTHON (create .venv and install deps first)"
fi
mkdir -p "$REPO_ROOT/.data"

# ---------------------------------------------------------------------------
# step 1/6 clean
# ---------------------------------------------------------------------------

step "step 1/6 clean DB"
if [[ "$DO_IMPORT" == 0 ]]; then
    warn "--skip-import: leaving DB as-is (clean step skipped to avoid empty DB)"
elif [[ "$DO_RESET" == 1 ]]; then
    rm -f "$DB_PATH" "$STATE_PATH"
    ok "removed $DB_PATH and $STATE_PATH"
else
    warn "--no-reset: keeping existing DB (probes mapper idempotency)"
fi
if [[ "$RESET_CACHE" == 1 ]]; then
    rm -rf "$REPO_ROOT/.legacy_cache"
    ok "removed .legacy_cache/"
fi

# ---------------------------------------------------------------------------
# step 2/6 legacy import
# ---------------------------------------------------------------------------

step "step 2/6 legacy import"
imported=()
skipped=()
if [[ "$DO_IMPORT" == 1 ]]; then
    for schema in $SCHEMAS; do
        if compgen -G "$DUMPS_DIR/dump-${schema}-*.sql" > /dev/null; then
            "$PYTHON" "$REPO_ROOT/scripts/import_legacy_dumps.py" import "$schema" --json \
                > "$REPO_ROOT/.data/import-${schema}.json" \
                || fail "import $schema failed (see .data/import-${schema}.json)"
            imported+=("$schema")
            ok "imported $schema"
        else
            skipped+=("$schema")
            warn "no dump for $schema under $DUMPS_DIR — skipping"
        fi
    done
    if [[ ${#imported[@]} -eq 0 ]]; then
        warn "no schemas imported (mysqldump files absent locally?)"
    fi
else
    warn "--skip-import: leaving DB as-is"
fi

# ---------------------------------------------------------------------------
# step 3/6 regen seed
# ---------------------------------------------------------------------------

step "step 3/6 regenerate seed_snapshot.json"
if [[ -f "$DB_PATH" ]]; then
    "$PYTHON" "$REPO_ROOT/scripts/build_true_data_seed.py" \
        || fail "seed regeneration failed"
    ok "seed regenerated"
else
    warn "no DB to seed from — skipping (ui will fall back to hand-authored snapshot)"
fi

# ---------------------------------------------------------------------------
# step 4/6 start REST
# ---------------------------------------------------------------------------

step "step 4/6 start REST in background"
REST_HOST="$REST_HOST" REST_PORT="$REST_PORT" "$PYTHON" - <<'PY' >/dev/null 2>&1 \
    || fail "REST port $REST_HOST:$REST_PORT is already in use"
import os, socket
with socket.socket() as s:
    s.bind((os.environ["REST_HOST"], int(os.environ["REST_PORT"])))
PY
( cd "$REPO_ROOT" && exec "$PYTHON" -m zw_brain.entry.rest.server ) \
    > "$REST_LOG" 2>&1 &
REST_PID=$!

i=0
while (( i < 60 )); do
    if ! kill -0 "$REST_PID" 2>/dev/null; then
        echo "--- last 40 lines of $REST_LOG ---" >&2
        tail -n 40 "$REST_LOG" >&2 || true
        fail "REST process exited before becoming healthy"
    fi
    if "$PYTHON" - <<PY >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://$REST_HOST:$REST_PORT/health', timeout=1).read()
PY
    then
        ok "REST up at http://$REST_HOST:$REST_PORT (PID $REST_PID)"
        break
    fi
    sleep 0.5
    i=$((i+1))
done
if (( i >= 60 )); then
    echo "--- last 40 lines of $REST_LOG ---" >&2
    tail -n 40 "$REST_LOG" >&2 || true
    fail "REST did not become healthy after 30s"
fi

# ---------------------------------------------------------------------------
# step 5/6 main-link smoke (J1+J2+J3 minimum)
# ---------------------------------------------------------------------------

step "step 5/6 main-link smoke (J1+J2+J3)"
# Skills paired with minimum-valid payloads (driven by their input_schema.required).
# Format: <skill_id>=<json-payload>. data.search needs `query`; the rest take {}.
declare -a MAIN_LINK_PAIRS=(
    'data.search={"query":""}'
    'catalog.browse={}'
    'request.list={}'
    'delivery.list={}'
    'audit.list={}'
)
for pair in "${MAIN_LINK_PAIRS[@]}"; do
    skill="${pair%%=*}"
    payload="${pair#*=}"
    SKILL_ID="$skill" REST_URL="http://$REST_HOST:$REST_PORT/api/skills/$skill" \
    PAYLOAD="$payload" "$PYTHON" - <<'PY' >/dev/null 2>&1 \
        || fail "main-link smoke failed for $skill"
import json, os, urllib.request
req = urllib.request.Request(
    os.environ["REST_URL"],
    data=os.environ["PAYLOAD"].encode("utf-8"),
    headers={"content-type": "application/json"},
    method="POST",
)
resp = urllib.request.urlopen(req, timeout=10)
body = resp.read()
assert resp.status == 200, f"status {resp.status}"
json.loads(body)
PY
    ok "smoke $skill"
done

# J3 depth smoke: approve → supplement → summary → receipt → backflow → evidence replay.
# REQ/DLV-2026-04-25-0011 is the stable true-data golden chain in the seed.
REST_BASE="http://$REST_HOST:$REST_PORT" "$PYTHON" - <<'PY' >/dev/null 2>&1 \
    || fail "J3 depth smoke failed"
import json, os, urllib.request
base = os.environ["REST_BASE"]

def post(skill_id, payload):
    req = urllib.request.Request(
        f"{base}/api/skills/{skill_id}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    assert resp.status == 200, (skill_id, resp.status, body)
    return body

request_id = "REQ-2026-04-25-0011"
task_id = "DLV-2026-04-25-0011"
assert post("request.view", {"request_id": request_id})["status"] == "pending"
assert post("delivery.view", {"task_id": task_id})["requestId"] == request_id
approved = post("approval.review_decide", {"request_id": request_id, "decision": "approve", "role": "r2", "confirmed": True})
assert approved["result"]["status"] == "supplementing"
supplemented = post("supplement.submit", {"request_id": request_id, "role": "r3", "confirmed": True})
assert supplemented["result"]["status"] == "summary-pending"
summarized = post("summary.confirm", {"request_id": request_id, "role": "r5", "confirmed": True})
assert summarized["result"]["status"] == "completed"
reconciled = post("delivery.reconcile_receipt", {"task_id": task_id, "role": "r6", "confirmed": True})
assert reconciled["result"]["receipt_status"] == "reconciled"
confirmed = post("backflow.confirm", {"task_id": task_id, "role": "r6", "confirmed": True})
assert confirmed["result"]["status"] == "completed"
after = post("delivery.view", {"task_id": task_id})
assert after["receiptStatus"] == "reconciled"
assert after["backflow"]["status"] == "已确认"
evidence = post("audit.replay_evidence_chain", {"dispute_id": "DSP-2026-04-25-0003"})
assert evidence["evidenceChain"], "empty evidence chain"
assert evidence["auditEvents"], "empty audit events"
PY
ok "smoke J3 approve → supplement → summary → receipt → backflow → evidence replay"

# ---------------------------------------------------------------------------
# step 6/6 all-skill health check
# ---------------------------------------------------------------------------

if [[ "$DO_HEALTH" == 1 ]]; then
    step "step 6/6 all-skill health check"
    if "$PYTHON" "$REPO_ROOT/scripts/smoke_skills.py" \
            --host "$REST_HOST" --port "$REST_PORT" \
            --report "$REPORT_PATH"; then
        ok "all-skill health check passed (report: $REPORT_PATH)"
    else
        warn "unhealthy skills found — see $REPORT_PATH"
        echo "[trial-up] failing intentionally per no-whitelist policy: failed skills must be fixed, not hidden"
        exit 1
    fi
else
    warn "--skip-health: step 6 skipped"
fi

# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------

step "trial-up complete"
echo "Imported schemas: ${imported[*]:-(none)}"
[[ ${#skipped[@]} -gt 0 ]] && echo "Skipped (no dump): ${skipped[*]}"
echo "REST URL:  http://$REST_HOST:$REST_PORT"
echo "Report:    $REPORT_PATH"
echo "REST log:  $REST_LOG"
echo "Stopping REST..."
