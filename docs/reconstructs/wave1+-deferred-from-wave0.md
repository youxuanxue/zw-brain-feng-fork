# Wave 1+ Deferred — Wave 0 验收识别项正式归档（W0-08）

> 本期 Wave 0 真数据验收（W0-01..W0-07）过程中识别、但**本期未修复**的全部 deferred 项的单一正式归档。
> 合并自 5 份散落 deferred 笔记 + 1 份浏览器 e2e demo.md §4 findings。**只整理、不修复、不引入新决策**——
> 所有处置已在前 7 wave 落定，本文档仅做汇总、排序、概括与证据回链。

## §1 概述

- Wave 0 共识别 **9 条 deferred 项（D-1..D-9）**：mapper 缺口 2、数据行差 1、feature 文档 1、cross-wave 链路 1、infra 未实现 1、契约漂移 1、设计事实记录 1、perf 1（**D-9 由 W0-08 后客户浏览器复测追加**）。
- 状态分布：**D-5 = Resolved**（path (b) 用户 sign-off，阈值 1% + runtime fixture 真验证）；**其余 8 条 = Deferred**。
- 客户首套部署阻塞评估：**9 条全部「否」**——J1 找数→用数黄金链路（P1→B1.1 渲染 + 申请→审批→凭据→监控写链路）已由 W0-07 真浏览器 e2e 跑通；e2e green 后又用 Jobs 视角追加 ~149 LOC UI/数据展示修复（详见 W0-09-pr-description.md「Jobs 视角 UI/数据修复（AC3 衍生）」节）；D-9 perf 影响进度页加载体感（37s）但不阻塞功能正确性。
- 解冻归属：D-1/D-4/D-6/D-7/D-8/D-9 → Wave 1；D-2 → Wave 1/2；D-5 → 数据治理 Wave 2/3；D-3 → 无需解冻（非 bug）。
- 每条 D-N 均带证据链（源笔记路径 / demo finding / pytest skip / 真数据快照 / 真访问日志），见 §2 总表与 §3 详情。
- 另有 7 项 W0-03/W0-04 UI skip（负向/多账号/时序边缘断言），均**未被正向黄金链路直接闭合**，建议 Wave 1 立「负向 + 多账号 e2e」专项承接，见 §4。

## §2 Deferred 总表（D-1..D-9）

| ID | 类别 | 一句话描述 | 触发 wave | 归属解冻 wave | 客户阻塞 | 证据路径 |
|---|---|---|---|---|---|---|
| D-1 | mapper | ExchangeMapper.data_apply_dept_approve 4 行未处理 | W0-02 | Wave 1 | 否 | W0-02-deferred-candidates.md |
| D-2 | mapper | GovernanceMapper actor_org_role_binding=0 | W0-02 | Wave 1/2 | 否 | W0-02-deferred-candidates.md |
| D-3 | data | verify-time mapping=1249 vs canonical=1222 行差 | W0-02 | 无需 | 否 | W0-02-deferred-candidates.md（非 bug）|
| D-4 | feature | j1-approval-conditional 全文档 Deferred | W0-04 | 同 D-1 | 否 | W0-04-deferred-additions.md |
| D-5 | cross-wave | approval(244)→delivery(26) 10.7%，path (b) Resolved | W0-05 | 数据治理 Wave 2/3 | 否 | W0-05-deferred-additions.md |
| D-6 | infra | AgentRuntime Embedded SDK 完全未实现 | W0-06 | Wave 1（与 ext-agent-pilot 同期）| 否 | W0-06-deferred-additions.md |
| D-7 | contract | 审批角色 .feature(BUSIAUDIT) vs runtime(ORGAN_MANAGER) 漂移 | W0-07 | Wave 1（业务方 sign-off）| 否（运行时自洽）| demo.md §4 finding B |
| D-8 | doc | catalog_code 而非 UUID 作 WebUI URL 主键（设计事实）| W0-07 | Wave 1（API/前端契约文档）| 否 | demo.md §4 finding A |
| D-9 | perf | `request.list` N+1 — 单次调用 ~1300 SQL roundtrip / 37s | W0-08 后客户浏览器复测 | Wave 1（perf hardening）| 否（功能正确，仅体感慢）| `.data/customer-acceptance/wave0/demo-server-v2.log` |

## §3 每条 D-N 详情（按 ID 排）

### D-1 — ExchangeMapper.data_apply_dept_approve 4 行未处理

