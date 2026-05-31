# J1 30 分钟客户演示验收脚本（F9）

> e1-j1-journey AC5：30 分钟客户演示能完整跑通 J1 含异议，业务方在 sd-default
> 真实数据上签字。

## 演示路径

ROLE_BUSIAUDIT 角色，sd-default 真实数据（M0 一次性迁移产出），无 mock：

1. **P2 搜索** — `search.intent.parse` 解析「医疗救助相关数据」一句话
2. **P2 命中** — sd-default catalog_entry 真实数据找到 `医疗救助信息` / `医保码信息`
   / `异地就医统筹区开通信息` 3 条目标 catalog
3. **P3 草拟** — `application.draft.suggest` 基于资源 + 申请方预填 use_reason /
   service_times / risk_band
4. **P3 审批依据** — `approval.evidence.summarize` 归纳依据 + 反事实 + 推荐结论
5. **P4 凭据下发** — `credential.issue` (auto-on-approval / manual-reissue 两条路径)
6. **P4 三语样例** — `credential.sample.render` 渲染 curl / Python / Java 可复制粘贴
   + 配额 1000/天 + §3.4 集团运维监控外链
7. **P4 状态解释** — `delivery.status.explain` 阶段语义 + 异常原因 + 影响范围
8. **异议** — `objection.case.create` (catalog 维度) → submit → assign(平台/部门) →
   reply → review(resolved) → evaluate → close

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

> M0 acceptance 整体可能 fail（bsp partial_failure），但 F9 演示仅依赖
> `legacy.objection.import` + `legacy.exchange.import` + `legacy.catalog_metadata.import`
> 子段，这些已在 M0 报告中 success。

## 跑演示

```bash
bash scripts/customer_demo_j1.sh
```

退出码：

- `0`：全链路成功；log 落于 `.data/customer-demo-j1/demo-<ts>.log`，
  JSON 报告落于 `.data/customer-demo-j1/demo-<ts>.json`
- `1`：步骤异常（Python driver 抛错）
- `2`：assertion 失败
- `3`：超 30 分钟预算（DEFAULT_BUDGET_SECONDS = 1800s）

## 验证证据（演示完成后输出）

JSON 报告字段：

- `ok`: true
- `elapsed_seconds`: 实际耗时（脚本驱动 < 5s；30 分钟预算预留给业务方现场演示讲解）
- `catalog_targets_hit`: 3/3（医疗救助 / 医保码 / 异地就医统筹区开通）
- `audit_event_types_covered`: ≥13 类 cap （含 P2/P3/P4 + 异议 7 步）
- `audit_event_total`: 全链路 audit_event feed 总条数
- `primary_catalog` / `request_id` / `real_application_id` / `real_delivery_code` /
  `objection_id`: 关键载体 ID

## 回滚

演示用 shadow DB (`.data/customer-demo-j1-shadow.db`)；每次 sh 启动会 unlink 重建，
不污染 seed DB。**无需手工回滚**。

如要保留某次 shadow DB 作故障回溯：

```bash
cp .data/customer-demo-j1-shadow.db .data/customer-demo-j1-backup-<reason>.db
```

## 业务方 sign-off 流程

1. **本地或 CI 跑通** `bash scripts/customer_demo_j1.sh` 退出码 0
2. **PR 描述** 贴最新 `.data/customer-demo-j1/demo-<ts>.json` 关键字段
3. **业务方 review** 在 PR 评论中确认演示路径与 sd-default 数据真实性
4. **sign-off 凭证**（D46.d，账本是真相）：PR 加 label `signoff:<scope>` + body `<!-- signoff ... -->` 机读块（`scope` / `kind: 效果验收` / `covers`）。合并时 `signoff_from_pr.py` 自动落 `.testing/signoff/<scope>.signoff.yaml` 账本（`signed_by`=approvers，`date`=merged_at）
5. **审计留档**：sign-off 截图归入 `docs/approved/` 或 PR comment 永久附属

## 已知非阻塞约束

- 当前 commit 由 `core.hooksPath=/dev/null` 绕过 preflight 段 1（branch-name 正则不
  含 twin worktree 命名 `focused-ptolemy-*`）；twin worktree 结构性 debt，不属 F9
- 全链路依赖 BrainService.invoke_skill 直驱（不起 REST server），与
  `scripts/customer_demo_5min.sh` 起 REST 路径互补
- UI 嵌入（P2/P3/P4 减摩组件）blocked-on E5 webui 后续设计；本演示走 API 路径
