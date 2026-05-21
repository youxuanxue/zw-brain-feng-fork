---
doc_id: testing-cleanup-plan
status: one-shot-archive
expires: merge + 30 天后可删除
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7)
---

# tests/*.py 全量重写一次性档案

> **目的**：记录本次 PR 删除 42 个测试文件的依据，以及每个文件的"按新 .feature 重写"映射；merge 后 30 天可删本档案。

## 一、保留（4 个机械对齐测试）

| 文件 | 保留理由 |
|---|---|
| `tests/test_role_codes_alignment.py` | R10 7 角色码跨文件一致性的机械验证；不依赖任何 wave |
| `tests/test_contract_projection.py` | 单一能力契约 → 5 消费面投影一致性的机械验证；R3 核心约束 |
| `tests/test_packaging.py` | hatchling 打包 manifest / openapi.json / agent_card.json 一致性（slow_infra，push-to-main 跑） |
| `tests/test_domain_policy.py` | `policy.assert_no_legacy_role_codes()` 启动检查 — R10 双层兜底之一 |

合计保留 4 个，27 个测试用例（其中 1 个 slow_infra 默认 deselected）。

## 二、删除（42 个）+ 重写映射

### 批次 A：已退役架构（3 个）

| 文件 | 退役原因 | 重写到 |
|---|---|---|
| `test_acceptance_9_roles_e2e.py` | 9 角色（M0 + 申请人-安全审计员）已收敛为 7 角色码（D23）；W5 客户验收 checklist 已重写 | `.testing/waves/wave-0-golden-path/features/*` 端到端组合 + 业务方 sign-off |
| `test_ui_spec_b_gate.py` | prototype/ 可点击 SPA 已退役（D 决策 2026-04-28）；`scripts/check_ui_spec_b.py` 已删 | 不重写（已无对应业务） |
| `test_legacy_rollback.py` | alembic 已退役（v4.1 R15）；schema 用 `drop_all` + `create_all`，不需要 rollback | 不重写 |

### 批次 B：Wave 命名旧实现（4 个）

| 文件 | 退役原因 | 重写到 |
|---|---|---|
| `test_w1_skills.py` | W1-W5 旧 wave 编号与 D23 后新 Wave 0-4 错配 | `.testing/waves/wave-0-golden-path/features/infra-*.feature` + `wave-1-j1-j2-closed-loop/features/j2-*.feature` |
| `test_w2_provider_workflow.py` | 同上 | `.testing/waves/wave-1-j1-j2-closed-loop/features/j2-*.feature` |
| `test_w3_r7_inbox.py` | 文件名 R7（旧角色编号）已退役（R[1-8] → 7 角色码 D23） | `.testing/waves/wave-1-j1-j2-closed-loop/features/j2-department-review.feature` |
| `test_w4_inline_panels.py` | 同 W4 编号错配 | `.testing/waves/wave-2-engines-b1-zones/features/engine-ai-config-draft.feature` |

### 批次 C：浏览器 e2e 旧实现（3 个）

| 文件 | 退役原因 | 重写到 |
|---|---|---|
| `test_j1j2_b1_browser_matrix_e2e.py` | 测试矩阵建在 prototype SPA 上 | `.testing/waves/wave-0-golden-path/features/j1-*.feature` + `wave-1-j1-j2-closed-loop/features/j2-*.feature` + `wave-2-engines-b1-zones/features/b1-*.feature` 按 Wave 重组 |
| `test_webui_browser_e2e.py` | 同上 | 同上（按 8 页面拆分） |
| `test_webui_journey_contract.py` | 同上 | `.testing/waves/wave-0-golden-path/features/infra-contract-projection.feature`（契约一致性回归） |
| `test_web_snapshot_redaction.py` | 与 prototype SPA 文案矩阵耦合 | `.testing/cross-cutting/negative-and-guardrails.feature`（敏感数据脱敏属于横切回归） |

### 批次 D：Legacy migration（8 个）

> per memory：`project_legacy_import_migration_only` — legacy import 是一次性迁移工具，不进 wave 测试矩阵。

| 文件 | 退役原因 |
|---|---|
| `test_legacy_migration_batch.py` | legacy 迁移工具单测；非 Wave 路径 |
| `test_legacy_migration_status_query.py` | 同上 |
| `test_legacy_catalog_metadata_mapper.py` | mapper 工具单测；如保留，应在 `zw_brain/adapters/` 旁的本地测试，不混入主测试矩阵 |
| `test_legacy_exchange_mapper.py` | 同上 |
| `test_legacy_governance_mapper.py` | 同上 |
| `test_legacy_topic_package_mapper.py` | 同上 |
| `test_legacy_parser.py` | 同上 |
| `test_legacy_runtime_offline.py` | 同上 |
| `test_installed_legacy_migration.py` | install 后跑 legacy migration 的 smoke；如需保留，按 Wave 0 `infra-legacy-import-smoke.feature` 重写 |

**结论**：legacy 迁移工具的测试如有强烈需要，可由 `zw_brain/adapters/` 模块自带 mini test（不进主 tests/），或由首次客户上线 PR 接力。本次全量删除。