- **状态**：Deferred
- **触发 wave**：W0-02（legacy 导入灌库）
- **客户首套部署阻塞**：否——J1 无条件共享走单段审批，部门审时间线在无条件分支不渲染。
- **解冻条件**：当 `j1-application-conditional-share`（有条件共享，需部门审批时间线）进入实测射程时解冻；与 D-4 同批。
- **证据路径**：`.data/customer-acceptance/wave0/W0-02-deferred-candidates.md`；灌库 skip 记录见 `W0-02-import.log:117,215`。canonical 目标 = `ApprovalStepRecord(decision_mode="department")`。
- **预估解冻代价**：mapper 改 ≈ 35-40 LOC（跨 3 处）+ 重灌 + verify ≥4 条 'department' 行。
- **复盘**：legacy `dsp_catalog.data_apply_dept_approve` 4 行属部门级审批语义，本期 J1 无条件分支不依赖。

### D-2 — GovernanceMapper actor_org_role_binding=0

- **状态**：Deferred
- **触发 wave**：W0-02
- **客户首套部署阻塞**：否——J1 回退到 `actor.role_code + org_id` 二元组即可完成鉴权与队列分发。
- **解冻条件**：当 J3/B1 后台管理或 J2 挂数维数需要 用户×组织×角色 三元矩阵时解冻。
- **证据路径**：`.data/customer-acceptance/wave0/W0-02-deferred-candidates.md`；投影表 `ActorOrgRoleBindingRecord` 灌库 0 行；亦见 `tests/test_wave0_infra.py:316` skip（D-2 红线）。
- **预估解冻代价**：多表/多方法 mapper > 30 LOC + 重灌。
- **复盘**：GovernanceMapper 缺位为已知红线，J1 现有回退路径自洽。

### D-3 — verify-time mapping=1249 vs canonical=1222 行差（非 bug）

- **状态**：Deferred（信息性记录，**非缺陷**）
- **触发 wave**：W0-02
- **客户首套部署阻塞**：否
- **解冻条件**：无需解冻；行差 27 来自按 `source_ref` 幂等重跑的合并，已是正确语义。
- **证据路径**：`.data/customer-acceptance/wave0/W0-02-deferred-candidates.md`；记录于 `legacy-import-mapping-v1.md`。`legacy_object_mapping.catalog_entry=1249` vs `catalog_entry`(sd-default)`=1222`。
- **预估解冻代价**：0（不需修复）。
- **复盘**：幂等重灌产生的 mapping 与 canonical 行差属预期，文档化即可。

### D-4 — j1-approval-conditional 全文档 Deferred

- **状态**：Deferred
- **触发 wave**：W0-04
- **客户首套部署阻塞**：否——真数据 886 行 `decision_mode='single'`，零 'department' 行，本期无可测有条件共享审批主体。
- **解冻条件**：随 D-1 解冻（根因依赖 D-1 的部门审批投影）；supervisor 4 问门禁 Q1/Q2/Q3=YES、Q4=NO。
- **证据路径**：`.data/customer-acceptance/wave0/W0-04-deferred-additions.md`；`.feature` 头标 `Status=Deferred` + `Defer-Reason` + `Defer-Tracker`。
- **预估解冻代价**：mapper ≈ 35-40 LOC（同 D-1）+ 重灌 + verify ≥4 条 'department' 行 + 写 7-scenario pytest。
- **复盘**：W0-08 将 D-1 + D-4 视作同一解冻批次。

### D-5 — approval(244)→delivery(26) 10.7%（path (b) Resolved）

- **状态**：**Resolved**（path (b) 用户 + supervisor sign-off）
- **触发 wave**：W0-05
- **客户首套部署阻塞**：否——legacy 218/244 已审批但未签发凭据是**真实历史状态**（用户已确认），非导入丢失。
- **解冻条件**：legacy 历史缺口归数据治理 Wave 2/3；新系统 J1 forward flow 已由 runtime fixture 证明完整，与历史缺口正交。
- **证据路径**：`.data/customer-acceptance/wave0/W0-05-deferred-additions.md`；阈值 1%（Jobs decision）；实测 `approved=244 / with_delivery=26 = 10.7% > 1%` → 断言 PASS；`test_runtime_delivery_issue_contract` 经 `BrainService.grant_delivery_access` 真验证 forward grant 落库为已签发终态。
- **预估解冻代价**：本期已用 path (b) 关闭；W0-08 备选 (a) 解冻 D-1 + 映射 `data_apply_authrization` ≈ 60-80 LOC + 重灌（未采用）；(c) defer `j1-credential-issue.feature`（未采用）。
- **复盘**：数据快照 delivery_task=68 / capability_call=744 / approved=244 / with_delivery=26（10.7%）。阈值由初版 60% 下调至 1%，仅作「灌库链路非全断」存在性下限。

