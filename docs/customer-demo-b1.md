# B1 30 分钟客户演示验收脚本（F8）

> e4-b1-agentruntime AC6：30 分钟客户演示能完整跑通 B1.1 合规审计 + B1.2 接入扩展中心，
> 业务方 + 安全审计员在 sd-default 真实数据 + 合成审计事件 上双方签字。

## 演示路径

ROLE_SECURITY_AUDIT 跑 B1.1 审计 4 panel；ROLE_BUSIAUDIT 跑 B1.2 能力包 lifecycle。
真实数据来自 M0 一次性迁移产出 (`sd-default` tenant)；审计事件用 audit_bus.emit 合成
（无 mock LLM）：

### B1.1 合规审计（5 步）

1. **STEP-1** 合成 13 条审计事件（4 ok / 4 high-fail / 3 deny-loop / 2 含敏感字段）
2. **STEP-2 statistics** — `audit.event.statistics` day 桶 × audit_class 维度聚合
3. **STEP-3 anomaly** — `audit.event.anomaly` 命中 high-failure-rate + repeated-denied 双规则
4. **STEP-4 accountability** — `audit.event.accountability` 拉 BAD_ACTOR 拒绝链 + 验脱敏
   （credential 原文不出现在响应里）
5. **STEP-5 investigation_summary** — `assistant.investigation_summary` 走推理回落
   规则摘要路径（不调用第三方 LLM；集团推理平台未配凭证时仍可演示）

### B1.2 接入扩展中心（6 步）

6. **STEP-6** 注入 draft 状态演示能力包 `PKG-DEMO-B1-001`
7. **STEP-7 review_decide** — `package.review_decide` approve → status=approved
8. **STEP-8 enable** — `tenant.capability.enable` 启用到 sd-default（write-critical 审计）
9. **STEP-9 exposure_matrix** — `package.exposure.matrix.query` 200+ manifest × 5 surface 投影
10. **STEP-10 trust_level** — `package.trust_level.update` baseline → reviewed
11. **STEP-11 rollback** — `package.rollback` v1.2.0 → v1.1.0，status → rolled-back

## 依赖

1. `uv sync --extra dev` — 安装 .venv 与 pytest
2. `.data/zw_brain.db` 存在（跑一次 M0 acceptance）：

```bash
uv run python -m zw_brain.entry.legacy_migration.main \
  --dumps-dir /Users/xuejiao/Desktop/History/inspur/cowork/zw/zw-brain/old/10示例数据 \
  --db-path .data/zw_brain.db \
  --reset-db \
  --report .data/m0-report.json \
  --acceptance
```

> 不像 J1/J2 demo 依赖 `legacy.objection.import` / `legacy.exchange.import`，
> B1 demo 只需要 schema 就绪（capability_call / audit_event 表）+ sd-default tenant 注册；
> M0 子段任一 partial_failure 不阻塞本 demo。

## 跑演示

```bash
bash scripts/customer_demo_b1.sh
```

退出码：

- `0`：全链路成功；log 落于 `.data/customer-demo-b1/demo-<ts>.log`，
  JSON 报告落于 `.data/customer-demo-b1/demo-<ts>.json`
- `1`：步骤异常（Python driver 抛错）
- `3`：超 30 分钟预算（DEFAULT_BUDGET_SECONDS = 1800s）

## 验证证据（演示完成后输出）

JSON 报告字段：

- `ok`: true
- `elapsed_seconds`: 实际耗时（脚本驱动 < 10s；30 分钟预算预留给现场讲解）
- `b11.statistics_scanned`: 审计事件扫描数（≥ 13）
- `b11.anomaly_rules_hit`: 命中规则列表（应含 `high-failure-rate` + `repeated-denied`）
- `b11.accountability_chains_total`: 拒绝链路条数（≥ 2）
- `b11.investigation_summary_model`: 推理模型（含 LLM 凭证时 `claude-sonnet-4-7`；
  无凭证时 `rule-fallback`，仍合法）
- `b12.manifest_total`: 暴露矩阵 manifest 数（≥ 200）
- `b12.trust_level_after`: `"reviewed"`
- `b12.registered_version_after_rollback`: `"v1.1.0"`
- `b12.status_after_rollback`: `"rolled-back"`
- `capability_call_total`: 全链路 capability_call 表总条数
- `capability_call_required_covered`: 9 条 capability slug 全覆盖

## 回滚

演示用 shadow DB (`.data/customer-demo-b1-shadow.db`)；每次 sh 启动会 unlink 重建，
不污染 seed DB。**无需手工回滚**。

如要保留某次 shadow DB 作故障回溯：

```bash
cp .data/customer-demo-b1-shadow.db .data/customer-demo-b1-backup-<reason>.db
```

## sign-off 流程（双签）

B1 涉及合规审计 + 能力包治理两个权责域，需 **业务方 + 安全审计员** 双签：

1. **本地或 CI 跑通** `bash scripts/customer_demo_b1.sh` 退出码 0
2. **PR 描述** 贴最新 `.data/customer-demo-b1/demo-<ts>.json` 关键字段
3. **业务方 review** B1.2 能力包 lifecycle 5 步 + 暴露矩阵投影是否符合接入扩展中心预期
4. **安全审计员 review** B1.1 4 panel 是否能识别合成的高失败率 + repeated-denied + 敏感
   字段脱敏是否生效（accountability 响应里不能出现 credential 原文）
5. **sign-off 凭证**（D46.d，账本是真相）：PR 加 label `signoff:<scope>` + body `<!-- signoff ... -->` 机读块（`kind: 双签` — 业务方 + 安全审计员；`covers`: 被签 .feature）。合并时 `signoff_from_pr.py` 自动落 `.testing/signoff/<scope>.signoff.yaml` 账本，`signed_by`=PR approvers（两位 reviewer）
6. **审计留档**：sign-off 截图归入 `docs/approved/` 或 PR comment 永久附属

## 已知非阻塞约束

- 全链路依赖 BrainService.invoke_skill 直驱（不起 REST server），与
  `scripts/customer_demo_5min.sh` 起 REST 路径互补
- `assistant.investigation_summary` LLM 真路径需集团推理平台凭证；本地无凭证时走
  规则回落（`model="rule-fallback"`），契约/演示无差异
- UI 浏览器手验（B1.1 4 panel + 调查助手 / B1.2 3 tab）由 E5 F17 b12_intake.spec.ts +
  E5 F16 b11_compliance.spec.ts e2e 覆盖；本演示走 API 路径
- AgentRuntime Registry 4 字段（runtime_spec_version / agent_yaml_ref / trust_level
  Registry-side / workspace_required）由 T1 触发（首个真实外部 Agent 接入需求当日
  落地）；本期 manifest schema 不含这些字段（R15 T1 触发式延后）
- **B1.2 lifecycle 连续性**：脚本在 `review_decide → enable` 之间用直接置位代替
  `capability.version.submit`（推 versionStatus draft→registered），在
  `enable → rollback` 之间用直接置位代替 activation（推 status→active）；演示中
  保持 lifecycle 流畅，生产中由对应 cap 各自驱动。客户问及 "submit / activate
  在哪？" 时单独 demo 这两条 cap（`capability.version.submit` handler 见
  `zw_brain/command/handlers/b1/capability_admin.py`）
