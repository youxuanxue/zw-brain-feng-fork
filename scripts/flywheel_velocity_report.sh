#!/usr/bin/env bash
# 飞轮速度看板 — docs/approved/zw-brain-flywheel.md §七.1.
#
# 单一健康度指标：Flywheel Velocity = 1 / (单客户上线 worker·week)
# 健康判据：第 N+1 个客户 < 第 N 个客户的 worker·week
#
# 数据源：docs/customer-readiness/velocity-history.md（首客户上线后由回灌 ritual 维护）

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HISTORY="$REPO_ROOT/docs/customer-readiness/velocity-history.md"

cat <<'HEAD'
═══════════════════════════════════════════════════════════════════════════════════════
Flywheel Velocity Report — 飞轮设计 §七.1
  Flywheel Velocity = 1 / (单客户上线 worker·week)
  健康判据: 第 N+1 客户成本 < 第 N 客户
═══════════════════════════════════════════════════════════════════════════════════════
HEAD

echo
echo "  当前阶段: 第 0 圈（势能积累期，首客户尚未上线）"
echo
echo "  | 客户                         | 类型     | worker·week | 速度 | 倍速 |"
echo "  |------------------------------|---------|-------------|------|------|"
echo "  | N0 sd-default (baseline)     | 实测    |       96    | 1/96 |  1x  |"

if [[ -f "$HISTORY" ]]; then
    # velocity-history.md 由回灌 ritual 维护，按表格形式追加
    # 解析以 "| N" 开头的非表头行
    grep -E '^\| N[1-9][0-9]?\s' "$HISTORY" 2>/dev/null | sed 's/^/  /' || true
else
    echo "  | N1 首客户 (6-8 月预估)       | 预估    |       24    | 1/24 |  4x  |"
    echo "  | N2 二客户 (9-11 月目标)       | 目标    |        6    | 1/6  | 16x  |"
    echo "  | N3+ 后续 (12 月+)            | 目标    |        2    | 1/2  | 48x  |"
fi

echo
echo "  数据源:"
echo "    - 历史: docs/customer-readiness/velocity-history.md"
if [[ -f "$HISTORY" ]]; then
    echo "      （首客户上线后由回灌 ritual 维护）"
else
    echo "      （尚未创建；首客户上线 30 天 ritual 触发时初始化）"
fi
echo "    - 设计: docs/approved/zw-brain-flywheel.md §七.1 / §十"

echo
echo "  反模式监测（飞轮 §九）："
echo "    [ ] #1 客户机房专用 fixture / mapper（preflight 段 25 + R8 反 fork 守）"
echo "    [ ] #2 业务方 review 不签字（promote_signoff.py + 月度 review 固化）"
echo "    [ ] #3 spec/test trace 漂移（preflight 段 38 守）"
echo "    [ ] #4 不回灌真值源（上线 ritual 硬步骤 §十）"
echo "    [ ] #5 三引擎走捷径硬编码（preflight 段 25 + Wave 2 AC5）"
echo "    [ ] #6 xlsx 128 条只引用不验证（tests/test_legacy_smoke_equivalence.py）"
echo "    [ ] #7 把全 feature Verified 当 ship 判据（ship gate = Wave 0+1+2 Verified）"
echo "    [ ] #8 Wave 4 SLI 当 GWT 用（docs/customer-readiness/wave4-cutoff-criteria.md）"

echo
echo "  飞轮三层完整度："
flywheel_potential=5
flywheel_potential_checked=0
for src in \
    docs/approved/zw-brain-architecture.md \
    docs/approved/zw-brain-flywheel.md \
    docs/approved/zw-brain-roles.md \
    old/共享平台V5.0.2-冒烟.xlsx \
    .testing/cross-cutting/legacy-128-mapping.md; do
    [[ -f "$src" ]] && flywheel_potential_checked=$((flywheel_potential_checked + 1))
done
echo "    势能层（5 类真值源）: ${flywheel_potential_checked} / ${flywheel_potential}"
triangle_n=$(python3 scripts/check_trace_triangle.py 2>&1 | grep -oE 'scanned [0-9]+' | head -1 | awk '{print $2}' || echo '?')
echo "    齿轮组（三角连接）  : ${triangle_n} feature 三角字段守住（preflight 段 38）"
echo "    动能层（客户上线）  : 0 / N（等首客户上线）"

echo
echo "═══════════════════════════════════════════════════════════════════════════════════════"
exit 0