### D-6 — AgentRuntime Embedded SDK 完全未实现

- **状态**：Deferred（supervisor sign-off，path b）
- **触发 wave**：W0-06
- **客户首套部署阻塞**：否——J1 不依赖内置 AgentRuntime；非 freeze/IA/credentials 红线。
- **解冻条件**：Wave 1 与 `ext-agent-pilot.feature`（已引 `AGENT.yaml`）同期落地。
- **证据路径**：`.data/customer-acceptance/wave0/W0-06-deferred-additions.md`；SDK / `AGENT.yaml` / CLI 完全缺位；`tests/test_wave0_infra.py:327` skip（needs_human 已 supervisor 决断为 Deferred）。
- **预估解冻代价**：≥200 LOC infra（不含集成测试）。
- **复盘**：团队协同下按确定性自动化原则不支持 ≥200 LOC 推测性 infra 提前实现（violates R7）；Wave 1 与外部 Agent pilot 合并落地最经济。

### D-7 — 审批角色 .feature(BUSIAUDIT) vs runtime(ORGAN_MANAGER) 漂移

- **状态**：Deferred
- **触发 wave**：W0-07
- **客户首套部署阻塞**：否——**前端与后端自洽**（policy.py + WebUI 均 = ROLE_ORGAN_MANAGER），仅 `.feature` 文本是漂移的一侧。
- **解冻条件**：Wave 1 由业务方 sign-off「无条件共享究竟谁审」后统一 `.feature` 文本与 policy。
- **证据路径**：`.data/customer-acceptance/wave0/demo.md` §4 finding B；`zw_brain/domain/policy.py`（`application.resource.review.execute` 仅授 `ROLE_ORGAN_MANAGER`）；`j1-approval-unconditional.feature` 头标 `Roles: ROLE_BUSIAUDIT`。
- **预估解冻代价**：文本对齐 ≈ 数行（取决于业务 sign-off 方向）；本期 scope 红线，不改 .feature、不改 policy。
- **复盘**：e2e 按运行时事实用 ROLE_ORGAN_MANAGER 完成审批，如实记录漂移。

### D-8 — catalog_code 而非 UUID 作 WebUI URL 主键（设计事实）

- **状态**：Deferred（设计事实记录，非缺陷）
- **触发 wave**：W0-07
- **客户首套部署阻塞**：否——WebUI 自始至终用 catalog_code 作资源主键，端到端自洽。
- **解冻条件**：Wave 1 补 API/前端契约文档，明确「资源 URL 主键 = catalog_code」。
- **证据路径**：`.data/customer-acceptance/wave0/demo.md` §4 finding A；`data.search`/`catalog.resource_view` 返回与接收的 `id` 均为 catalog_code（如 `basic-elem:0b26783950004ed882ec9309fae73310`，对应 catalog_entry UUID `c9d54d11-2d37-4d48-aeeb-06ead19df0d4`）。
- **预估解冻代价**：契约文档补充 ≈ 数行；产品代码无需改。
- **复盘**：W0-07 e2e 首跑误用 UUID 导航失败，改用 catalog_code 后通过——属脚本对齐，未动产品代码。

### D-9 — `request.list` N+1（单次 ~1300 SQL roundtrip / 37s）

