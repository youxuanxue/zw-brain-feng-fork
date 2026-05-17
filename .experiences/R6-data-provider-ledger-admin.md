# R6 数据提供方/台账管理员：把资源证据变成可复用资产

## 这一页解决什么事

你要把部门内部台账、资源、schema 和字段证据整理成 zw-brain 可以发现、申请、授权和交付的资产。旧元数据后台里的资源管理、schema 采集、字段注释、物化、血缘、审核能力都要承接，但你不再维护一个孤立的元数据后台，也不处理开箱切换批次。

## 你手上拿到的真实输入

- 目录与资源样例：`辐射安全许可证首次申请信息`、`省编办党政群赋码信息`、`全省规模以上工业经济效益主要指标`。
- 资源类型：库表、文件、文件夹、链接、API/接口等 M0 验收后的 `resource_asset` / `resource_channel_binding` 来源证据。
- 外部执行器证据：数据源、前置库、文件服务器、元数据采集任务、在线建表、库表结构复制、数据建模和物化回执。
- 治理开发侧证据：旧 `metricsmgr-front` 由后端菜单动态加载，`src/pages/*` 含 datamodel / datasource / metric / facet / generate / task 等页面；新平台不复刻这套主导航，只把它们沉淀为数据源 / 模型 / 指标 / 任务证据。
- 目录后台证据：旧 `catalog-front` 的 res-hook、open、atlas、资源挂接和在线目录定义。
- 资源挂接工作队列：旧 `catalog-front` 的 `/res-hook`、`/res-hook-publish`、`/res-maintenance` 在 zw-brain 由 R6 主责承接为"资源挂接 / 资源发布 / 资源维护"三条工作队列；`/res-hook-examine`、`/res-revoke-examine` 走 R7/R8 监督视角。
- 资源开放配置：旧 `catalog-front /open/resource-config`、`/open/resource-config-examine`、`/open/resource-publish` 由 R6 主责，R7 审核。
- 字段安全证据：旧 `datasecurity-front` 的 `dataDesensitization/{algorithm, dynamicDesensitization, staticDesensitization, staticTask, policy}`（脱敏）、`dataEncryption/{key, encryption, passwordApp}`（加密）、`dataIdentification/{rules, groups, tasks, record, sensitive, whitelist}`（敏感识别）、`assetsData/source`（资产数据来源）在新平台沉淀为字段安全证据。
- 字段证据：中文注释、`字段格式`、`是否主键`、`是否允许为空`、`安全级别`、`是否需要加密`。
- schema 证据：`resource_schema_snapshot`、采集时间、采集来源、版本变化。
- 绑定证据：目录项到资源字段的 `resource_schema_mapping`。
- API 服务化证据：旧 `dsp_service` 的 `api_service_info` / `api_service_general` / `api_access_ip` / `api_service_fuse` / `api_service_filter` / `api_service_counter` / `api_service_app` / `api_group` / `api_service_proxy` / `api_service_errors` 等表，承接为 `resource_channel_binding(kind=api)` 的服务化配置证据：IP 白名单、限流熔断、调用计数、错误样本、订阅应用、过滤代理。
- 反向编目工作队列输入：`db_meta_database` / `db_meta_table` / `db_meta_column` 已采集 schema → 反向编目草稿建议。
- 自动检测任务规则证据：旧 `catalog_quality_rule` / `catalog_quality_task` / `catalog_quality_template` / `catalog_quality_task_log` / `catalog_quality_task_result`。
- 旧→新状态映射：资源生命周期旧为 `草稿(0)/待审核(1)/审批通过(2)/审批驳回(3)/已发布(4)/下线(5)` + 独立 `revoke_status`，新平台扩展为 `discovered/draft/pending_review/approved_pending_publish/active/changing/suspended/revoked`，映射规则以 catalog3-metadata3 重构方案 §八 为准；变更 / 物化期间保留上一 active 版本可回放。
- 单租户单省锚定：所有资源 `tenant_id=sd-default`、`region_code=370000000000`；数据源、前置库、文件服务器、API 凭据样例统一为 `山东省 / 省大数据局（11370000MB284651XL）/ 省公安厅 / 省人力资源和社会保障厅` 等真实组织。

