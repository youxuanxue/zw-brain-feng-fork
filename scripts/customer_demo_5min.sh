#!/usr/bin/env bash
# zw-brain 5 分钟客户演示路径（ITEM-02 of customer-delivery-final-mile）
#
# 一条命令把客户从 zero 带到『真数据找到 → 申请提交 → 审批通过 → 审计可证』。
# 5 段真数据 curl：ROLE_ORGAN_OPERATER 浏览 → 详情 → 申请 → ROLE_ORGAN_MANAGER 审批 → ROLE_BUSIAUDIT 审计。
# 角色码遵循 D23（2026-05-19）：r1-r8 退役，BSP 7-code ROLE_* 体系。
#
# Stop conditions:
#   - 任一 step 5xx 或 jq 解析失败 → exit 1
#   - REST 30s 内没起来 → exit 1
# Cleanup: trap EXIT 杀掉 REST 子进程。

set -euo pipefail

# Drop any inherited HTTP proxy — local REST is 127.0.0.1 and many dev envs route through 7890,
# which would 502 every /health probe and 5 demo curls.
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"
export no_proxy="$NO_PROXY"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
# Backend = PostgreSQL only. Target DB = resolved ZW_BRAIN_DATABASE_URL (defaults to
# local dev PG `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain`);
# start one with `docker compose up -d postgres`.
REST_HOST="${ZW_BRAIN_REST_HOST:-127.0.0.1}"
REST_PORT="${ZW_BRAIN_REST_PORT:-8800}"
LOG_DIR="$REPO_ROOT/.data/customer-demo"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/demo-$(date +%Y%m%d-%H%M%S).log"
REST_PID=""

# All output mirrored to log; trim later if > 600 lines.
exec > >(tee -a "$LOG") 2>&1

step() { printf '\n[demo-5min] ============== %s ==============\n' "$1"; }
ok()   { printf '[demo-5min] ok: %s\n' "$1"; }
note() { printf '[demo-5min] note: %s\n' "$1"; }
fail() {
  printf '[demo-5min] FAIL: %s\n' "$1" >&2
  if [[ -n "${2:-}" ]]; then printf '[demo-5min] next-step: %s\n' "$2" >&2; fi
  exit 1
}

cleanup() {
  local status=$?
  if [[ -n "$REST_PID" ]] && kill -0 "$REST_PID" 2>/dev/null; then
    kill "$REST_PID" 2>/dev/null || true
    wait "$REST_PID" 2>/dev/null || true
  fi
  if (( status == 0 )); then
    printf '\n[demo-5min] log saved: %s\n' "$LOG"
  else
    printf '\n[demo-5min] FAILED. log: %s\n' "$LOG" >&2
  fi
  exit "$status"
}
trap cleanup INT TERM EXIT

# ---------- preflight ----------
step "preflight"
[[ -x "$PYTHON" ]] || fail "missing virtualenv python at $PYTHON" \
  "run: python3 -m venv .venv && .venv/bin/pip install -e ."
command -v jq >/dev/null || fail "jq not installed" \
  "macOS: brew install jq ; Debian/Ubuntu: sudo apt install -y jq"
ok "venv + jq present"

if ! "$PYTHON" - <<'PY' "$REST_HOST" "$REST_PORT"
import socket, sys
host = sys.argv[1]; port = int(sys.argv[2])
with socket.socket() as s:
    s.settimeout(1)
    if s.connect_ex((host, port)) == 0:
        raise SystemExit(1)
PY
then
  fail "port $REST_HOST:$REST_PORT already in use" \
    "find owner: lsof -nP -iTCP:$REST_PORT -sTCP:LISTEN ; then kill it"
fi
ok "port $REST_HOST:$REST_PORT free"

# ---------- M0 真数据 acceptance bootstrap (idempotent) ----------
step "M0 真数据 acceptance bootstrap"
# PG-only: probe whether the resolved DB already holds real catalog rows. A
# populated catalog → skip the import; empty / fresh schema → run the importer.
# (No SQLite file-size heuristic — the backend is PostgreSQL.)
if "$PYTHON" - <<'PY' >/dev/null 2>&1
import sys
from sqlalchemy import text
from zw_brain.shared.db import create_session_factory
try:
    with create_session_factory()() as s:
        n = s.execute(text("SELECT COUNT(*) FROM catalog_entry")).scalar() or 0
except Exception:
    sys.exit(1)
sys.exit(0 if n > 0 else 1)
PY
then
  ok "已有 canonical db（catalog 非空，resolved ZW_BRAIN_DATABASE_URL）"
else
  note "canonical db 为空 / 未就绪；调用 scripts/customer_acceptance_up.sh 导入真数据"
  bash "$REPO_ROOT/scripts/customer_acceptance_up.sh" \
    || fail "customer_acceptance_up.sh 失败" \
       "请按其错误提示修复（缺 dump / 缺 datastructure / venv 依赖 / PG 未起），再重跑本脚本"
  ok "acceptance 完成"
