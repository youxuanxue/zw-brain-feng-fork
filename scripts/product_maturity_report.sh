#!/usr/bin/env bash
# 产品成熟度周报 — 飞轮设计 §七.2.
#
# 单一指标：Verified feature 数 / 应做 feature 数（按 Wave 分子分母）.
# 落地飞轮反模式 #2 的看板侧（业务方 sign-off label → Ready；客户真实数据跑通 → Verified）.
#
# 使用：
#   ./scripts/product_maturity_report.sh          # 输出到 stdout
#   ./scripts/product_maturity_report.sh --check  # CI 模式：0 = 报告生成成功

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CHECK_MODE=0
[[ "${1:-}" == "--check" ]] && CHECK_MODE=1

count_status() {
    # $1 = wave dir glob; $2 = status
    local pattern="$1"
    local status="$2"
    local n
    n=$(find ".testing/waves/${pattern}/features" -name "*.feature" -type f 2>/dev/null \
        | xargs grep -l "^# Status: ${status}\$" 2>/dev/null | wc -l)
    echo "${n//[[:space:]]/}"
}

count_total() {
    local pattern="$1"
    local n
    n=$(find ".testing/waves/${pattern}/features" -name "*.feature" -type f 2>/dev/null | wc -l)
    echo "${n//[[:space:]]/}"
}

render_wave() {
    # $1 = wave-N short; $2 = wave dir pattern; $3 = description
    local wave="$1"
    local pattern="$2"
    local desc="$3"
    local total draft ready intest verified
    total=$(count_total "$pattern")
    draft=$(count_status "$pattern" "Draft")
    intest=$(count_status "$pattern" "InTest")
    ready=$(count_status "$pattern" "Ready")
    verified=$(count_status "$pattern" "Verified")

    # 进度条: Verified + Ready 占比
    local progress
    if [[ "$total" -gt 0 ]]; then
        progress=$(( (verified * 100 + ready * 50) / total ))
    else
        progress=0
    fi
    local bars=$((progress / 10))
    local bar=""
    for ((i=0; i<bars; i++)); do bar="${bar}█"; done
    for ((i=bars; i<10; i++)); do bar="${bar}░"; done

    printf "  %-7s %-22s [%s] %2d 设计 ✓ / %2d Draft / %2d InTest / %2d Ready / %2d Verified  (%3d%%)\n" \
        "$wave" "$desc" "$bar" "$total" "$draft" "$intest" "$ready" "$verified" "$progress"
}

echo "═══════════════════════════════════════════════════════════════════════════════════════"
echo "Product Maturity Report — $(date +%Y-%m-%d)"
echo "  飞轮设计 §七.2 — Verified feature / 应做 feature 数"
echo "  PR commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
echo "═══════════════════════════════════════════════════════════════════════════════════════"

render_wave "Wave 0" "wave-0-golden-path"          "J1 主路径"
render_wave "Wave 1" "wave-1-j1-j2-closed-loop"    "J1 深化 + J2"
render_wave "Wave 2" "wave-2-engines-b1-zones"     "三引擎 + B1"
render_wave "Wave 3" "wave-3-protocol-tenant-national" "协议 + 多租户 [delayed]"
render_wave "Wave 4" "wave-4-legacy-retirement"    "退役 [post-ship]"

# Ship gate
total_012=$(( $(count_total "wave-0-golden-path") + $(count_total "wave-1-j1-j2-closed-loop") + $(count_total "wave-2-engines-b1-zones") ))
verified_012=$(( $(count_status "wave-0-golden-path" "Verified") + $(count_status "wave-1-j1-j2-closed-loop" "Verified") + $(count_status "wave-2-engines-b1-zones" "Verified") ))

echo
echo "  Ship gate (Wave 0+1+2 Verified): ${verified_012} / ${total_012}"
if [[ "$verified_012" -ge "$total_012" && "$total_012" -gt 0 ]]; then
    echo "  ✓ 客户机房 dry-run 可启动"
else
    remaining=$((total_012 - verified_012))
    echo "  ⏳ 还需 ${remaining} 个 feature Verified（业务方 sign-off + 客户真实数据跑通）"
fi

echo
cc_docs=$(find .testing/cross-cutting -maxdepth 1 -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
cc_feats=$(find .testing/cross-cutting -maxdepth 1 -name '*.feature' -type f 2>/dev/null | wc -l | tr -d ' ')
echo "  cross-cutting: ${cc_docs} docs + ${cc_feats} feature"
echo "  飞轮反模式 #2 / #8 守卫见 docs/approved/zw-brain-flywheel.md §九"
echo "═══════════════════════════════════════════════════════════════════════════════════════"

exit 0
