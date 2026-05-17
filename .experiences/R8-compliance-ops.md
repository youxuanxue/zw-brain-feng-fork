# R8 合规运营/督查人员：用证据证明减负和追责

## 这一页解决什么事

你要回答三个问题：是否真的减少重复要数，是否有人绕开平台，目录/资源/授权/投影哪里断链。旧平台里的工单、审核日志、资源流转、统计、质量、血缘能力都要承接为可审计证据，但不得把原始工单人员信息、内部地址或附件内容写进产品文案。

## 你手上拿到的真实输入

- 抽查主题：`医疗救助信息`、`医保码信息`、`停车场信息`。
- 问题模式：目录发布后不可见、申请通过但授权未生效、挂接资源不显示列、M0 验收证据缺失、质量报告异常、血缘断链、绕行导出。
- 证据来源：M0 来源证据、`approval_case`、`delivery_task`、resource flow log、projection status、quality projection、lineage projection。
- 状态：`已核查`、`已驳回`、整改中、已闭环。
- 指标：重复申请、退回率、授权生效率、投影失败率、基层补差字段数、来源证据缺口、绕行导出风险。
- 治理大盘入口：旧 `data-operation-board-front` 的 overview、integration、governance、data-usage、data-objection、direct-data-access；`/catalog`、`/resource` 是目录 / 资源运营视图，由 R7 / R6 主责，R8 仅做断链抽查。
- 安全前端入口：旧 `datasecurity-front` 的子模块 `dataAudit/{managementAudit, auditAccess}`、`dataDesensitization/{algorithm, dynamicDesensitization, staticDesensitization, staticTask, policy}`、`dataEncryption/{key, encryption, passwordApp}`、`dataIdentification/{rules, groups, tasks, record, sensitive, whitelist}`、`risk/{rule, warningevent, auditlist}`、`situation`、`assetsData/source`、`system`；R8 主用作访问审计 / 管理审计 / 脱敏策略 / 加密密钥 / 敏感识别记录 / 风险规则与预警 / 态势 projection / 资产数据来源等证据。`system` 是平台运维面，不归 R1-R8。
- 撤回审核独立审计视角：旧 `catalog-front /res-revoke-examine` 在 R7 业务影响审之外，本端做"撤回是否绕过审批 / 是否静默断订阅 / 是否被用作规避审计"的独立审计。
- 异议绕行督查：旧 `dsp_handling / data_objection` 四子流程（评估/处置/授权/用数）若被线下推进，本端从用数方反馈、授权回执、交付时间差等线索回溯。
- 自动检测失败督查：旧 `catalog_quality_task_log` 失败 / 超时 / 反复重跑模式由本端定位是执行器问题、规则口径问题还是数据源问题。
- 数据直达绕行抽查：dc_catalog / dc_datasource 必须只读；任何越过 `application_record` 写入 dc 的请求都属高风险。
- 旧状态映射：旧 `草稿(0)/待审核(1)/审批通过(2)/审批驳回(3)/已发布(4)/下线(5)` + 独立 `revoke_status` ↔ 新 `draft/pending_review/approved_pending_publish/active/suspended/revoked`；完整映射以 catalog3-metadata3 重构方案 §八 状态机为基线判断。

## 一条主旅程