## 一条主旅程

1. 进入提供方资产视图，查看本部门已验收或日常新建的资源草案、schema 快照和字段安全证据。
2. 选择 `辐射安全许可证首次申请信息`，核对目录说明、提供方、区域范围和共享条件。
3. 打开关联 `resource_asset`，确认资源类型、通道、状态、schema 快照和最近采集结果；库表、文件、文件夹、链接、API/接口都进入同一资产视图。
4. 查看数据源、前置库、文件服务器、元数据采集、数据建模、在线建表、库表结构复制或物化任务的外部执行器回执，但不在 zw-brain 内直接管理数据库连接。
5. 对治理开发侧对象（旧 `metricsmgr-front` 按后端菜单动态加载的数据源 / 模型 / 指标 / 维度 / 任务），只把它们沉淀为数据源、模型、指标、口径和任务证据，不给普通用户新增导航。
6. 补齐字段中文注释、格式、长度、敏感级别、脱敏规则和来源说明；脱敏 / 加密 / 敏感识别策略由旧 `datasecurity-front` 子模块提供的字段安全证据托底，本步只决定"哪一档落到本资源字段"。
7. 建立或确认 `resource_schema_mapping`，让每个目录项能解释到具体资源字段或交付参数。
8. 对 res-hook、开放目录、关系图谱和在线目录定义，只提供资源证据、字段绑定、开放输出和血缘/关系证据；其中"资源挂接、资源发布、资源维护"三条工作队列在 R6 落点，挂接审核 / 撤回审核归 R7 / R8，最终目录发布由 R7 组织。
9. 提交资源审核；通过后发布资源，并让 R7 组织可见入口和申请边界。
10. 对资源维护、撤回、下架、归档、删除、schema 变更、血缘修正或 active 版本切换，先形成变更草案和影响范围，再走审批和审计。
11. 对物化、结构调整、采集失败、指标生成或任务执行等高副作用动作，只发起外部执行器任务，核心保存审批、版本、schema、回执和审计。
12. 对反向编目，先从已采集的 `db_meta_database` / `db_meta_table` / `db_meta_column` 选源；系统生成目录项草稿（字段中英文名、类型、长度、敏感建议）；只签字"此 schema 证据真实"，不替 R7 决定目录共享条件与字段口径；R7 字段确认完成后再回到本端做 `resource_schema_mapping` 挂接。
13. 对 API 服务化交付，从可发布资源中勾选目录项 → 生成 API 草稿（路径、方法、入参、出参、字段脱敏档位）→ 配置 IP 白名单、限流阈值、熔断条件、过滤规则 → 提交 R7 审核 → 发布后对接应用订阅；上线后只看调用计数与错误样本 projection，不在本端改 API 行为，行为变更走变更草案。
14. 对自动检测任务，维护检测规则与模板（必填率、格式、值域、字段一致性、挂接一致性等），把规则绑定到目录或目录项；任务失败时只看脱敏失败摘要与重跑回执，规则口径变更走审批。

## 工作队列卡片

