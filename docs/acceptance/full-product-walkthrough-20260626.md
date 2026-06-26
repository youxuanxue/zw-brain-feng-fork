# 全量产品走查验收记录（2026-06-26）

## 环境

- Worktree: `/Users/xuejiao/Desktop/History/inspur/cowork/zw/zw-brain-product-walkthrough-20260626`
- Branch: `chore/full-product-walkthrough-20260626`
- Base commit: `18c322a1 fix(webui): restore header logo asset (#344)`
- REST/WebUI: `http://127.0.0.1:8802/zw-brain/`
- Database: `postgresql+psycopg://zw_brain:zw_brain@127.0.0.1:5432/zw_brain_walkthrough_20260626`
- Mode: local dev IAM bypass, role switch enabled, national channel flag enabled
- Backend boot: `scripts/start-local.sh` passed, `/health` returned `webui: true`

## 覆盖范围

- Post-fix route crawl: 35 static/deep-link routes x 5 roles = 175 Playwright visits.
- Screenshots: `.data/product-walkthrough/screenshots-full-postfix/`（175 张）.
- Crawl report: `.data/product-walkthrough/reports/page-crawl-postfix.json`.
- Crawl problem report: `.data/product-walkthrough/reports/page-crawl-postfix-problems.json`.
- E2E by spec report: `.data/product-walkthrough/reports/e2e-postfix-by-spec.json`.
- Visual review screenshots:
  - `.data/product-walkthrough/screenshots/review-p4-delivery.png`
  - `.data/product-walkthrough/screenshots/review-p4-tasks.png`
  - `.data/product-walkthrough/screenshots/review-workbench-busiaudit.png`
  - `.data/product-walkthrough/screenshots/review-platform-assistant.png`

Covered roles:

- 部门操作员 `ROLE_ORGAN_OPERATER`
- 部门管理员 `ROLE_ORGAN_MANAGER`
- 业务运营员 `ROLE_BUSIAUDIT`
- 安全审计员 `ROLE_SECURITY_AUDIT`
- 平台运维员 `ROLE_SYSTEM`

Covered product surfaces:

- P1 工作台
- P2 找数据 / 目录浏览 / 目录详情 / 资源详情
- P3 申请详情 / 审批详情 / 异议 / 供需对接
- P4 领数据 / 交付任务 / 凭据领取
- P5 供数据 / 在线编制 / 目录资源清单 / 数据源 / 反向编目 / API 服务 / 挂接审核 / 供需 / 异议 / 国家扩展要素
- B1.1 查审计
- B1.2 外部系统 / 流程表单 / 身份治理
- B1.3 服务调用监控
- 智能体 / 平台助手入口

## 改造结果

### P4 领数据

- `P4Delivery.vue` 收敛为一个一屏入口：申请进度、授权凭据、交付任务。
- 去掉说明型长段落，首屏改为三段状态条和清晰主动作。
- 我的申请行只保留一个主动作：草稿提交、待补正重新提交、其他查看进度。
- 我的授权行主动作改为领取凭据。
- 交付任务行继续按资源类型分流：文件下载、库表交换任务、API/未知查看授权。
- `p4_delivery_detail.spec.ts`、`webui_smoke.spec.ts` 已按真实 UI 进入 `领数据 -> 交付任务` 验证。

### 工作台下一步

- `workbench_backlog_projection.py` 给待办增加 `nextAction`，让待发布、待转报、待受理、待督办、待汇总等首屏说明下一步。
- `P1Workbench.vue` 渲染 `nextAction`，避免“只有计数、没有下一步”。
- e2e 对 `decision-list` 行内待办按真实 contract 校验每个 item 的 capability。

### 国家通道

- 没有新增入口。国家通道继续归业务事项待办：`国家通道待转报`。
- P5 国家扩展要素页负责编制，工作台负责转报办理。
- `role_projection_views.spec.ts` 已把“待转报”纳入业务运营员职责白名单。

### 平台助手

- UI 和 e2e 统一为“平台助手”/“平台助手问答”。
- 旧“平台指南”断言已清理。
- AgentRuntime 未启用时，客户侧错误文案不暴露内部运行时术语。

### 申请详情授权收回

- 修复路由门：`/request-flow/request/:id` 允许业务运营员进入同一申请详情页，以执行已授权申请的“收回授权/暂停授权”。按钮仍由 action gate 控制。
- `j1_credential_revoke_monitoring.spec.ts` 通过：2 passed, 1 skipped（skip 为本地无 demand_match 前置）。