1. 进入合规运营视图，选择本周期重点目录和部门，例如民生保障专题下的 `医疗救助信息`。
2. 先看重复申请和新增采集趋势，判断 R1/R2 是否真的先复用后新增。
3. 抽查 M0 验收结论是否被日常链路正确引用：来源证据是否可追溯，验收后是否仍有运行时兼容或线下导出。
4. 抽查一条申请链：目录发现、申请、审批、补录、汇总、授权、交付、回流是否都在平台内完成。
5. 对“目录发布后不可见”下钻：目录状态、发布审计、共享专题 projection、搜索 projection 哪一步失败。
6. 对“申请通过但授权未生效”下钻：`approval_case` 是否 approved，`delivery_task` 是否有授权快照和回执。
7. 对“挂接资源不显示列”下钻：目录项、资源、schema 快照和 `resource_schema_mapping` 是否一致。
8. 对质量检测报告异常下钻：检测规则、自动检测任务、人工质量检测和字段口径是否一致。
9. 对血缘断链或目录关系图谱异常下钻：lineage projection 是否缺来源、去向、字段关系或外部执行器回执。
10. 对治理大盘下钻：overview 看总体趋势，integration 看外部通道，governance 看规则执行，data-usage 看用数，data-objection 看异议，direct-data-access 看直达交付是否已审批。
11. 对安全前端下钻：用 `dataAudit/managementAudit` 与 `dataAudit/auditAccess` 解释管理审计与访问审计；用 `dataDesensitization` 与 `dataEncryption` 子模块解释脱敏与加密策略；用 `dataIdentification` 子模块解释敏感识别与白名单；用 `risk/{rule, warningevent, auditlist}` 解释风险规则、预警与处置；`situation` 看态势 projection；`assetsData/source` 看资产数据来源。`system` 是平台运维面，不归 R1-R8。
12. 输出整改建议：收紧准入、补齐字段证据、修复投影、调整共享说明、提交 M0 验收缺口、修复安全策略或升级外部执行器问题。
13. 对资源撤回审核做独立审计：撤回是否走 `approval_case`、是否有撤回理由、是否有"替代资源或订阅终止方案"、订阅用户是否收到影响摘要、active 版本切换是否保留上一版本可回放；任一环节缺失视为审计断链。
14. 对异议处理四子流程做绕行督查：评估、处置、授权、用数四段是否每段都在 `data_objection` projection 留痕；从用数方反馈时间、授权回执时间、交付时间差中回溯是否有线下处置。
15. 对自动检测任务做失败督查：分类是执行器问题（外化）、规则口径问题（转 R6）、数据源问题（转 R6 / M0 来源）、还是任务模板问题（转 R7）；不让"任务失败 → 默认通过"成为隐性绕行。
16. 对数据直达绕行做抽查：检查是否有未经 `application_record` 直接对 dc_catalog / dc_datasource 取数的痕迹；任何"数据库直连"声称的"数据直达"都视为高风险。
17. 对 API 服务化交付做绕行抽查：检查 IP 白名单变更是否走审批、限流/熔断是否被临时放开、订阅应用是否越权、错误样本是否回流敏感字段；任一项异常都立即熔断。

## 关键判断点

| 你看到什么 | 该怎么判断 | 系统证据 |
| --- | --- | --- |
| 同主题重复申请仍高 | R1/R2 复用链路没有生效 | `application_record`、目录发现日志 |
| 发布状态 active 但门户不可见 | projection 或可见策略断链 | projection status、审计回执 |
| 审批 approved 但授权无效 | 交付链或授权回写断链 | `delivery_task.access_grant_snapshot` |
| 资源挂接后无字段 | schema 或 mapping 证据缺失 | `resource_schema_snapshot`、`resource_schema_mapping` |
| 质量/血缘显示风险 | 只能作为解释证据，不能直接改业务状态 | quality / lineage projection |
| 日常链路引用的 M0 验收证据缺失 | 不能当作合规结论 | M0 acceptance receipt、source evidence reference |
| 资源流转日志断裂 | 定位缺失审批或外部执行器回执 | resource flow log、audit event |
| 发现线下导出绕行 | 追责授权边界和交付链缺口 | `delivery_task`、ops issue projection |
| 数据直达没有审批回执 | 视为绕行风险，不算合规交付 | 数据直达交付回执、approval case |
| 安全策略与授权结果冲突 | 暂停高风险交付，回到策略和审批链 | security policy snapshot、access audit |
| 敏感识别或脱敏失败 | 不交付原始数据，转 R6/R7 修字段证据 | classification/desensitization evidence |
| 撤回未经审批静默断订阅 | 视为审计断链；要求补撤回审批与影响摘要 | 撤回审计、`delivery_subscription` |
| 异议处置时间早于评估留痕 | 视为线下绕行；要求重新进 `data_objection` projection | `data_objection_*` projection 时间线 |
| 自动检测任务长期失败但未触发整改 | 视为"默认通过"风险；强制升级到 R6/M0 责任环节 | task log、quality projection |
| 数据直达交付清单出现无审批回执条目 | 视为绕行；锁定相关 dc_datasource 只读 | direct-access projection、approval case |
| API IP 白名单临时放开后未回收 | 视为越权风险；立即收回并审计 | `api_access_ip` 历史变更 |
| API 错误样本含敏感字段回流 | 立即熔断并要求 R6 修脱敏档位 | `api_service_errors`、字段策略快照 |

## 异常分支

