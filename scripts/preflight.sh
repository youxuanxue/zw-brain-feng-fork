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

# worktree fallback：worktree 默认 .venv 是 uv 缓存裸 python 解释器（无项目依赖），
# 把主仓 venv 加进 PATH 让所有 shebang `#!/usr/bin/env python3` 走主仓 venv，
# 并 export PYTHON_BIN 让 Python 子脚本（如 check_no_hand_maintained_projection.py 内部 _repo_python()）
# 也走主仓 venv（D33 retrofit）。只在 worktree 且 worktree venv 缺关键依赖时触发。
# canary 选 jwt：PyJWT 是 IAM auth 必需依赖（zw_brain.shared.iaf_oidc），项目生命周期
# 内不太可能去除；若 IAM 重构去掉 jwt 依赖，同步更新此 canary 为新核心依赖名。
if [ ! -x "$REPO_ROOT/.venv/bin/python3" ] || ! "$REPO_ROOT/.venv/bin/python3" -c "import jwt" >/dev/null 2>&1; then
    _d33_common_dir="$(git rev-parse --git-common-dir 2>/dev/null)"
    if [ -n "$_d33_common_dir" ]; then
        _d33_main_root="$(dirname "$(cd "$_d33_common_dir" && pwd)")"
        if [ -x "$_d33_main_root/.venv/bin/python3" ] && [ "$_d33_main_root" != "$REPO_ROOT" ]; then
            export PATH="$_d33_main_root/.venv/bin:$PATH"
            export PYTHON_BIN="$_d33_main_root/.venv/bin/python3"
        fi
    fi
