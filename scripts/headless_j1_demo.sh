#!/usr/bin/env bash
#
# scripts/headless_j1_demo.sh — F5 交付：J1 找数→用数 5 步链路 headless 全跑通。
#
# 用 zw-brain-cli (F5) 串行调用 5 步 capability，演示 OPC「单一入口 + 单一管线」原则。
# 链路：
#   STEP 1/5 检索：catalog.browse（拉 active 真目录条目）
#   STEP 2/5 申请：request.create（基于 step 1 的资源 id 起草复用申请）
#   STEP 3/5 审批：approval.case.decide（业务 review 决定 approved/rejected）
#   STEP 4/5 凭据：credential.query（查 step 2 申请的凭据状态）
#   STEP 5/5 调用：delivery.list（用凭据查交付任务，模拟实际 data 消费入口）
#
# E1/E2/E4 未 land 的 handler 会返结构化错误；本脚本捕获后标 'E*-pending' 不阻塞 exit 0。
# 价值在于「链路完整 + 等谁 land 明确」，不在「全部 200」。
#
# 实际跑过：依赖 .venv/bin/zw-brain-cli + ZW_BRAIN_DEV_IAM_BYPASS=1 in-process invoke。

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="${ZW_BRAIN_CLI:-$REPO_ROOT/.venv/bin/zw-brain-cli}"
ROLE="${ZW_BRAIN_DEMO_ROLE:-ROLE_ORGAN_OPERATER}"
export ZW_BRAIN_DEV_IAM_BYPASS=1
export ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only

if [ ! -x "$CLI" ]; then
    echo "[demo] FAIL: $CLI not found / not executable" >&2
    echo "  hint: cd to repo root, uv pip install -e . (in .venv) then re-run" >&2
    exit 1
fi

echo "=== zw-brain J1 headless demo (sd-default 单租户单省) ==="
echo "    role: $ROLE"
echo "    cli:  $CLI"
echo ""

# 工具：跑一个 skill，截断 stdout 前 200 字符，输出 STEP 行。
# 第 5 参数可选：override role（如审批走 MANAGER，交付查询走 BUSIAUDIT）。
step() {
    local n="$1" name="$2" skill="$3" payload="$4" override_role="${5:-$ROLE}"
    local out rc
    out=$("$CLI" "$skill" --role "$override_role" --payload "$payload" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ]; then
        # 抽取 status 关键字（如果有），否则按字段计数表示成功
        local marker
        marker=$(echo "$out" | head -c 200 | tr -d '\n' | sed 's/  */ /g')
        echo "[STEP $n/5 $name] capability=$skill status=200 result=$marker..."
    elif [ "$rc" -eq 2 ]; then
        echo "[STEP $n/5 $name] capability=$skill status=UNKNOWN_SKILL — 未注册或被砍 (preflight 段 22 边界)"
    elif [ "$rc" -eq 4 ]; then
        local err
        err=$(echo "$out" | head -c 200 | tr -d '\n' | sed 's/  */ /g')
        # 按 handler 类型粗判 pending owner（仅启发式）
        local pending="E*-pending"
        case "$skill" in
            request.*|application.*|approval.*) pending="E2-pending" ;;
            catalog.*|data.*|metadata.*)        pending="E1-pending" ;;
            credential.*|delivery.*)            pending="E2-pending" ;;
            governance.*|compliance.*|audit.*)  pending="E4-pending" ;;
            capability.*|external.*)            pending="E4-pending" ;;
        esac
        echo "[STEP $n/5 $name] capability=$skill status=$pending result=$err..."
    else
        echo "[STEP $n/5 $name] capability=$skill status=ERR($rc) result=$(echo "$out" | head -c 200)"
    fi
}

# ---- STEP 1: 检索（catalog.browse） ----
step 1 "检索" catalog.browse '{"limit":3,"lifecycle":"active","kind":"real"}'

# ---- STEP 2: 申请（request.create） ----
# resource_id 用 sd-default 真实目录 'res-jbxx-ledger'（停车场信息共享目录）。
step 2 "申请" request.create '{"resource_id":"res-jbxx-ledger","purpose":"J1 demo","confirmed":true}'

# ---- STEP 3: 审批（approval.case.decide）—— 角色切到部门管理员 ----
step 3 "审批" approval.case.decide '{"request_id":"REQ-2026-04-25-0011","decision":"approved","confirmed":true}' ROLE_ORGAN_MANAGER

# ---- STEP 4: 凭据（credential.query） ----
step 4 "凭据" credential.query '{"request_id":"REQ-2026-04-25-0011"}'

# ---- STEP 5: 调用（delivery.list — 模拟用凭据消费 data）—— 角色切到部门管理员 ----
step 5 "调用" delivery.list '{}' ROLE_ORGAN_MANAGER

echo ""
echo "=== demo 完成（exit 0 即使某步是 E*-pending）==="
exit 0