- **链路有断点**：标记断点环节、责任角色和缺失证据，不用“系统问题”笼统归因。
- **指标短期改善后反弹**：检查是否出现线下要数或绕行路径。
- **高频争议重复出现**：升级为目录口径、授权策略或外部执行器改造项。
- **projection 与业务事实不一致**：修 projection，不反向改目录或授权事实。
- **工单证据含敏感信息**：只保留脱敏问题模式和处置摘要。
- **M0 验收证据显示部分对象未覆盖**：标记缺口对象和影响目录，不用“总体成功”掩盖不可交付资源；补救动作回到 M0 缺口处理。
- **目录关系图谱与业务事实不一致**：修 projection 和血缘证据，不反向改目录或授权状态。
- **发现线下导出替代交付**：记录绕行模式，回到 R2/R7 修授权和交付链路。
- **数据直达被当成数据库直连**：标记高风险，要求回到已审批、可追踪交付。
- **安全前端发现敏感字段未标注**：暂停相关交付，要求 R6 补字段安全证据，R2/R7 重算授权边界。
- **风险处置建议试图直接改业务事实**：只形成整改和策略建议，不直接改目录、资源或授权状态。
- **撤回审核被绕过**：撤回未经 `approval_case` 视为审计断链，强制补审；订阅用户必须收到影响摘要。
- **异议四子流程出现线下处置**：用授权回执 / 用数反馈时间差回溯证据；不接受"已私下解决"作为关闭依据。
- **自动检测任务长期失败被默认通过**：升级为 R6 规则问题或 M0 来源缺口；不让失败变成静默关单。
- **API 调用错误样本回流敏感字段**：立即熔断，要求 R6 修脱敏档位、R2 复核授权策略。
- **数据直达被改写为数据库直连**：标记高风险，回到已审批主链路；dc_catalog / dc_datasource 锁只读。

## 成功判据

- 你能用平台证据回答“是否真的减负”。
- 每条治理结论都能回溯到目录、资源、审批、交付、projection 或 M0 来源证据。
- 对断链问题能定位到发布、投影、授权、schema、mapping 或外部执行器。
- 治理动作可持续复盘，而不是一次性通报。

## 旧平台能力在这里怎么落地

| 旧平台能力 | zw-brain 表达 | 用户感知 |
| --- | --- | --- |
| 审批日志 `audit_todo_task` / `resource_flow_log` | `approval_case` / audit receipt | 查谁在何时做了什么决定 |
| M0 验收结论 | M0 acceptance receipt + source evidence reference | 追溯来源验收结论，不在 R8 执行补救 |
| 目录/资源统计接口 | ops projection | 看减负和复用是否真实发生 |
| 质量检测 `catalog_quality_task*` | quality projection | 解释字段和目录质量风险 |
| 血缘关系 `meta_relation*` | lineage projection | 解释影响范围和来源去向 |
| 目录关系图谱 | relationship projection | 看目录、资源、部门和申请的断链位置 |
| 绕行导出风险 | ops issue projection + delivery audit | 查为什么用户离开平台拿数 |
| overview / integration / governance / data-usage / data-objection / direct-data-access | governance ops projection | 治理大盘用于定位断链，不替代业务事实 |
| 数据分级分类 / 脱敏 / 加密 / 敏感识别 | security evidence projection | 安全结果解释授权边界和交付方式 |
| dataAudit/managementAudit / dataAudit/auditAccess | 管理审计 / 访问审计 projection | 解释谁在何时访问 / 调整安全策略 |
| dataDesensitization/{algorithm,dynamicDesensitization,staticDesensitization,staticTask,policy} | 脱敏策略与任务证据 | 解释字段脱敏档位，不直接改目录 |
| dataEncryption/{key,encryption,passwordApp} | 加密密钥与服务证据 | 解释字段加密策略 |
| dataIdentification/{rules,groups,tasks,record,sensitive,whitelist} | 敏感识别证据 | 解释字段敏感等级与白名单 |
| risk/{rule,warningevent,auditlist} | 风险规则 / 预警 / 处置审计 | 形成整改建议 |
| situation | 态势 projection | 不反写事实 |
| assetsData/source | 资产数据来源证据 | 与 R6 提供方台账对账 |
| 访问审计 / 风险处置 / 态势感知 / 资产安全视图 | 安全运营 projection | 形成整改建议，不直接改目录或授权 |
| 脱敏工单模式 | ops issue projection | 只看问题模式，不看敏感原文 |
| 撤回审核 `/res-revoke-examine` 独立审计 | 撤回审批 + 影响摘要 + 订阅通知 | 撤回不能绕过审批、不能静默断订阅 |
| 异议处理 `dsp_handling / data_objection / data_objection_evaluate / data_objection_process / data_objection_authz / data_objection_use` 绕行督查 | 四段时间线交叉核对 | 处置不能早于评估、授权不能晚于用数 |
| 自动检测任务失败督查 `catalog_quality_task_log` | 任务失败分类（执行器/规则/数据源/模板） | 失败不等于通过；都要回到责任环节 |
| 数据直达绕行抽查 `dsp_connect / dc_catalog / dc_datasource` | 直达交付清单 vs `application_record` 时间对账 | dc 系列只读；越过申请视为绕行 |
| API 服务化绕行抽查 `dsp_service / api_access_ip / api_service_fuse / api_service_counter / api_service_errors` | IP 变更审批 + 限流变更审批 + 错误回流字段抽查 | API 边界不能私改 |