fi

# ---------- start REST in dev-iam-bypass ----------
step "启动 REST (dev-iam-bypass，仅本机演示)"
export ZW_BRAIN_DEV_IAM_BYPASS=1
export ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only
export ZW_BRAIN_REST_HOST="$REST_HOST"
export ZW_BRAIN_REST_PORT="$REST_PORT"

(
  cd "$REPO_ROOT"
  exec "$PYTHON" -m zw_brain.entry.rest.server
) &
REST_PID=$!
ok "REST PID=$REST_PID"

# wait /health, ≤ 30s
HEALTH_URL="http://$REST_HOST:$REST_PORT/health"
for i in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" -o /dev/null 2>/dev/null; then
    ok "REST healthy @ $HEALTH_URL"; break
  fi
  if (( i == 60 )); then fail "REST 30s 内未健康" "查看 stderr / 端口 / venv 依赖"; fi
  sleep 0.5
done

API="http://$REST_HOST:$REST_PORT/api/skills"

# ---------- helper: curl + status check ----------
call() {
  local method="$1" url="$2" body="${3:-}"
  local resp http
  if [[ "$method" == "GET" ]]; then
    resp=$(curl -sS -w '\n__HTTP__:%{http_code}' "$url")
  else
    resp=$(curl -sS -X "$method" -H 'Content-Type: application/json' \
      -d "$body" -w '\n__HTTP__:%{http_code}' "$url")
  fi
  http=$(printf '%s\n' "$resp" | awk -F: '/^__HTTP__:/{print $2}')
  body=$(printf '%s\n' "$resp" | sed '/^__HTTP__:/d')
  printf '%s' "$body"
  if [[ "$http" != "200" ]]; then
    printf '\n[demo-5min] HTTP %s 非 200\n' "$http" >&2
    return 1
  fi
}

# ---------- 5 steps ----------
step "[1/5] ROLE_ORGAN_OPERATER 浏览：真目录（catalog.browse）"
# Jobs 视角：客户老板第一眼必须看到真业务目录（医保码信息 / 停车场信息 / 医疗救助信息 等），
# 不能看到 legacy 测试条目（'dhhddhhdddddd' / UUID hex 字符串）。
# 真业务目录名 99% 含『信息』关键字（见 .experiences/README.md 样例清单），用 query=信息 精准锁定。
# fallback：若 query 命中 0，退回原默认浏览。
BROWSE=$(call GET "$API/catalog.browse?lifecycle=all&limit=10&query=%E4%BF%A1%E6%81%AF&role=ROLE_ORGAN_OPERATER") \
  || fail "catalog.browse 失败" "确认 canonical db 存在且非空 (re-run scripts/customer_acceptance_up.sh)"
TOTAL=$(printf '%s' "$BROWSE" | jq -r '.total // 0')
if (( TOTAL == 0 )); then
  note "query=信息 命中 0，回退到默认浏览"
  BROWSE=$(call GET "$API/catalog.browse?lifecycle=all&limit=10&role=ROLE_ORGAN_OPERATER")
  TOTAL=$(printf '%s' "$BROWSE" | jq -r '.total // 0')
fi
# 选 active 中首条；title 在 query=信息 模式下已 implicit 过滤为真业务名
FIRST_CATALOG=$(printf '%s' "$BROWSE" | jq -r \
  'first(.items[] | select((.lifecycle_status // "") == "active") | (.catalog_code // .id)) // .items[0].catalog_code // empty')
FIRST_NAME=$(printf '%s' "$BROWSE" | jq -r \
  --arg c "$FIRST_CATALOG" 'first(.items[] | select((.catalog_code // .id) == $c) | (.title // .name)) // "(无)"')
printf '%s' "$BROWSE" | jq '{total, head: (.items[:3] | map({code: (.catalog_code // .id), title: (.title // .name), lifecycle_status, owner_org_id}))}'
ok "真目录命中=${TOTAL}（query=信息）; 演示首选='${FIRST_NAME}' (${FIRST_CATALOG})"
(( TOTAL > 0 )) || fail "catalog 为空" "重跑 scripts/customer_acceptance_up.sh"
[[ -n "$FIRST_CATALOG" ]] || fail "无 catalog_code" "看上一步 BROWSE 原文，可能 schema 变了"

step "[2/5] ROLE_ORGAN_OPERATER 详情：$FIRST_CATALOG 真目录字段（catalog.resource_view）"
VIEW_BODY=$(jq -n --arg rid "$FIRST_CATALOG" '{resource_id:$rid,role:"ROLE_ORGAN_OPERATER"}')
DETAIL=$(call POST "$API/catalog.resource_view" "$VIEW_BODY") \
  || fail "catalog.resource_view 失败 (resource_id=$FIRST_CATALOG)" \
     "在上一步输出里 jq '.items[].catalog_code' 看可用 code"
