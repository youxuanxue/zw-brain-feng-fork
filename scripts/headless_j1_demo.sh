#!/usr/bin/env bash
#
# scripts/headless_j1_demo.sh — F5 交付：J1 找数→用数 5 步链路 headless 全跑通。
#
# 任一步 capability 非 0 退出 → exit 1（去假绿）。
# 链路：catalog.browse → request.create → approval.case.decide → credential.query → delivery.list
#
# 幂等：seed/CI 若 res-jbxx-ledger 已有在途或已批准申请，复用既有 request_id 继续后续步。

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="${ZW_BRAIN_CLI:-$REPO_ROOT/.venv/bin/zw-brain-cli}"
ROLE="${ZW_BRAIN_DEMO_ROLE:-ROLE_ORGAN_OPERATER}"
export ZW_BRAIN_DEV_IAM_BYPASS=1
export ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only

FAILED=0

if [ ! -x "$CLI" ]; then
    echo "[demo] FAIL: $CLI not found / not executable" >&2
    exit 1
fi

echo "=== zw-brain J1 headless demo (sd-default 单租户单省) ==="
echo "    role: $ROLE"
echo "    cli:  $CLI"
echo ""

invoke_skill() {
    local skill="$1" payload="$2" override_role="${3:-$ROLE}"
    "$CLI" "$skill" --role "$override_role" --payload "$payload" 2>&1
}

report_step() {
    local n="$1" name="$2" skill="$3" rc="$4" out="$5"
    local marker
    marker=$(echo "$out" | head -c 200 | tr -d '\n' | sed 's/  */ /g')
    if [ "$rc" -eq 0 ]; then
        echo "[STEP $n/5 $name] capability=$skill status=200 result=$marker..."
        return 0
    fi
    echo "[STEP $n/5 $name] capability=$skill status=ERR($rc) result=$marker..." >&2
    FAILED=1
    return 1
}

report_step_note() {
    local n="$1" name="$2" skill="$3" note="$4"
    echo "[STEP $n/5 $name] capability=$skill status=200 note=$note"
}

extract_request_id() {
    python3 -c 'import json,sys; d=json.load(sys.stdin); r=d.get("result") or d; print(r.get("request_id") or r.get("result",{}).get("request_id",""))'
}

extract_req_from_text() {
    python3 -c 'import re,sys; m=re.search(r"REQ-[A-Z0-9-]+", sys.stdin.read()); print(m.group(0) if m else "")'
}

# ---- STEP 1 ----
OUT=$(invoke_skill catalog.browse '{"limit":3,"lifecycle":"active","kind":"real"}')
RC=$?
report_step 1 "检索" catalog.browse "$RC" "$OUT" || true

# ---- STEP 2 ----
OUT=$(invoke_skill request.create '{"resource_id":"res-jbxx-ledger","purpose":"J1 headless demo","confirmed":true}')
RC=$?
REQ_ID=""
if [ "$RC" -eq 0 ]; then
    REQ_ID=$(printf '%s' "$OUT" | extract_request_id)
    report_step 2 "申请" request.create "$RC" "$OUT" || true
elif printf '%s' "$OUT" | grep -qE 'active request already exists|InvalidStateError'; then
    REQ_ID=$(printf '%s' "$OUT" | extract_req_from_text)
    if [ -n "$REQ_ID" ]; then
        report_step_note 2 "申请" request.create "reused-existing-$REQ_ID"
    else
        report_step 2 "申请" request.create "$RC" "$OUT" || true
    fi
else
    report_step 2 "申请" request.create "$RC" "$OUT" || true
fi
if [ -z "$REQ_ID" ]; then
    echo "[STEP 2/5 申请] FAIL: could not extract request_id" >&2
    FAILED=1
    REQ_ID="REQ-UNSET"
fi

# ---- STEP 3 ----
OUT=$(invoke_skill approval.case.decide "{\"request_id\":\"$REQ_ID\",\"decision\":\"approve_reuse\",\"confirmed\":true}" ROLE_ORGAN_MANAGER)
RC=$?
if [ "$RC" -eq 0 ]; then
    report_step 3 "审批" approval.case.decide "$RC" "$OUT" || true
elif printf '%s' "$OUT" | grep -qE 'not pending approval|already granted|InvalidStateError'; then
    report_step_note 3 "审批" approval.case.decide "already-granted-$REQ_ID"
else
    report_step 3 "审批" approval.case.decide "$RC" "$OUT" || true
fi

# ---- STEP 4 ----
OUT=$(invoke_skill credential.query "{\"request_id\":\"$REQ_ID\"}")
RC=$?
report_step 4 "凭据" credential.query "$RC" "$OUT" || true

# ---- STEP 5 ----
OUT=$(invoke_skill delivery.list '{}' ROLE_ORGAN_MANAGER)
RC=$?
report_step 5 "调用" delivery.list "$RC" "$OUT" || true

echo ""
if [ "$FAILED" -ne 0 ]; then
    echo "=== demo 失败（至少一步 capability 非 200）==="
    exit 1
fi
echo "=== demo 完成（5/5 全绿）==="
exit 0
