#!/usr/bin/env bash
# F8 B1 30 分钟客户演示验收脚本
#
# 一条命令把 ROLE_SECURITY_AUDIT + ROLE_BUSIAUDIT 两角色从 zero 带到 B1 全链路闭环：
#   B1.1 statistics + anomaly + accountability + investigation_summary
#   B1.2 review → enable → exposure_matrix → trust_level → rollback
#
# 退出码：
#   0 = 全链路成功
#   1 = 步骤异常 (Python driver 抛错)
#   3 = 超 30 分钟预算
#
# 业务方 + 安全审计员 sign-off 流程见 docs/customer-demo-b1.md。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/.data/customer-demo-b1"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/demo-$TS.log"
REPORT="$LOG_DIR/demo-$TS.json"

if [ ! -x "$PYTHON" ]; then
    echo "[demo-b1] .venv 未就位；先跑 'uv sync --extra dev'" >&2
    exit 1
fi

echo "[demo-b1] start at $TS, log=$LOG, report=$REPORT"
START_EPOCH=$(date +%s)

set +e
"$PYTHON" "$REPO_ROOT/scripts/customer_demo_b1.py" --report "$REPORT" 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))

echo "[demo-b1] finished rc=$RC, wall-elapsed=${ELAPSED}s"

if [ "$RC" -eq 0 ]; then
    echo "[demo-b1] ✓ 全链路成功；提交业务方 + 安全审计员 sign-off (见 docs/customer-demo-b1.md)"
fi

exit "$RC"
