# J2 30 分钟客户演示验收脚本（F6）

> e2-j2-journey AC5：业务方在 sd-default 真实数据上跑通 J2 提供方旅程
> （在线编制 → 资源挂接 → 3 层审批 → 发布 → 异议响应 → 评价）并签字。
> J2 独立于 J1（J1 演示见 [`customer-demo-j1.md`](customer-demo-j1.md)）。

## 演示路径

P5 提供方管理面，sd-default 真实数据（M0 一次性迁移产出），无 mock：

1. **STEP-1 在线编制** — `catalog.entry.create_draft` 新建 J2 demo catalog
   （ROLE_ORGAN_OPERATER，owner_org_id 取自真实 table 资源 owner）
2. **STEP-2 补元数据** — `catalog.entry.update` 写 summary_json
3. **STEP-3 资源挂接** — `catalog.resource.bind` 挂一个真实 `resource_kind=table`
   资源（M0 已加载 66 条；F2 fixture 路径同源）；handler 反射 `materialization_kind="table"`
4. **STEP-4 提交部门审** — `catalog.entry.submit_review` → `pending_review`
5. **STEP-5 部门审 (F1 3 层第 1 步)** — `catalog.entry.review approve`
   （ROLE_ORGAN_MANAGER → `pending_platform_review`，stage-aware 判定）
6. **STEP-6 平台审 (F1 3 层第 2 步)** — `catalog.entry.review approve`
   （ROLE_BUSIAUDIT → `approved_pending_publish`）
7. **STEP-7 发布 + 自动重复率检测 (F3)** — `catalog.entry.publish` → `active`
   ；envelope 自带 `duplicate_warnings` 数组（非硬拦；F3 catalog.duplicate.check 前置自动触发）
8. **STEP-8 创建异议** — `objection.case.create`（catalog 维度，申请方 OPERATER
   对本 demo catalog 发起字段描述异议）
9. **STEP-9 异议生命周期** — `submit` + `assign(platform_investigating)`
   + `assign(provider_investigating, handler_org_id=provider_org)`
10. **STEP-10 提供方响应 (F4)** — `objection.case.reply`
    （ROLE_ORGAN_MANAGER, handler_org_id=provider_org）
11. **STEP-11 review → resolved** — `objection.case.review decision=resolve`
12. **STEP-12 申请方评价** — `objection.case.evaluate` (rating + comment)
13. **STEP-13 归档** — `objection.case.close` (额外收官，保 lifecycle 完整闭环)

## 依赖

1. `uv sync --extra dev` — 安装 .venv 与 pytest
2. `.data/zw_brain.db` 存在（跑一次 M0 acceptance）：

```bash
bash scripts/customer_acceptance_up.sh
# 或带显式 dumps 路径：
ZW_BRAIN_LEGACY_DUMPS_DIR=/path/to/old/10示例数据 \
ZW_BRAIN_LEGACY_DATASTRUCTURE_DIR=/path/to/old/12-datastructure \
    bash scripts/customer_acceptance_up.sh
```

> M0 acceptance 整体可能 fail（apply_failed → repeat_apply skipped 幂等校验
> debt），但 F6 J2 演示仅依赖 `catalog_entry / resource_asset(resource_kind=table)`
> 加载完整即可。其余 4 物化（file/api/url/folder）由 M0 mapper 独立 chip 解锁后
> 转 demo 多样化展示，本期未启用。

## 跑演示

```bash
bash scripts/customer_demo_j2.sh
```

### P5 浏览器面冒烟（F6/F8，可选）

后端 demo 通过后，在本 **worktree** 构建 WebUI 并启动 REST（勿占用他处旧 8800 进程）：

```bash
cd zw-brain-web && npm install && npm run build
ZW_BRAIN_REST_PORT=8801 bash scripts/start-local.sh   # 8800 已被其它 clone 占用时
ZW_E2E_BASE_URL=http://127.0.0.1:8801 .venv/bin/python3 tests/e2e/wave1_j2_provider_p5_smoke.py
```

- 退出码 `0`：四条 inbox + 反向编目 wizard 均不含「功能建设中」
- 退出码 `2`：`{ZW_E2E_BASE_URL}/health` 不可达（跳过，非失败）
- 截图：`.data/customer-acceptance/wave1/screenshots/provider-p5-smoke/`

退出码：

- `0`：全链路成功；log 落于 `.data/customer-demo-j2/demo-<ts>.log`，
  JSON 报告落于 `.data/customer-demo-j2/demo-<ts>.json`
- `1`：步骤异常（Python driver 抛错）
- `2`：assertion 失败
- `3`：超 30 分钟预算（DEFAULT_BUDGET_SECONDS = 1800s）

## 验证证据（演示完成后输出）

JSON 报告字段：

