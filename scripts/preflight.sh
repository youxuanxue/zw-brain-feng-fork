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
    local script_cmd="$2"
    local desc="$3"
    section "$section_id $desc ($script_cmd)"
    # script_cmd 第一段为路径，剩余为参数（支持 `script.py --check` 类形态）
    local script_path script_args
    script_path="${script_cmd%% *}"
    if [[ "$script_cmd" == *" "* ]]; then
        script_args="${script_cmd#* }"
    else
        script_args=""
    fi
    if [ ! -f "$script_path" ]; then
        echo "  skip: $script_path not present (see docs/preflight-debt.md)"
        return
    fi
    if [ ! -x "$script_path" ]; then
        chmod +x "$script_path" 2>/dev/null || true
    fi
    # shellcheck disable=SC2086
    if "$script_path" $script_args; then
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
段 20	scripts/check_no_retired_features.py	no-retired-features (alembic 删除 + K12 dashboard 退役)
段 21	scripts/check_no_numbered_routes.py	no-numbered-routes (route de-identify guardrail)
段 22	scripts/check_capability_boundary.py	capability-boundary (P0-05 §1.3 forbidden-zone live+builtin)
段 23	scripts/check_iam_prod_guard.py	iam-prod-guard (G1.4 — dev-iam-bypass 不得入生产部署清单)
段 24	scripts/check_ui_term_blacklist.py	ui-term-blacklist (R12 工程术语不进 UI — 9 词黑名单)
段 24b	scripts/check_webui_user_facing_en.py	webui user-facing EN leak (页面模板禁裸枚举)
段 25	scripts/check_adapter_write_ban.py	adapter-write-ban (§9.5 adapter 禁止成为新写入口)
段 26	scripts/check_twin_workspaces.py	twin-workspaces (.twin/ 6 workspace goal+plan schema valid)
段 27	scripts/check_ruff.py	ruff (与 CI lint job 对齐，F821/F401/I001/E402)
段 28	scripts/check_capability_registration.py	capability-registration (DISPATCH_TABLE + handlers + _CATEGORIZATION.md 三处一致)
段 29	scripts/check_no_hand_maintained_projection.py	no-hand-maintained-projection (F4 5 消费面投影派生自单一 Registry)
段 30	scripts/check_m0_mapper_coverage_doc.py	m0-mapper-doc (覆盖判定 doc count vs HANDLED_TABLES 防漂移)
段 31	scripts/check_trusted_payload_usage.py	trusted-payload-usage (tests 走 invoke_trusted 不直接 brain.invoke_skill — F6 防回潮)
段 32	scripts/check_read_path_full_scan.py	read-path-full-scan (PR #113 教训机械化)
段 32b	scripts/generate_full_scan_exemptions.py --check	full-scan-exemptions-sync (E2 豁免清单与代码同步)
段 33	scripts/check_live_builtin_budget.py	live-builtin-budget (架构约束 R7 单 prefix > 25 触发 review)
段 34	scripts/check_wave_snapshot_sync.py	wave-snapshot-sync (E1 — §〇.1 反向链接锚点解析 + debt 反向覆盖)
段 35	scripts/check_brain_no_request_state_singleton.py	brain-no-request-state-singleton (per-request role 必走 ContextVar，不得 seed 到 _ui_state 单例)
段 36	scripts/check_no_demo_id_literals.py	no-demo-id-literals (REQ-/DLV-/PKG- demo id 限 demo_state_sync.py，不得入 brain.py/handlers)
段 37	scripts/check_brain_no_record_to_dict.py	brain-no-record-to-dict (record_to_dict 纯函数住 command/serializers/，不得回潮到 BrainService — Phase 1.1)
段 38	scripts/check_trace_triangle.py	trace-triangle (飞轮 §四 — .feature # Owner/# Pytest/# Twin-F + plan.yaml spec_ref 三角连接守卫)
段 39	scripts/check_legacy_smoke_row_numbers.py	legacy-smoke-rows (飞轮 §三.2 — .feature 引用旧 xlsx 行号必须在 mapping doc 出现)
段 40	scripts/check_handler_brain_backref.py	handler-brain-backref (handler body 不得反向访问 BrainService — Action A，白名单受控)
段 41	scripts/check_no_silent_error_swallow_in_adapter.py	no-silent-error-swallow-in-adapter (CLAUDE.md §2 — mapper add_issue+continue 必须经 finish_run 写 error_summary)
段 42	scripts/check_pipeline_middleware_order.py	pipeline-middleware-order (SkillPipeline middleware 顺序与 MIDDLEWARE_ORDER 一致 — Action B)
段 43	scripts/check_handler_uses_pipeline.py	handler-uses-pipeline (handler 不得调 brain._mutate / _invoke_traced_read / _append_audit_feed，必须走 deps.pipeline — Action B)
段 44	scripts/check_approved_doc_drift.py	approved-doc-drift (D32.d — D-编号决策真值源回灌守卫，PR-mode WARN-only)
段 45	scripts/check_handler_no_direct_snapshot_read.py	handler-no-direct-snapshot-read (handler 不得直接读 brain._snapshot / brain._state_store.database_store / brain._{request,package,delivery}_by_*，必须走 deps.view / deps.repos — Action C)
段 46	scripts/check_handler_no_ui_state.py	handler-no-ui-state (handler/helper 不得反向读 brain._ui_state，role 走 ctx.role / actor 走 ctx.actor — Action F)
CHECKS

echo ""
if [ $project_errors -eq 0 ]; then
    echo "=== preflight: PASS (common + project stages) ==="
    exit 0
else
    echo "=== preflight: FAIL ($project_errors project check(s) failed) ==="
    exit 1
fi
