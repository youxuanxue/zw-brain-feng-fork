#!/usr/bin/env bash
# F9 J1 30 分钟客户演示验收脚本
#
# 一条命令把 ROLE_BUSIAUDIT 角色从 zero 带到 J1 全链路闭环：
#   P2 搜索 → P3 草拟+审批 → P4 凭据+样例+解释 → 异议 5 维度 catalog 闭环
#
# 退出码：
#   0 = 全链路成功
#   1 = 步骤异常 (Python driver 抛错)
#   2 = assertion 失败
#   3 = 超 30 分钟预算
#
# 业务方 sign-off 流程见 docs/customer-demo-j1.md。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/.data/customer-demo-j1"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/demo-$TS.log"
REPORT="$LOG_DIR/demo-$TS.json"

if [ ! -x "$PYTHON" ]; then
    echo "[demo-j1] .venv 未就位；先跑 'uv sync --extra dev'" >&2
    exit 1
fi

echo "[demo-j1] start at $TS, log=$LOG, report=$REPORT"
START_EPOCH=$(date +%s)

set +e
"$PYTHON" "$REPO_ROOT/scripts/customer_demo_j1.py" --report "$REPORT" 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
set -e

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))

echo "[demo-j1] finished rc=$RC, wall-elapsed=${ELAPSED}s"

if [ "$RC" -eq 0 ]; then
    echo "[demo-j1] ✓ 全链路成功；提交业务方 sign-off (见 docs/customer-demo-j1.md)"
fi

exit "$RC"