- `ok`: true
- `elapsed_seconds`: 实际耗时（脚本驱动 < 5s；30 分钟预算预留给业务方现场演示讲解）
- `catalog_code` / `resource_code` / `objection_id`：本次 demo 创建的实体 ID
- `provider_org`: 资源提供方部门（owner_org_id）
- `audit_event_total`：全链路 audit_event feed 总条数
- `audit_event_types_covered`：14 类（F1+F2+F3+F4 核心 skill 全部触发）
- `duplicate_check_triggered`: true（F3 publish 路径自动前置触发证明）
- `duplicate_warnings_count`: 0 或 N（首次 demo 通常 0；重复 demo 可触发 N>0）
- `capability_call_total` / `capability_call_core_missing`: 持久化 capability_call
  覆盖；core_missing 应为空数组（所有 F1/F3/F4 核心 skill 都落账）
- `quality_flags`：8 项布尔，逐项标注 F1-F5 哪些覆盖了真数据 / 哪些待 M0 chip 解锁

期望证据矩阵（业务方可逐项核对）：

| 检查项 | 期望值 | 来源 |
|---|---|---|
| catalog 创建到归档全链路 | active 状态达成 | STEP-7 publish 出 `lifecycle_status=active` |
| 3 层审批每个角色至少触发 1 次 | MANAGER + BUSIAUDIT 各 1 次 review | STEP-5/6 audit_event |
| 异议 7 步事件全部落账 | create+submit+assign×2+reply+review+evaluate+close | STEP-8 ~ 13 audit_event |
| duplicate.check capability_call ≥ 1 条 | true | STEP-7 publish 自动触发 |
| F2 table 物化真数据挂接 | resource_code 来自 sd-default 真行 | STEP-3 报告字段 |

## 已知 partial（非 demo blocker，仅 transparent 警示）

- **F2 file / api 物化 e2e 仍 SKIP**：M0 mapper 跨界缺位 — `rc_resource_catalog_item_link`
  当前仅覆盖 table 类资源 → file / api 类 resource_schema_mapping = 0；
  snapshot.resource_code 不规范化到 resource_asset.resource_code（5560 unique
  snapshot 中仅 5 个能 JOIN 回 table 资源）。本 demo 走 table 物化代表通过；
  file/api demo 待独立 M0 mapper PR merged 后启用。
- **P5 异议响应面 UI**：blocked-on E5 webui 重建；本演示走 API 路径。

## 回滚

演示用 shadow DB (`.data/customer-demo-j2-shadow.db`)；每次 sh 启动会 unlink 重建，
不污染 seed DB。**无需手工回滚**。

如要保留某次 shadow DB 作故障回溯：

```bash
cp .data/customer-demo-j2-shadow.db .data/customer-demo-j2-backup-<reason>.db
```

## 业务方 sign-off 流程

1. **本地或 CI 跑通** `bash scripts/customer_demo_j2.sh` 退出码 0
2. **PR 描述** 贴最新 `.data/customer-demo-j2/demo-<ts>.json` 关键字段：
   - `ok: true` / `elapsed_seconds` / `catalog_code` / `objection_id`
   - `quality_flags`（业务方关注 f1/f3/f4 必 true；f2 file/api 当前 false 是已知 partial）
3. **业务方 review** 在 PR 评论中确认演示路径与 sd-default 数据真实性
4. **sign-off 凭证**（D46.d，账本是真相）：PR 加 label `signoff:<scope>` + body `<!-- signoff ... -->` 机读块（`scope` / `kind: 效果验收` / `covers`）。合并时 `signoff_from_pr.py` 自动落 `.testing/signoff/<scope>.signoff.yaml` 账本（`signed_by`=approvers，`date`=merged_at）
5. **审计留档**：sign-off 截图归入 `docs/approved/` 或 PR comment 永久附属

### 业务方现场填写区段（sign-off 时由业务方手动填）

| 字段 | 业务方填 | 备注 |
|---|---|---|
| 业务方姓名 / 部门 |  |  |
| sign-off 日期 (YYYY-MM-DD) |  |  |
| 演示版本 commit SHA |  | `git rev-parse HEAD` |
| 实际跑通 demo JSON 报告路径 |  | `.data/customer-demo-j2/demo-<ts>.json` |
| 路径偏差（如有） |  | 比如 step 跳过 / 替换为 manual 操作 |
| 业务方 sign-off 文字 |  | "确认 J2 提供方日常旅程可用 — <姓名>" |

## 与 E1 J1 / E5 UI 协作边界

- **J1 (E1)**：申请方旅程；演示见 [`customer-demo-j1.md`](customer-demo-j1.md)；
  与 J2 互不重叠。J1 demo 命中 3 个真实 catalog（医疗救助/医保码/异地就医）；
  J2 demo 新建一个 demo catalog 走完提供方端到端。
- **E5 UI**：P5 提供方管理面 + 异议响应面 UI 嵌入 blocked；本演示仅 API 路径，
  webui 重建后由 E5 worker 把 catalog.duplicate.check + objection.case.query
  (F4 新增的 target_ref/target_org_id/dimension filter) 接入 P5 页面。
- **M0 mapper PR**：解锁 F2 file/api 物化 e2e 转 PASS；merge 后本 demo 可扩展
  `quality_flags.f2_*_materialization_real_data` 全 true。

## CI 集成

`tests/test_wave1_customer_demo_j2.py` 在 CI 上通过 import driver 跑全链路 +
断言关键证据字段；真数据缺位时 module-level skip。