- **状态**：Deferred（W0-08 客户浏览器复测期间识别，supervisor sign-off path b——超 Wave 0 ≤30 LOC 阈值）
- **触发 wave**：W0-08 后浏览器复测追加（非 W0-01..W0-07 验收主体）
- **客户首套部署阻塞**：否——功能正确，仅"申请进度"页加载体感慢（实测 37 秒）。J1 黄金链路 W0-07 已 7/7 green，不依赖 list 接口低延迟。
- **解冻条件**：Wave 1 perf hardening 立项；可选三种修法（择一）：(a) batch `application_repo.list_records` 与 `legacy_mapping_repo.list_mappings` 一次拉全后内存 join；(b) `_application_record_to_request` 仅在 `request.view` 调用，list 只返摘要字段；(c) 引入 SQLAlchemy session 复用层，去掉 `_legacy_mapping_refs` 每次新开 SessionLocal。
- **证据路径**：`.data/customer-acceptance/wave0/demo-server-v2.log`（监控 dev-only wrapper `.data/customer-acceptance/wave0/run_server_with_logs.py` 抓取的真访问日志，`/api/skill/request.list` 单次耗时 37000+ ms）；代码根因 `zw_brain/command/brain.py:2642-2655 list_requests`（拉全表 → 每条 record 进 `_application_record_to_request`） + `brain.py:2925-3020 _application_record_to_request`（每条 record 触发 5-10 次 SQL：`get_resource` / `_delivery_task_from_record` / `_legacy_mapping_refs` × 2 / `_application_source_evidence` / `_application_history_context` / `_application_quality_evidence`） + `brain.py:5018-5038 _legacy_mapping_refs`（每次调用新开 SessionLocal）。265 records × ~5 hits = ~1300 SQL roundtrips / 调用。
- **预估解冻代价**：选项 (a) batch + 内存 join ≈ 60-80 LOC；选项 (b) list 字段裁剪需先核对 UI 列表实际依赖字段 ≈ 30-50 LOC + 回归；选项 (c) session 复用层 ≈ 40-60 LOC。三选一，均超 Wave 0 ≤30 LOC 阈值，且涉及 list 接口响应形状（违反「基线不漂移」原则）需 Wave 1 立项。
- **复盘**：W0-08 后 supervisor 在客户浏览器复测期间，因原 demo-server.log 无访问日志（`RestHandler.log_message` 被 noop override + Python stdout buffered + `/exit` 杀进程未 flush）创建 dev-only monkey-patch wrapper `run_server_with_logs.py`（带 `print(..., flush=True)` 与状态码捕获）重启服务，复测后捕获到 `request.list` 37 秒主因。同期识别 dropdown 暴露 2 个无 UI 角色（SECURITY_ADMIN / SYSTEM）触发死循环渲染 + 任意角色切换到 denied 路由也会落到 access-denied 死页，**已在 Wave 0 scope 内修复**（`zw-brain-web/index.html` -2 LOC dropdown trim + `app.js` 新增 `pickRoleLandingHash()` + `dispatch()` 改为 deny → 自动跳首个可用落地页 + `pages.js` 删 `renderAccessDeniedShell`），未列入 deferred。

## §4 7 项 W0-03/W0-04 UI skip 状态

W0-07 浏览器 e2e 是 **J1 正向 happy-path**（P1→B1.1 渲染 + 找数→申请→审批→凭据→监控写动作链路）。
下列 7 项 W0-03/W0-04 UI skip 多为**负向/多账号/时序边缘断言**，不在单条正向黄金链路脚本射程内。
逐项闭合状态如下：**0/7 被正向黄金链路直接闭合**，建议 Wave 1 立「负向 + 多账号 e2e」专项承接。

| # | skip 项 | 类型 | 闭合路径 |
|---|---|---|---|
| 1 | j1-resource-discovery：P2 未授权角色拒绝 | 负向 | 未闭合 → Wave 1 负向 e2e（需越权角色专测）|
| 2 | j1-application-draft：AI 一票否决 / AI 助手 DOM | 边缘 | 未闭合 → Wave 1（AI 减摩点 DOM 断言，依赖推理网关 fallback）|
| 3 | j1-application-draft：applicant_org 跨账号拒绝 | 负向 | 未闭合 → Wave 1（dev bypass 单身份不便造跨账号，需多 IAM 账号 fixture）|
| 4 | j1-application-draft：AI 草拟助手提交按钮非 AI 触发 | 边缘 | 未闭合 → Wave 1（反约束 §5.4.5 结构化确认断言）|
| 5 | j1-approval-unconditional：SLA 超时>临期>普通 排序 | 边缘 | 未闭合 → Wave 1（需构造多 SLA 时序申请）|
| 6 | j1-approval-unconditional：非 BUSIAUDIT 角色拒审 | 负向 | **部分澄清**：实测审批授予 ROLE_ORGAN_MANAGER（见 D-7）；负向断言本身未跑 → Wave 1 |
| 7 | j1-approval-unconditional：R11 跨部门队列分发 | 负向 | 未闭合 → Wave 1（跨部门队列需多 org 账号）|

