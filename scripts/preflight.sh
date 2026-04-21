#!/usr/bin/env bash
#
# scripts/preflight.sh — zw-brain 项目级提交前/CI 强约束门禁
#
# 结构：
#   1. 调用 dev-rules 通用模板（段 1-8：分支/submodule/sync drift/contract/story/approved/pending/stat）
#   2. 叠加 zw-brain 项目特有的硬约束检查段（段 9-11，对应基线 §13.1 + §十四 D4/D6/D15）
#
# 设计原则（OPC：通用入模板，特有入项目）：
#   - 通用守卫（branch/submodule/contract/stat）由 dev-rules 模板维护，所有项目共享
#   - zw-brain 特有守卫（无直连 LLM / 审计同步 / 区块链异步 / 大屏只读 / fixture 脱敏）
#     直接住在项目内 scripts/check_*.py，不污染 dev-rules 模板
#
# 段号映射（与基线 §13.1 一致）：
#   段 7a  audit-must-block       → scripts/check_audit_must_block.py    （D4 上半）
#   段 7b  blockchain-async       → scripts/check_blockchain_async.py    （D4 下半）
#   段 9   fixture-pii            → scripts/check_fixture_pii.py         （D11 fixture 脱敏）
#   段 10  no-direct-llm          → scripts/check_no_direct_llm.py       （D6 推理平台 SDK 唯一出口）
#   段 11  dashboard-readonly     → scripts/check_dashboard_readonly.py  （D15 大屏只读）
#   段 12  fixture-coverage       → scripts/check_fixture_coverage.py    （D18，GATE-2 后启用）
#   段 13  gate1-prototype        → scripts/check_gate1_prototype.py     （D21，GATE-1 retrofit）
#   段 14  external-refs          → scripts/check_external_refs.py       （D22，外部引用悬空检查）
#
# 用法：./scripts/preflight.sh [--fix]
# 退出码：0 = 全部通过；非 0 = 至少一项失败

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

FIX_MODE=0
[ "${1:-}" = "--fix" ] && FIX_MODE=1

# ── 1) 调用 dev-rules 通用模板（段 1-8）─────────────────────────────
"$REPO_ROOT/dev-rules/templates/preflight.sh" "$@"
template_exit=$?

# 通用模板失败则直接退出（避免把项目段的 ok 误读为通过）
if [ $template_exit -ne 0 ]; then
    echo ""
    echo "=== preflight: FAIL (template stage exited $template_exit; project stages skipped) ==="
    exit $template_exit
fi

# ── 2) zw-brain 项目特有硬约束（段 7a / 7b / 9 / 10 / 11）──────────
project_errors=0
section() { echo ""; echo "=== $* ==="; }
fail_proj() { echo "  FAIL: $*"; project_errors=$((project_errors + 1)); }
ok_proj()   { echo "  ok: $*"; }
skip_proj() { echo "  skip: $*"; }

run_check() {
    local section_id="$1"
    local script="$2"
    local desc="$3"
    section "$section_id $desc ($script)"
    if [ ! -f "$script" ]; then
        skip_proj "$script not present (Phase 0 task — see docs/approved/zw-brain-architecture.md 附录 A)"
        return
    fi
    if [ ! -x "$script" ]; then
        chmod +x "$script" 2>/dev/null || true
    fi
    if "$script"; then
        ok_proj "$desc"
    else
        fail_proj "$desc"
    fi
}

run_check "段 7a" "scripts/check_audit_must_block.py"   "audit-must-block (D4 审计同步落库熔断)"
run_check "段 7b" "scripts/check_blockchain_async.py"   "blockchain-async (D4 区块链异步锚定)"
run_check "段 9"  "scripts/check_fixture_pii.py"        "fixture-pii (D11 fixture 脱敏校验)"
run_check "段 10" "scripts/check_no_direct_llm.py"      "no-direct-llm (D6 禁止直连第三方 LLM API)"
run_check "段 11" "scripts/check_dashboard_readonly.py" "dashboard-readonly (D15 大屏只读)"
run_check "段 13" "scripts/check_gate1_prototype.py"    "gate1-prototype (D21 GATE-1 设计文档必须配套原型)"
run_check "段 14" "scripts/check_external_refs.py"      "external-refs (D22 外部引用文件 + 锚点必须可解析)"

echo ""
if [ $project_errors -eq 0 ]; then
    echo "=== preflight: PASS (template + project stages) ==="
    exit 0
else
    echo "=== preflight: FAIL ($project_errors project check(s) failed) ==="
    exit 1
fi
