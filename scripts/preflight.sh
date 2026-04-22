#!/usr/bin/env bash
#
# zw-brain 提交前门禁：先跑 dev-rules 通用模板（分支/子模块/sync/契约/story/stat 等），
# 再跑本仓库产品硬约束脚本。段号与附录 A / 设计基线一致；段 12 等待 GATE-2 见 docs/preflight-debt.md。
#
# 用法：./scripts/preflight.sh [--fix]   （--fix 传给通用模板）

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── 1) dev-rules 通用模板 ────────────────────────────────────────────
"$REPO_ROOT/dev-rules/templates/preflight.sh" "$@"
template_exit=$?

if [ $template_exit -ne 0 ]; then
    echo ""
    echo "=== preflight: FAIL (template stage exited $template_exit; project stages skipped) ==="
    exit $template_exit
fi

# ── 2) zw-brain 产品段（路径与策略绑定本仓库，不上提 dev-rules；理由见 docs/preflight-debt.md）──
project_errors=0
section() { echo ""; echo "=== $* ==="; }
fail_proj() { echo "  FAIL: $*"; project_errors=$((project_errors + 1)); }
ok_proj()   { echo "  ok: $*"; }

run_check() {
    local section_id="$1"
    local script="$2"
    local desc="$3"
    section "$section_id $desc ($script)"
    if [ ! -f "$script" ]; then
        echo "  skip: $script not present (see docs/preflight-debt.md)"
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

while IFS=$'\t' read -r sid script desc || [ -n "${sid:-}" ]; do
    [ -z "${sid:-}" ] && continue
    [[ "$sid" =~ ^# ]] && continue
    run_check "$sid" "$script" "$desc"
done <<'CHECKS'
段 7a	scripts/check_audit_must_block.py	audit-must-block (D4)
段 7b	scripts/check_blockchain_async.py	blockchain-async (D4)
段 9	scripts/check_fixture_pii.py	fixture-pii (D11)
段 10	scripts/check_no_direct_llm.py	no-direct-llm (D6)
段 11	scripts/check_dashboard_readonly.py	dashboard-readonly (D15)
段 13	scripts/check_gate1_prototype.py	gate1-prototype (D21)
段 14	scripts/check_external_refs.py	external-refs (D22)
CHECKS

echo ""
if [ $project_errors -eq 0 ]; then
    echo "=== preflight: PASS (template + project stages) ==="
    exit 0
else
    echo "=== preflight: FAIL ($project_errors project check(s) failed) ==="
    exit 1
fi