### 反向编目数据源前置

- `catalog_datasource_walkthrough.spec.ts` 不再假设本地库天然有数据源；若反向编目数据源下拉为空，先经 UI 创建验收数据源，再继续走查。
- M0 脚本判断：本次 worktree 无 `old/` 目录，未导入 old 数据；代码上已有 `DatasourceEndpointMapper` 从 `dsp_pipelines.meta_database` 导入 `datasource_endpoint_projection`。若业务要求冷启动 M0 后反向编目可直接操作，应在 M0 验证加入 `datasource.endpoint.list total > 0`。

## Playwright 走查结论

### 全路由 crawl

- 175 visits completed.
- 10 problem signals all came from故意构造的 missing delivery/task 与 credential 深链：每个角色各 2 条。
- 普通页面无 404/422/console error 问题信号。
- Redirects are expected role guards: OPERATER 12, MANAGER 7, BUSIAUDIT 14, SECURITY 27, SYSTEM 24.

### 全量 e2e by spec

- 已按 36 个 spec 逐文件执行，避免 B2 长流程阻塞整套。
- 原始分文件结果：25 passed, 11 failed。
- 后续修复并重跑重点集合：34 passed, 7 skipped, 0 failed。
- `webui_smoke.spec.ts` 最新结果：14 passed, 4 skipped, 0 failed。
- `catalog_datasource_walkthrough + p4_delivery_detail + role_projection_views + scenario_agents_ui + workbench_todo_closure + j1_credential_revoke_monitoring + webui_smoke` 最新结果：34 passed, 7 skipped, 0 failed。

### 已验证命令

- `npm run build` passed.
- `.venv/bin/python -m pytest tests/test_page_access.py tests/test_request_flow_dissolution.py tests/test_workbench_backlog_projection.py tests/test_datasource_endpoint.py -q` passed: 69 tests.
- `git diff --check` passed.

## 生产数据口径降级

1. **B1.2 身份治理用户列表**
   - 本地验收库无 actor/无角色行，`b12_iam_governance.spec.ts` 用户列表相关断言失败。
   - 你已确认生产有数据；本轮不作为产品阻断。

2. **P2 找数据资源密度 / J1 data gap**
   - 本地库只有少量资源，搜索密度、资源数 `>40`、我的申请 `>5` 等断言不成立。
   - 你已确认生产有数据；本轮不作为产品阻断。`webui_smoke` 对此改为本地数据不足时 skip。

7. **工作台数据量**
   - 本地库待办数据会随 e2e 造数变化；生产有真实数据。
   - 本轮关注“有待办时是否有下一步、是否可办理”，重点回归已通过。

## 剩余验收风险

- **B2 字段元数据 10 列链路**：`b2_field_metadata_10col.spec.ts` 两次卡在 `getByPlaceholder('t_xxx')`，300s 超时。需单独查挂接向导库表资源表名输入区是否已改版、隐藏或前置数据不足。
- **类型化库表资源详情**：`typed_resource_detail.spec.ts` 仍找不到“库表信息”分型块；同文件的“提供部门下拉非空”也受本地资源 provider 为空影响。
- **反向编目两级全链**：`p0_feedback_0611_chain.spec.ts` 链路 2 仍因本地 provider catalogs 的 `schema_ref` 数量为 0，进入 detail 向导后没有可选目录。数据源 CRUD 能自建前置数据，但两级审核全链还需要 schema_ref/catalog 前置。
- **AgentRuntime 真实问答**：本地 `/health` 显示 `agent_runtime.enabled=false`，真实往返用例按设计 skipped；平台助手降级文案已通过。

## 乔布斯式复审结论

- 领数据现在更像产品入口，不再像三张后台表拼在一起；用户只需要判断“我现在在申请、拿凭据，还是领交付”。
- 工作台的关键不是多一个入口，而是每条待办都告诉人下一步做什么；`nextAction` 把这个补上了。
- 国家通道不该成为新导航。它是某类申请的下一步，放在工作台办理是更少、更清楚的选择。
- 平台助手统一命名是对的，避免“智能体/指南/助手”在同一屏讲三套语言。
- 下一阶段别再扩大入口，优先补数据契约和 B2/类型化详情这类会让用户在真实流程里停下来的断点。