> 注：另有 credential / call 侧多条 UI skip（P4 凭据四件套 / curl 实调 / 配额限流 / 加密展示 / 非 owner 403），
> 其中 curl 实调→API 200→监控显示已由 W0-07 Step6 正向闭合；配额/限流引擎本期不实现属 Wave 1+。
> 本表聚焦 supervisor 指定的 W0-03/W0-04 7 项正向链路覆盖评估口径。

## §5 Wave 0 整体结论

### 验收基准（AC1-AC5）状态

> AC1-AC5 = Wave 0 真数据验收基准；本表即权威记录（含完整定义），保留 Wave 0 当期原始编号。

| AC | 内容 | 状态 |
|---|---|---|
| AC1 | legacy 真数据导入 canonical + 核心表行数 > 0（catalog_entry=1222，sd-default）| ✓ 达成（D-3 行差为幂等语义，非缺陷）|
| AC2 | 11 .feature 配套 pytest 全 Green + Status 推进 | ✓ 达成（4 pytest 50P/25S/0F + 11 .feature 头标更新；infra 5 个 .feature 同期数据层断言一并落 test_wave0_infra.py）|
| AC3 | 浏览器 P1→B1.1 逐页验收 + ≥6 截图归档 | ✓ 达成（W0-07，7/7 green，6 截图）；**衍生：e2e green 后 Jobs 视角追加 5 处 UI/数据展示修复（~149 LOC），详见 W0-09-pr-description.md** |
| AC4 | preflight Green + diff 不引入 Wave 1+ + 改动可反查 W0 编号 | ✓ 达成（W0-09-preflight.log + git diff --stat 限定 Wave 0）|
| AC5 | 本期识别但 Wave 0 范围外的 bug/缺陷/缺口全部归档 + 证据链 + 归属 Wave | ✓ 达成（本文档 D-1..D-9，0 客户首套部署阻塞）|

### 实证数据

- **4 个 pytest 文件**：`test_wave0_j1_discover_draft.py` / `test_wave0_j1_approval.py` / `test_wave0_j1_credential_call.py` / `test_wave0_infra.py`——合计正向断言全 pass，UI/未实现场景 skip 并逐条注明归属（W0-07 / W0-08 / Wave 1+）。
- **Playwright e2e**：`tests/e2e/wave0_j1_golden_path.py` 对活动服务 + 真库（`.data/zw_brain.db`，sd-default，catalog_entry 1222 行）7/7 步骤 green，exit 0。
- **真 REQ 实证**：链路产生申请单 **REQ-2026-05-22-0001**（applicant_org=`市营商环境专班`），复跑按 (user, resource, 日) 去重，application_record 仅 +1（264→265）。

### 惊喜事实

- **正向链路本身 0 处 UI 源码修复**：W0-07 真浏览器 e2e 跑通 J1 P1→B1.1 全链路时，`zw-brain-web/`、`server.py`、`orchestrator/` 路由/鉴权/角色切换/技能投影端到端可用，无需任何源码改动即可 green。
- **e2e green 后的 Jobs 视角追加 ~149 LOC UI/数据展示修复**（不属正向链路阻塞，归 AC3 衍生质量修整）：raw enum 码翻译、未来日期 clamp、mapping 重复行去重、credential resourceName 回退、access-denied 死循环改 fallback redirect、role-switch 下拉去掉 dev-only 角色。详见 W0-09-pr-description.md「Jobs 视角 UI/数据修复（AC3 衍生）」节。

### Jobs 风格决策记录

- **W0-05 path (b)**：用户 + supervisor sign-off，接受 legacy 历史缺口，cross-wave 阈值降至 1% + 新增 runtime fixture 真验证 J1 forward flow（D-5 Resolved）。
- **W0-06 path (b)**：supervisor sign-off，AgentRuntime Embedded SDK 降级 Wave 1 与 ext-agent-pilot 同期，避免团队提前实现 ≥200 LOC 推测性 infra（D-6 Deferred）。

### 引向 W0-09

Wave 0 验收主体（AC1-AC5）已闭合，deferred 项已正式归档且客户首套部署 0 阻塞。
**W0-09 收尾**：preflight.sh green + PR 描述草拟（引 W0-05 用户 sign-off / W0-06 supervisor sign-off / W0-07 6 截图 + 0 UI 修复 / 4 pytest + Playwright e2e / 真 REQ-2026-05-22-0001）+ git diff --stat 限定 Wave 0 范围。merge-to-main 人工。
