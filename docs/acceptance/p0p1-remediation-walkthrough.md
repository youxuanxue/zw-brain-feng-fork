# P0/P1 安全·正确性收尾 — 验收签字清单 + 本地走查取证

> 范围：审计定出的 P0(1) + P1(3)，在单 PR（多 commit）内修复。
> 分支 `fix/p0p1-security-correctness`，base = main HEAD 1cdc4e6。
> 本清单供**产品研发负责人**逐条核对后签字；已于 2026-06-02 核对通过（见文末「签字」段）。
> 所有「证据列」为本地实测结果（pytest + CLI/boot 级走查），命令可复跑。
> 守住边界：未碰 #185 文件、未碰前端；D4 审计 fail-closed / H2 锚定 / H3 写锁未削弱。

## 走查环境

- 干净隔离 DB（每条走查用 `ZW_BRAIN_DB_PATH` 切临时库或 `tmp_path`，不污染 `.data/zw_brain.db`）。
- worktree 缺 `.data`/`.venv` → symlink 主仓 gitignored 副本（venv 依赖一致）。
- 业务数据禁 Mock（D11）：走查用真实 seed 库 / 真实 store 行为，构造数据仅为审计/申请态等运行时记录。

---

## 验收表

| # | 修复项 | 验收标准 | 证据（测试名 + 结果 / 本地走查观察） | 签字 |
|---|--------|----------|--------------------------------------|------|
| P0-1 | MCP + CLI 补 M5 prod 护栏（镜像 A2A bypass 启动门禁） | `ZW_BRAIN_DEPLOY_MODE=prod` + bypass env 下：MCP `serve` 拒绝启动（非零退出、`DevBypassInProductionError`），CLI in-process invoke fail-closed；非 prod 下 MCP/CLI 正常工作 | **测试** `tests/test_p0_mcp_cli_prod_guard.py`：8 passed（含 prod/production/PROD/Production × MCP exit 2 / CLI fail-closed + 非 prod OK；CLI 断言门禁在 `get_service` 之前触发）。去掉修复 → MCP/CLI 测试 FAIL（已验）。<br>**本地走查**：① `ZW_BRAIN_DEPLOY_MODE=prod ZW_BRAIN_DEV_IAM_BYPASS=1 ZW_BRAIN_DEV_IAM_BYPASS_ACK=development-only python -m zw_brain.entry.mcp.server serve` → stderr `[mcp] refusing to start: ...forbidden in production...`，**exit 2**。② 同 env CLI `workbench.view` → JSON `{"error":"DevBypassInProductionError"...}`，**exit 4**。③ `ZW_BRAIN_DEPLOY_MODE=dev` MCP serve → `[mcp] zw-brain-mcp 1.0.0 stdio ready (63 tools)`，**exit 0**。④ dev CLI `workbench.view` → 返回真实 workbench greeting，**exit 0**。 | ☐ |
| P1-2 | governance 审计/调用查询下推 SQL + 500 截断完整性修 | 过滤（skill_id 白名单 / 单 skill_id）下推 SQL WHERE，LIMIT 在过滤后生效 → 匹配的旧审计不被 500 cap 静默丢；import_issues 不再全表加载 capability_call；响应形状不变 | **测试** `tests/test_p1_governance_pushdown_completeness.py`：3 passed（completeness：>500 审计中 3 条最旧白名单匹配全返回；只返白名单 skill；capability_call 单 skill_id 下推等价）。去掉修复 → completeness FAIL（匹配被截断）（已验）。<br>**本地走查**：临时库插 603 条审计（3 条 `governance.iam_overview` 作最旧行 + 600 噪声）→ `_governance_audit_events` 返回 **3** 条匹配（完整）；对照旧式「先 500 cap 再 Python 过滤」返回 **0**（匹配被丢）。 | ☐ |
| P1-3 | `grant_delivery_access` 跨聚合 fail-closed 守卫（46f0 类） | 授权前查绑定申请状态，处终态负向集合 `{withdrawn,rejected,revoked}` → 抛 `InvalidStateError` 拒绝；有效申请正常授权；只对无歧义终态负向拒绝（不误伤合法流） | **测试** `tests/test_p1_grant_cross_aggregate_guard.py`：4 passed（withdrawn/rejected/revoked 三态拒绝 + granted 正常）。去掉修复 → 三态 `DID NOT RAISE` FAIL（已验）。<br>**本地走查**：交付任务停 `warning`（可授权态）绑 `withdrawn` 申请 → grant 抛 `InvalidStateError: cannot grant delivery access: bound application is in a terminal-negative state (withdrawn)`；绑 `granted` 申请 → grant 完成（status=completed, grant_ref=grant-DLV-G）。 | ☐ |
| P1-4 | `get_service()` 冷启动双检锁 | ThreadingHTTPServer 并发首请求只 init 一次；无并发 DDL 崩溃；所有调用得同一实例 | **测试** `tests/test_p1_get_service_cold_start_lock.py`：1 passed（8 线程 barrier 同步释放打首请求，DatabaseStore.initialize 注入 50ms 加宽窗口 → 0 崩溃 + init 恰 1 次 + 8 调用同一实例）。去掉修复 → 并发 init 崩溃 `OperationalError: table runtime_state already exists` FAIL（已验）。<br>**本地走查**：8 并发线程打 `get_service` → errors **0**，BrainService init **1** 次，all same instance **True**，8 results 全返回。 | ☐ |