fi

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
    # 如果 .py 脚本，用 PYTHON_BIN（preflight.sh 顶部 worktree fallback 已 export）
    # 或 REPO_ROOT/.venv/bin/python（main repo 场景），避免走 shebang 命中 system python3
    # 缺项目依赖（sqlalchemy / jwt / yaml）。worktree 场景下 PATH 也已包含主仓 venv 第一位，
    # 即使 shebang 也会走对——run_check 内的显式 invoker 是定向安全网。
    local invoker=""
    if [[ "$script_path" == *.py ]]; then
        if [ -n "${PYTHON_BIN:-}" ] && [ -x "${PYTHON_BIN}" ]; then
            invoker="$PYTHON_BIN"
        elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
            invoker="$REPO_ROOT/.venv/bin/python"
        fi
    fi
    # shellcheck disable=SC2086
    if [ -n "$invoker" ]; then
        if "$invoker" "$script_path" $script_args; then
            ok_proj "$desc"
        else
            fail_proj "$desc"
        fi
    elif "$script_path" $script_args; then
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
段 27	scripts/check_ruff.py	ruff (与 CI lint job 对齐，F821/F401/I001/E402)
段 28	scripts/check_capability_registration.py	capability-registration (DISPATCH_TABLE + handlers + _CATEGORIZATION.md 三处一致)
段 29	scripts/check_no_hand_maintained_projection.py	no-hand-maintained-projection (F4 5 消费面投影派生自单一 Registry)
段 30	scripts/check_m0_mapper_coverage_doc.py	m0-mapper-doc (覆盖判定 doc count vs HANDLED_TABLES 防漂移)
段 31	scripts/check_trusted_payload_usage.py	trusted-payload-usage (tests 走 invoke_trusted 不直接 brain.invoke_skill — F6 防回潮)
段 32	scripts/check_read_path_full_scan.py	read-path-full-scan (PR #113 教训机械化)
段 32b	scripts/generate_full_scan_exemptions.py --check	full-scan-exemptions-sync (E2 豁免清单与代码同步)
段 32c	scripts/check_read_path_scan_to_one.py	read-path-scan-to-one (god's-eye 详情页 N+1 — handler/service 禁 list_*() 全表筛一条；改用索引 getter get_record/get_case/get_task；与段 32 互补，豁免 # scan-to-one-ok:)
段 33	scripts/check_live_builtin_budget.py	live-builtin-budget (架构约束 R7 单 prefix > 25 触发 review)
段 34	scripts/check_wave_snapshot_sync.py	wave-snapshot-sync (E1 — §〇.1 反向链接锚点解析 + debt 反向覆盖)
段 35	scripts/check_brain_no_request_state_singleton.py	brain-no-request-state-singleton (per-request role 必走 ContextVar，不得 seed 到 _ui_state 单例)
段 36	scripts/check_no_demo_id_literals.py	no-demo-id-literals (REQ-/DLV-/PKG- demo id 限 demo_state_sync.py，不得入 brain.py/handlers)
段 37	scripts/check_brain_no_record_to_dict.py	brain-no-record-to-dict (record_to_dict 纯函数住 command/serializers/，不得回潮到 BrainService — Phase 1.1)
段 38	scripts/check_trace_triangle.py	trace-triangle (飞轮 §四 — .feature # Owner/# Pytest ←→ tests 连接守卫；.twin 退役后收敛为 SPEC↔test 双边 D46.e)
段 39	scripts/check_legacy_smoke_row_numbers.py	legacy-smoke-rows (飞轮 §三.2 — .feature 引用旧 xlsx 行号必须在 mapping doc 出现)
段 40	scripts/check_handler_brain_backref.py	handler-brain-backref (handler body 不得反向访问 BrainService — Action A，白名单受控)
段 41	scripts/check_no_silent_error_swallow_in_adapter.py	no-silent-error-swallow-in-adapter (CLAUDE.md §2 — mapper add_issue+continue 必须经 finish_run 写 error_summary)
段 42	scripts/check_pipeline_middleware_order.py	pipeline-middleware-order (SkillPipeline middleware 顺序与 MIDDLEWARE_ORDER 一致 — Action B)
段 43	scripts/check_handler_uses_pipeline.py	handler-uses-pipeline (handler 不得调 brain._mutate / _invoke_traced_read / _append_audit_feed，必须走 deps.pipeline — Action B)
段 44	scripts/check_approved_doc_drift.py	approved-doc-drift (D32.d — D-编号决策真值源回灌守卫，PR-mode WARN-only)
段 45	scripts/check_handler_no_direct_snapshot_read.py	handler-no-direct-snapshot-read (handler 不得直接读 brain._snapshot / brain._state_store.database_store / brain._{request,package,delivery}_by_*，必须走 deps.view / deps.repos — Action C)
段 46	scripts/check_handler_no_ui_state.py	handler-no-ui-state (handler/helper 不得反向读 brain._ui_state，role 走 ctx.role / actor 走 ctx.actor — Action F)
段 47	scripts/check_brain_no_domain_method.py	brain-no-domain-method (BrainService 域方法必须是 1 行 delegate shim，实现住 zw_brain/domain/services/ — Action D)
段 48	scripts/check_brain_no_cross_cutting.py	brain-no-cross-cutting (BrainService 跨切关注 / 状态同步 helper 必须是 shim，实现住 zw_brain/command/{pipeline_ops,sync}.py — Action E)
段 49	scripts/check_domain_no_command_import.py	domain-no-command-import (zw_brain/domain/ 不得 runtime import zw_brain.command — 4 层 entry→command→domain→shared，Action H R-001)
段 50	scripts/check_no_skill_identifier_in_zw_brain.py	no-skill-identifier-in-zw-brain (D33 — 防 skill 命名回潮，新增 class/def 标识符须在白名单)
段 51	scripts/check_agentruntime_bundles.py	agentruntime-bundles (D33.b / D30 — agents/*/AGENT.yaml + capabilities.json schema 持续守卫)
段 52	scripts/check_webui_capability_rendered.py	webui-capability-rendered (god's-eye #161 — live+webui 能力须有 .vue/.ts 渲染消费者，baseline 棘轮防净新增"声称UI无渲染"漂移；台账 scripts/webui_capability_rendered_exemptions.txt)
段 53	scripts/check_signoff_package.py	signoff-package-lint (D35 — 业务方 sign-off 材料包三层守卫：数据真实性 + 禁过程数字 + 强制节/建议列)
段 54	scripts/check_signoff_landed.py	signoff-landed (D46.b — approved sign-off 文档 scope ↔ .testing/signoff/<scope>.signoff.yaml 账本单源，关「C/D 靠人记忆」债)
段 55	scripts/check_acceptance_package.py	acceptance-package-lint (D37 — 效果验收材料包：证据产物 result=pass + 来自当前历史 + 每验收点挂 evidence 标签 + 禁过程数字)
段 56	scripts/check_no_legacy_inference_env.py	no-legacy-inference-env (D36.e — 禁已退役推理网关 INSPUR 系 env 前缀回潮；allowlist=CLAUDE.md D36 记录 + 负向守卫测试 + 守卫自身)
段 57	scripts/check_require_real_seed_sanity.py	require-real-seed-sanity (D44 — 禁 require_real_seed gate 运行时累积表 capability_call/audit_event/anchor_outbox/audit_receipt；运行时数据靠 fixture 自产不靠 seed 门槛)
段 66	scripts/check_credential_grant_invariant.py	credential-honesty-invariant (C-1 凭据诚实化：legacy exchange granted 分支须**显式处理凭据态**——credential + credential_status 都赋值，且**不得**调 derive_demo_credential 捏造；真实授权表无 per-grant 凭据→诚实 not_issued。新建在产单 approve 自动签发不在此约束)
段 67	scripts/check_orphan_rows.py	orphan-rows (数据模型参照完整性脊柱 §六 — 自建干净 seed 库扫 A12+B5+C7 全父子边孤儿=0 + FK 回潮 floor≥22 + catalog_entry 可达性；A/B 走 M1 FK+CASCADE、C 类 honest 降级由本守卫唯一兜底 design §2.5)
段 60	scripts/check_feature_measurement.py	feature-measurement (单一事实源 — MEASUREMENT 产物 schema+banner 合法 + **内容指纹新鲜**：绿 feature 的存档指纹须 == 当前 .feature+测试文件指纹（D46.g 信任锚，非 git_sha；squash 免疫）；陈旧→FAIL；preflight 不跑 pytest 只读产物，缺则 green() fail-closed)
段 61	scripts/gen_feature_status.py --check	feature-status-gen (单一事实源 — feature status 现算不存储：.testing/status/feature-status.md 须与 SPEC+MEASUREMENT+SIGN-OFF 现算字节一致，禁手改)
段 62	scripts/check_no_hand_typed_status.py	no-hand-typed-status (全局宪法 §5 — .feature 禁手写 # Status/状态词，status 由 gen_feature_status.py 现算；排期外用 # Deferred；替原段 58 对账守卫，使漂移结构性消失)
段 63	scripts/check_signoff_ledger.py	signoff-ledger (D46 — .testing/signoff/ 签字唯一权威源：每账本 schema 合法 + covers 的 .feature 存在 + evidence 非空禁空签；decision_only 须 covers 空)
段 64	scripts/check_debt_status.py	debt-status (debt-as-function 单一事实源 — .testing/debt/*.debt.yaml schema 合法 + 每条 assert 现算；invalid→FAIL、stale-fixed→WARN（PREFLIGHT_DEBT_STRICT=1 转 FAIL）；空账本绿)
段 65	scripts/gen_debt_status.py --check	debt-status-gen (debt-as-function 单一事实源 — .testing/debt/debt-status.md 须与各 debt assert 现算字节一致，禁手改)
CHECKS

echo ""
if [ $project_errors -eq 0 ]; then
    echo "=== preflight: PASS (common + project stages) ==="
    exit 0
else
    echo "=== preflight: FAIL ($project_errors project check(s) failed) ==="
    exit 1
fi