| 工作队列 | 何时进 | 谁批 | 何时出 | 留在哪 |
| --- | --- | --- | --- | --- |
| 资源挂接 | R6 把目录项绑定到资源字段 | R7 挂接审核 | 通过：`resource_schema_mapping.status=active`；驳回：回到 R6 修复字段绑定再次提交 | mapping evidence + audit |
| 资源发布 | 资源草稿字段、schema、脱敏证据齐全 | R7 资源发布审核 | 通过：`resource_asset.status=active`；驳回：回到 R6 补字段或更换通道 | resource version + audit |
| 资源维护 | schema 版本变化、字段下架、active 版本切换 | 高风险走 R7 审批；非高风险记审计 | 通过：写新 `catalog_entry_version`/schema version；保留上一 active | resource version + audit |
| 反向编目（R6 半边） | 已采集 schema 可以生成目录草稿 | R7 字段口径确认 | 通过：R6 继续做 `resource_schema_mapping`；驳回：回 R6 补 schema 证据 | draft + audit |
| API 服务化交付 | 资源已 active 且需对外 API | R7 审核 API 边界、R2 审核授权策略 | 通过：API 上线、应用可订阅；调整：走 API 变更草案 | channel binding(kind=api) + audit |
| 自动检测任务规则维护 | 检测规则变更、模板更新 | R7 字段口径裁决 | 通过：规则 active；失败重跑只记证据 | quality rule version + audit |

## 关键判断点

| 你看到什么 | 该怎么判断 | 系统证据 |
| --- | --- | --- |
| 资源已入库但字段缺中文注释 | 不能发布为高质量资产 | `resource_schema_snapshot` 缺口 |
| 目录项没有资源字段绑定 | 不能说“可交付” | `resource_schema_mapping` |
| 字段敏感级别高 | 必须配置脱敏或授权策略 | 字段 policy snapshot |
| schema 版本变化 | 保留上一 active 版本，变更走审核 | schema version、`approval_case` |
| 采集或物化失败 | 不直接改发布状态，只保存证据 | metadata gather / materialize evidence projection |
| 资源需要下架、归档或删除 | 先看影响范围和授权中的交付任务 | `resource_asset.status`、`delivery_task` |
| API/接口资源频次变化 | 走授权边界和交付策略变更 | `resource_channel_binding`、access policy snapshot |
| 血缘关系需要修正 | 改 lineage evidence，不直接改业务事实 | lineage projection、audit receipt |
| 在线建表或结构复制失败 | 只保存外部执行器回执，不能手工补库 | executor receipt、schema version |
| 指标或模型口径变化 | 作为字段和质量证据，变更走审核 | metric/facet evidence、schema version |
| 任务生成结果不稳定 | 不写 active 事实，保留执行回执 | task receipt、quality projection |
| API 调用计数集中冲高 | 不直接改 API；评估是否调限流/熔断/IP 白名单或拆分应用订阅 | `api_service_counter` projection、`api_service_fuse` 配置 |
| API 错误样本里出现敏感字段回流 | 立即熔断该路径，回审脱敏档位 | `api_service_errors` projection、字段策略快照 |
| 反向编目草稿字段中英文不一致 | 不直接发布；转 R7 字段口径确认 | draft catalog entry、字段建议 |
| 自动检测任务连续失败 | 看是执行器问题还是规则口径问题，不直接关任务 | task log、规则 version |
| 检测规则变更影响 active 目录 | 走规则版本审核；不让历史检测结论被静默覆盖 | quality rule version + approval |

## 异常分支

- **字段冲突无法自动合并**：标记为 conflicted，发起人工确认，不覆盖 active 绑定。
- **schema 变化过快**：冻结高风险字段，先发布稳定子集。
- **质量诊断不通过**：补齐字段口径或修复资源后再发布。
- **物化结构调整失败**：保留脱敏错误摘要和执行回执，转外部执行器处理。
- **提供方责任不清**：保留组织和区划快照，由 R7/R8 做治理判断。
- **资源下架影响在途申请**：先冻结新增申请，保留已授权交付影响范围，交给 R2/R7 判断替代资源或撤回。
- **API/接口资源不可用**：记录调用边界和错误摘要，转外部执行器修复，不改目录事实。
- **血缘修正与业务口径冲突**：保留两类证据，由 R8 抽查断链，不让血缘投影反向覆盖目录状态。
- **API 上线后被高频应用打爆**：先调限流/熔断/IP 白名单，不直接关接口；持续异常转资源治理。
- **API 服务化字段越权**：暂停发布，回到 R6 字段脱敏证据 + R2 授权边界；不允许接口绕过字段策略。
- **反向编目草稿与现有目录主键冲突**：草稿改为"目录变更建议"，由 R7 决定是合并、撤回还是新建。
- **自动检测规则与现场字段口径冲突**：保留两个版本，由 R7 字段口径裁决；不让检测规则反向改字段定义。