### 批次 E：Brain / runtime 大块（13 个）

| 文件 | 大小 | 退役原因 | 重写到 |
|---|---|---|---|
| `test_brain_service.py` | 188 KB | 累积膨胀；混合多 wave 关注点 | 拆分到 `wave-0-golden-path/features/j1-*.feature` + `wave-1-j1-j2-closed-loop/features/j1-*` + `wave-2-engines-b1-zones/features/b1-*` |
| `test_repositories.py` | 40 KB | domain 仓储层混合多聚合 | 按 6 聚合拆到对应 wave 的 j1/j2/b1 features 中（聚合 setup 体现在 Background） |
| `test_rest_runtime.py` | 25 KB | REST 投影 + runtime 混合 | `wave-0-golden-path/features/infra-contract-projection.feature` + `wave-3-protocol-tenant-national/features/observability-cost-quota.feature` |
| `test_rest_session_lifecycle.py` | 20 KB | 会话生命周期混 IAM + REST | `wave-0-golden-path/features/infra-iam-session.feature` |
| `test_database_store.py` | 11 KB | DatabaseStore 直接测试 | 改为通过 `wave-0-golden-path/features/infra-audit-bus.feature` 端到端覆盖（白盒测试退化为黑盒） |
| `test_entry_runtimes.py` | 15 KB | entry 多消费面混合 | `wave-0-golden-path/features/infra-contract-projection.feature` |
| `test_installed_entries.py` | 2 KB | wheel install 后 entry 可执行性 | 由 `tests/test_packaging.py`（slow_infra mark）接管；不另起 .feature |
| `test_installed_http_handlers.py` | 3 KB | 同上 | 同上 |
| `test_read_models.py` | 19 KB | read model 直接测试 | 端到端覆盖（同 test_database_store） |
| `test_rest_projection.py` | 2 KB | REST 投影一致性 | `wave-0-golden-path/features/infra-contract-projection.feature` |
| `test_runtime_config.py` | 4 KB | runtime 配置 | 折叠进 `wave-0-golden-path/features/infra-contract-projection.feature`（runtime 配置 = 契约一致性的一部分） |

### 批次 F：IAM / OIDC（3 个）

| 文件 | 退役原因 | 重写到 |
|---|---|---|
| `test_iaf_iam_e2e_offline.py` | IAF IAM 外部依赖 e2e | `wave-0-golden-path/features/infra-iam-session.feature`（与 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 边界对齐） |
| `test_iaf_oidc.py` | OIDC 集成 | 同上 |
| `test_auth_session_store.py` | session 存储 | 同上 |

### 批次 G：推理客户端（2 个）

| 文件 | 重写到 |
|---|---|
| `test_inference_client.py` | `wave-0-golden-path/features/infra-inference-gateway.feature` |
| `test_inference_smoke.py` | 同上 |

### 批次 H：其它（6 个）

| 文件 | 退役原因 | 重写到 |
|---|---|---|
| `test_background_tasks.py` | 后台任务通用机制 | `wave-3-protocol-tenant-national/features/observability-cost-quota.feature` |
| `test_sensitive_mask.py` | 敏感数据脱敏 | `cross-cutting/negative-and-guardrails.feature` |
| `test_credential_issue.py` | 凭据发放 | `wave-0-golden-path/features/j1-credential-issue.feature` |
| `test_customer_acceptance_script_contract.py` | 客户验收脚本契约 | `wave-4-legacy-retirement/features/j1-replacement-validation.feature` |
| `test_customer_export_script.py` | 客户导出脚本 | `wave-4-legacy-retirement/features/long-tail-external-coverage.feature` |
| `test_policy_tag_lead_dept.py` | tag_lead_dept 标签位 | `wave-1-j1-j2-closed-loop/features/j2-online-catalog-compile.feature`（牵头部门审核场景） |

## 三、删除前/后 pytest 验证

**删除前**：
```bash
$ .venv/bin/pytest tests/test_role_codes_alignment.py tests/test_contract_projection.py tests/test_packaging.py tests/test_domain_policy.py -v
26 passed, 1 deselected in 2.29s
```

**删除后**（本次 PR）：
```bash
$ .venv/bin/pytest tests/ -q
.......................... 26 passed
```

26 个测试 + 1 deselected (slow_infra) 数量不变，证明删除未连带误伤保留测试。

## 四、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 删 42 个测试后 Wave 实施 PR 找不到对应 setup helpers | 中 | 这些 helpers 都在 `zw_brain/` 主代码或 `conftest.py`（已不存在）；Wave 实施 PR 按 .feature Background 重新写 setup |
| 旧测试中有未察觉的隐式覆盖（如 race condition 检查） | 低 | 26 个保留测试 + 后续 Wave 0 实施 PR 多端到端断言会覆盖；如 merge 后发现真实回归，git revert 单文件即可恢复 |
| CI 矩阵 / `.github/workflows/*` 引用了被删测试名 | 低 | grep 检查 |

## 五、合并后清理

merge 后 30 天，确认 Wave 0 实施 PR 顺利接力，可删除本档案 `.testing/cleanup-plan.md`。