---

## 既有套件保持绿（回归不破）

| 套件 | 关注点 | 结果 |
|------|--------|------|
| `test_entry_surfaces.py` | A2A serve 门禁 / CLI / MCP 入口契约 | passed（含 P0-1 后） |
| `test_c1n1_shared_resolver_and_guards.py` / `test_c1n1_m7_rest_surface.py` | C1/N1 边界 + M5 既有护栏 | passed |
| `test_wave1_j2_pipeline.py` / `test_contract_projection.py` / `test_read_views.py` / `test_iam_governance_web_surface.py` | governance 消费侧 + 契约 | passed（P1-2 后形状不变） |
| `test_wave0_j1_credential_call.py` / `test_wave1_p4_delivery_explain.py` / `test_delivery_snapshot_enrichment.py` | grant / 交付 | passed（P1-3 后） |

## 守住的边界

- **未碰 #185 文件**：`application_service.py` / `P2ResourceDetail.vue` / `useResourceSchema.ts` / `pageAccess.ts` 一字未改。
- **未碰前端**：四项均后端修复，`zw-brain-web/` 无改动。
- **审计 D4 不削弱**：P1-3 走 `_mutate` 仍强制审计落库（走查 grant 正常时 audit_id 正常生成）。
- **H2 锚定 / H3 写锁未破**：未触 `runtime.py` 写锁语义之外的逻辑（仅加冷启动 init 锁）、未触锚定回路。
- **契约 `--check` 零漂移 / 响应形状不变**：P1-2 governance 审计事件键集（id/skill_id/phase/actor/occurred_at/payload_json）不变。

## P2（记债不通宵改，诚实留痕）

见 `docs/preflight-debt.md`「2026-06-02 — P0/P1 收尾 PR 判定不通宵改的 P2」+ `.testing/debt/`：
`prefilled-fake-enterprise-data`（归 #185）、`approval-case-projection-stale`、`shared-command-reverse-dep`、
`dead-layer-remnants`，以及 brain.py god-object debt 计数更正（3462→1425 LOC / 192→152 方法）。

---

## 签字

- 验收结论（产品研发负责人）：☑ 通过　☐ 退回
- 签字：产品研发负责人（本会话确认）
- 日期：2026-06-02
- 备注：P0-1 / P1-2 / P1-3 / P1-4 四项经 live 全栈走查复核通过（REST :8800 真实 316M seed 库 + mock 推理）：P1-4 冷启动 init 干净、P1-2 governance.iam_overview 白名单下推 + 形状不变、P1-3 三态终态负向 grant 经 REST 全返 409 invalid_state 且任务态未变（reversible，零残留写）、P0-1 prod MCP exit 2 / CLI exit 4 + start-local 入口 prod 拒启。preflight PASS、CI 全绿。