## 成功判据

- 每个可申请目录项都能解释到资源、通道、字段和证据。
- 资源发布前有 schema 快照、字段口径、敏感策略和审核回执。
- 元数据采集、血缘、物化、质量都成为证据，不绕过核心状态机。
- 下次 R1 检索时能直接复用资产，基层不再重复填。

## 旧平台能力在这里怎么落地

| 旧平台能力 | zw-brain 表达 | 用户感知 |
| --- | --- | --- |
| 资源本体 `rc_resource` | `resource_asset` | 部门资源统一成资产 |
| 表/文件/链接资源 `rc_resource_table/file/url` | `resource_channel_binding` | 看资源如何交付 |
| 文件夹资源 / API 接口资源 | `resource_channel_binding(kind=folder/api)` | 长尾资源不长成新后台菜单 |
| 数据源 / 前置库 / 文件服务器 | external executor evidence | 只保存脱敏证据和回执，不暴露连接信息 |
| 元数据对象 `meta_baseinfo` | `resource_schema_snapshot` | 字段结构有版本证据 |
| 目录项挂接 `rc_resource_catalog_item_link` | `resource_schema_mapping` | 目录项对应哪张表哪个字段可解释 |
| 采集、物化、血缘 | evidence / lineage projection / 外部执行器 | 高副作用动作有回执，不直接改事实 |
| 资源维护、下架、归档、删除、active 版本切换 | resource version + approval case + audit receipt | 变更可审批、可回放、可解释影响范围 |
| 数据建模、在线建表、库表结构复制、数据管理 | external executor receipt + schema version | 执行在外部，核心只收版本和回执 |
| datasource / datamodel / metric / facet / generate / task | source/model/metric/task evidence | 治理开发侧沉淀为证据，不变成新导航 |
| res-hook / res-hook-publish / res-maintenance | 资源挂接 / 资源发布 / 资源维护工作队列 | 提供方主责的三条工作队列 |
| res-hook-examine / res-revoke-examine | 转 R7 / R8 监督视角 | 挂接审核 / 撤回审核不在 R6 |
| open/resource-config / open/resource-config-examine / open/resource-publish | 开放资源配置与发布 | R6 主，R7 审核 |
| dataDesensitization / dataEncryption / dataIdentification / assetsData/source | 字段安全证据（脱敏 / 加密 / 敏感识别 / 资产数据来源） | 沉淀为字段安全证据，R2/R7 据此裁决策略 |
| res-hook / open / atlas / 在线目录定义 | mapping/open/relationship evidence | 提供资源挂接、开放输出和关系证据 |
| API 服务化 `api_service_info` / `api_service_general` / `api_access_ip` / `api_service_fuse` / `api_service_filter` / `api_service_counter` / `api_service_app` / `api_group` / `api_service_proxy` / `api_service_errors` | `resource_channel_binding(kind=api)` + 服务化配置证据 | API 上线、IP 白名单、限流熔断、错误样本、订阅应用、调用计数都可解释 |
| 反向编目 `CatalogCompileServiceImpl` | R6 提供 schema 证据 → 系统生草稿 → R7 字段确认 → R6 挂接 | 反向编目不是隐式入库；半边在 R6 |
| 自动检测任务 `catalog_quality_rule` / `catalog_quality_task` / `catalog_quality_template` / `catalog_quality_task_log` / `catalog_quality_task_result` | quality rule version + quality evidence projection | 规则与任务都有版本与回执，失败可重跑 |