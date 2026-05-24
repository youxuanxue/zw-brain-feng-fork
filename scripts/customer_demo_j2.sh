#!/usr/bin/env bash
# F6 J2 30 分钟客户演示验收脚本
#
# 一条命令把 ROLE_ORGAN_OPERATER / MANAGER / BUSIAUDIT 三角色带过 J2 全链路：
#   在线编制 → 资源挂接 (table 物化真数据) → 3 层默认审批 (F1)
#   → publish + 自动重复率检测 (F3) → 异议接收 + 提供方响应 + 评价 (F4)
#
# 退出码：
#   0 = 全链路成功
#   1 = 步骤异常 (Python driver 抛错)
#   2 = assertion 失败
#   3 = 超 30 分钟预算
#
# 业务方 sign-off 流程见 docs/customer-demo-j2.md。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/.data/customer-demo-j2"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/demo-$TS.log"
REPORT="$LOG_DIR/demo-$TS.json"

if [ ! -x "$PYTHON" ]; then
    echo "[demo-j2] .venv 未就位；先跑 'uv sync --extra dev'" >&2
    exit 1
fi

if [ ! -f "$REPO_ROOT/.data/zw_brain.db" ]; then
    echo "[demo-j2] .data/zw_brain.db 不存在；先跑 'bash scripts/customer_acceptance_up.sh' 灌 M0 真数据" >&2
    exit 1
fi

echo "[demo-j2] start at $TS, log=$LOG, report=$REPORT"
START_EPOCH=$(date +%s)

set +e
"$PYTHON" "$REPO_ROOT/scripts/customer_demo_j2.py" --report "$REPORT" 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))

echo "[demo-j2] finished rc=$RC, wall-elapsed=${ELAPSED}s"

if [ "$RC" -eq 0 ]; then
    echo "[demo-j2] ✓ 全链路成功；提交业务方 sign-off (见 docs/customer-demo-j2.md)"
fi

exit "$RC"