printf '%s' "$DETAIL" | jq '{id, name, status, fields_count: (.fields // [] | length), coverage}'
FIELD_COUNT=$(printf '%s' "$DETAIL" | jq '.fields // [] | length')
ok "真目录详情字段数=$FIELD_COUNT (status=$(printf '%s' "$DETAIL" | jq -r .status))"

step "[3/5] ROLE_ORGAN_OPERATER 申请：res-market-activity（application.resource.submit）"
SUBMIT_RESOURCE="res-market-activity"
SUBMIT_BODY=$(jq -n --arg rid "$SUBMIT_RESOURCE" --arg q "5 分钟客户演示 — 市营商环境专班复用市场主体活跃度" \
  '{resource_id:$rid,role:"ROLE_ORGAN_OPERATER",confirmed:true,query:$q}')
# 演示幂等：DB 跨重启保留 pending request。若 res-market-activity 已有 pending，复用之，跳过 submit。
REUSED=0
REQ_ID=""
LIST=$(call GET "$API/request.list?role=ROLE_ORGAN_OPERATER" 2>/dev/null || printf '{}')
EXISTING=$(printf '%s' "$LIST" | jq -r --arg rid "$SUBMIT_RESOURCE" \
  '.items[]? | select((.resourceId // .resource_id // "") == $rid and (.status // "") == "pending") | (.id // .request_id) // empty' | head -1)
if [[ -n "$EXISTING" ]]; then
  REQ_ID="$EXISTING"; REUSED=1
  note "已存在 pending 申请，复用：$REQ_ID（跨进程持久化预期行为）"
else
  SUBMIT=$(call POST "$API/application.resource.submit" "$SUBMIT_BODY") \
    || fail "application.resource.submit 失败" \
       "若 422 entity_not_found，检查 seed_snapshot 是否完整；若 409，跑 .data/brain_state.json 重置或换 resource_id"
  REQ_ID=$(printf '%s' "$SUBMIT" | jq -r '.result.request_id // .result.id // ""')
  [[ -n "$REQ_ID" ]] || fail "拿不到 request_id" "看上一段 SUBMIT 原文"
  printf '%s' "$SUBMIT" | jq '{ok, audit_id, request: {id: (.result.request_id // .result.id), status: .result.status}}'
fi
ok "$([[ $REUSED -eq 1 ]] && echo "复用 pending 申请" || echo "新建申请"): request_id=$REQ_ID"

step "[4/5] ROLE_ORGAN_MANAGER 审批：通过申请（approval.review_decide）"
APPROVE_BODY=$(jq -n --arg rid "$REQ_ID" \
  '{request_id:$rid,decision:"approve",role:"ROLE_ORGAN_MANAGER",confirmed:true}')
APPROVE=$(call POST "$API/approval.review_decide" "$APPROVE_BODY") \
  || fail "approval.review_decide 失败" "确认 request_id=$REQ_ID 仍为 pending（被多次审批会拒）"
printf '%s' "$APPROVE" | jq '{ok, audit_id, decision: .result.decision, status: .result.status}'
ok "审批通过：audit_id=$(printf '%s' "$APPROVE" | jq -r '.audit_id // "n/a"')"

step "[5/5] ROLE_BUSIAUDIT 审计：审计事件流（audit.list）"
AUDIT=$(call POST "$API/audit.list" '{"role":"ROLE_BUSIAUDIT"}') \
  || fail "audit.list 失败" "审计落库异常 → 排查 brain_state.json / audit repo"
EVT_COUNT=$(printf '%s' "$AUDIT" | jq '.items | length')
printf '%s' "$AUDIT" | jq '{count: (.items | length), tail5: (.items[-5:] | map({audit_id: .id, type, actor, time, target}))}'
ok "审计事件总数=$EVT_COUNT (含本次 OPERATER 提交/MANAGER 审批/BUSIAUDIT 查询)"

# ---------- summary ----------
step "demo done — 一句话总结"
cat <<EOF
  ROLE_ORGAN_OPERATER 浏览到 ${TOTAL} 条真目录条目（含 ${FIRST_NAME} 等）；
  ROLE_ORGAN_OPERATER 看到 ${FIRST_CATALOG} 详情（${FIELD_COUNT} 字段）；
  ROLE_ORGAN_OPERATER 提交申请 ${REQ_ID}；
  ROLE_ORGAN_MANAGER 一键通过；
  ROLE_BUSIAUDIT 审计回看到 ${EVT_COUNT} 条事件链。
  浏览器入口：http://${REST_HOST}:${REST_PORT}/  (用 dev-bypass 登录)
  剧本：docs/release-notes/customer-demo-5min.md
  完整 log：${LOG}
EOF
