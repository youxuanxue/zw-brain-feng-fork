#!/usr/bin/env bash
#
# zw-brain 提交前门禁：先跑 vendored 通用段（scripts/preflight_common.sh），
# 再跑本仓库产品硬约束脚本。可选本机 dev-rules symlink 供 sync 段与 cloud-agent 段使用。
# 段号与附录 A / 设计基线一致；段 12 等待 GATE-2 见 docs/preflight-debt.md。
#
# 用法：./scripts/preflight.sh [--fix]   （--fix 传给通用段）

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── 1) 通用段（approved / stat 等使用本仓库 scripts/，CI 不依赖 dev-rules 检出）──
"$REPO_ROOT/scripts/preflight_common.sh" "$@"
template_exit=$?

if [ $template_exit -ne 0 ]; then
    echo ""
    echo "=== preflight: FAIL (common stage exited $template_exit; project stages skipped) ==="
    exit $template_exit
fi

# ── 2) zw-brain 产品段（路径与策略绑定本仓库；理由见 docs/preflight-debt.md）──
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
段 14	scripts/check_external_refs.py	external-refs (D22)
段 15	scripts/check_ui_spec_b.py	ui-spec-b (Spec B single theme)
段 16	scripts/check_legacy_mappers.py	legacy-mappers (D7+D4)
段 17	scripts/check_iam_doc_freshness.py	iam-doc-freshness (R-002)
段 18	scripts/check_db_bloat.py	db-bloat-check (canonical DB ≤ 2GB hard, 500MB soft)
段 19	scripts/check_no_legacy_role_codes.py	no-legacy-role-codes (D23 retrofit)
段 20	scripts/check_no_retired_features.py	no-retired-features (R15 alembic + R17 K12 dashboard)
段 21	scripts/check_no_numbered_routes.py	no-numbered-routes (route de-identify guardrail)
段 22	scripts/check_capability_boundary.py	capability-boundary (P0-05 §1.3 forbidden-zone live+builtin)
段 23	scripts/check_iam_prod_guard.py	iam-prod-guard (G1.4 — dev-iam-bypass 不得入生产部署清单)
CHECKS

echo ""
if [ $project_errors -eq 0 ]; then
    echo "=== preflight: PASS (common + project stages) ==="
    exit 0
else
    echo "=== preflight: FAIL ($project_errors project check(s) failed) ==="
    exit 1
fi
