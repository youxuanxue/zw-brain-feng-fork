# dsp-objection-handling 异议闭环重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-objection-handling`（目标版本 1.3.9）、`old/代码信息抽取/代码信息抽取-27newbranch/dsp-objection-handling_*`、旧结构数据 `old/12-datastructure/dsp_handling.xml`、旧平台业务说明 `old/integrated-bigdata-platform/README.md`，以及已批准的 zw-brain 数据模型与重构原则。
> 结论：zw-brain 不迁入旧 `dsp-objection-handling` 的页面、菜单、Dubbo、XXL-Job、消息表和旧 URL；只吸收异议填报、受理、分发、核查、复核、评价、督办、证据留存等承重语义，重建为 `ObjectionAggregate` + `AuditAggregate` 上的可审计强状态链路。异议处理由 zw-brain 自带最小闭环，不集成现有工单系统。
> 单一事实源：本文是异议闭环专题的旧表映射、Capability 边界、状态机、证据模型和外化边界的单一事实源；approved 数据模型保留 canonical 表定义，本文补充旧仓库迁移与产品化方案；跨专题 greenfield 口径和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 一、设计原则

### 1.1 Jobs：从“异议管理后台”改成“纠错、协同、追责、闭环”

旧 `dsp-objection-handling` 的表面形态是异议列表、异议受理、数据关联、消息管理、目录查询和开放 API。zw-brain 不继承这些后台模块名，只保留五类用户可感知价值：

1. 使用方能针对目录、资源、授权、使用、内容质量发起异议，并提交依据和期望结果。
2. 平台方能判断异议是否合理，决定受理、驳回、退回补充或分发核查。
3. 提供方能围绕被质疑的目录、资源、服务、数据质量提交核查说明和整改证据。
4. 监管方能看到处理是否超时、责任归属、处理过程、评价结果和证据链。
5. Agent 能把异议、审计、交付、服务调用和目录质量证据转成可读摘要，辅助判断而不是替代业务责任人。

### 1.2 OPC：强状态入核心，通知和调度外部化

- 异议主状态进入 `objection_case`，不能退化成 `catalog_entry`、`resource_asset` 或 `delivery_task` 上的备注字段。
- 异议过程进入 `objection_process`，评价进入 `objection_evaluation`，文本、附件、字段差异、错误数据清单等进入 `objection_evidence`。
- 旧 `data_message_info`、短信、站内信、邮件、XXL-Job 只作为通知 / 调度 adapter 线索，不成为新事实源。
- 旧 Dubbo、Zookeeper、Elasticsearch、MyBatis、Flyway、Kingbase / MySQL 兼容实现都不决定新系统边界。
- 页面、REST、CLI、MCP、A2A 都从统一 `objection.*` Capability contract 投影，不兼容旧 `/dataObjection*`、`/accept/*`、`/restapi/*` URL。

### 1.3 为什么单独形成异议专题

异议链路与目录、资源、申请、授权、交付都有关，但它不是这些领域的附属状态：

1. `docs/approved/zw-brain-data-model.md` 已将 `objection_case`、`objection_evidence`、`objection_process`、`objection_evaluation` 设计为独立表。
2. 旧表 `data_objection.objection_type` 覆盖数据目录、数据资源、数据授权、数据使用，后续又新增内容质量类异议。
3. 旧平台业务说明明确“实际数据修复属于线下动作，平台只承载流程协同”，说明异议的核心不是改数据，而是责任、证据和闭环。
4. 旧代码存在超期预警调度和四方速率查询，说明异议是合规运营和追责指标的重要输入。

### 1.4 旧业务逻辑继承规则

异议发起、受理、分发、核查、复核、评价、督办、状态映射、SLA 与统计口径，默认以旧 `dsp-objection-handling` 代码和 `dsp_handling.xml` 字段语义为实施依据。只有当旧逻辑试图复刻消息中心 / 调度中心、绕过 `ObjectionAggregate` 直接改目录 / 资源 / 源数据、或包含敏感配置时，才进入独立决策。

### 1.5 全新项目口径

本专题不提供旧 `/dataObjection*`、`/accept/*`、`/restapi/*`、Dubbo 服务、菜单或旧页面兼容层。异议状态权威只属于 `ObjectionAggregate`；P6 只能消费异议指标 projection，不得反向推进异议主状态。

## 二、证据清单

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture.md` | 目录、申请、交付、异议是强状态领域；异议不是备注字段，而是独立链路。 |
| `docs/approved/zw-brain-data-model.md` | `ObjectionAggregate` 是核心聚合之一；异议状态推进需要与审计事件、回执在事务边界内一致。 |
| `docs/approved/zw-brain-user-roles-and-journeys-v1.md` | 处理对象不是抽象管理员，而是要数的人、管数的人、填数的人、审数的人、查责的人。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | `dsp-objection-handling` 被列为 P0，优先补齐 J4 异议强状态闭环。 |
| `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` | 目录 / 资源质量问题应进入证据与强状态，不通过门户或目录后台补丁解决。 |
| `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md` | 授权、交付、订阅争议应能关联申请和交付回执，不能散落在交换系统里。 |

### 2.2 旧 API 证据

`dsp-objection-handling_对外提供API清单.md` 显示旧接口可分为七类：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/dataObjection1/*`、`/dataObjectionList/*` | 异议首页、列表、新增、编辑、提交 | `objection.case.create` / `objection.case.submit`，列表是读模型。 |
| `/accept/*` | 待受理、已受理、详情、受理异议 | `objection.case.accept`，受理结果写过程和审计。 |
| `/apply/*` | 查询申请列表和详情 | 只读关联 `application_record`，不是异议系统自有申请事实源。 |
| `/connect/*` | 关联申请、目录、异议、组织 | 转为 `target_type` / `target_id` / `related_application_id` 和 legacy 映射。 |
| `/message/*` | 消息列表、处理消息 | 通知 adapter，不进入 `ObjectionAggregate`。 |
| `/catalogstable/*`、`/queryCatalogGroupList` | 查询目录和分组 | 只读关联 `catalog_entry` / P7 projection。 |
| `/restapi/queryObjectFourRate`、`/restapi/getDataObjectionProcessList`、`/restapi/dataContent/*` | 四方速率、流程、内容质量异议开放接口 | P6 指标 projection、`objection_process` 读模型、`quality` 类异议能力。 |

### 2.3 旧表证据

`old/12-datastructure/dsp_handling.xml` 与数据库结构文档显示旧异议库至少包含以下承重语义：

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `data_objection` | 异议主单、提出方、提供方、类型、状态、依据、附件、区划 | `objection_case` 主实体。 |
| `data_objection_catalog` | 目录名称、目录数据项纠错 | `objection_evidence` 的 `field_diff` / `catalog` 证据。 |
| `data_objection_resource` | 服务时间、并发、授权方式、入参、返回值等资源 / 服务能力异议 | `objection_evidence` 的 `api_contract` / `field_diff` 证据，并关联 `resource_asset` / dataservice capability。 |
| `data_objection_authz` | 申请、审批时间长、驳回原因不明确 | 关联 `application_record` / `approval_case`，作为授权争议证据。 |
| `data_objection_use` | 数据使用场景、业务名称、描述、附件、建议 | `usage` 类异议证据，关联 `delivery_task` 或服务调用回执。 |
| `data_objection_content` | 内容质量错误数据清单、使用系统、使用部门 | `quality` 类异议证据；错误清单保存为结构化 JSON 或对象存储引用。 |
| `data_objection_process` | 环节、核查组织、核查人、意见、核查状态 | `objection_process`。 |
| `data_objection_evaluate` | 评价内容、得分、是否解决、时效 / 结果评分 | `objection_evaluation`。 |
| `data_message_info` | reject / finish / accept / inspect 消息 | 通知 adapter 事件，不作为业务事实源。 |

### 2.4 旧流程证据

旧平台说明中的流程是：

1. 异议填报：使用方操作员或管理员发起。
2. 异议受理：平台管理员审核异议合理性。
3. 异议分发：判断责任归属是平台方还是数据提供方。
4. 异议核查：责任方调查并提交核查回复。
5. 异议审查：平台管理员复核处理是否规范；审查通过结束，驳回继续整改。
6. 异议督办：超时通过站内信和短信提醒。

关键约束：实际数据修复在线下完成，平台承载流程协同、证据、责任归属和追责，不直接修改目录、资源、服务或源数据。

### 2.5 旧外部依赖证据

旧项目依赖 Spring Boot、Spring Cloud、Dubbo、Zookeeper、XXL-Job、Elasticsearch、MySQL、Kingbase、Prometheus。对 zw-brain 的含义是：

| 旧依赖 | 新系统处理 |
| --- | --- |
| Dubbo / Zookeeper | 不迁；统一 Capability contract 暴露。 |
| XXL-Job | 不迁；超期预警作为调度 adapter 或平台计划任务。 |
| Elasticsearch | 不迁；异议列表和证据检索可由统一搜索 / PostgreSQL FTS / 外部检索承担。 |
| Prometheus | 不迁；运行指标进入观测底座。 |
| MySQL / Kingbase 脚本 | 只作为字段和状态映射证据。 |

## 三、目标领域模型

### 3.1 聚合边界

`ObjectionAggregate` 包含：

- `objection_case`：主单、目标、提出方、提供方、状态、依据、期望结果、解决摘要。
- `objection_evidence`：目录纠错、资源服务能力、授权争议、使用问题、内容质量、附件、日志、回执、字段差异。
- `objection_process`：受理、驳回、分发、平台核查、提供方核查、复核、退回、结案。
- `objection_evaluation`：是否解决、总评分、时效评分、结果评分和评价文本。

`ObjectionAggregate` 不包含：

- 通知消息读取状态。
- 调度任务定义。
- 目录、资源、申请、交付的权威事实。
- 源数据修复任务。

### 3.2 目标类型

| 目标类型 | 关联对象 | 来源旧类型 |
| --- | --- | --- |
| `catalog` | `catalog_entry` / `catalog_item` | `data_objection_catalog`，旧 `objection_type=1`。 |
| `resource` | `resource_asset` / `resource_channel_binding` | `data_objection_resource`，旧 `objection_type=2`。 |
| `authorization` | `application_record` / `approval_case` / 授权快照 | `data_objection_authz`，旧 `objection_type=3`。 |
| `usage` | `delivery_task` / `delivery_receipt` / 服务调用回执 | `data_objection_use`，旧 `objection_type=4`。 |
| `quality` | `resource_asset` / 数据内容证据 / 质量投影 | `data_objection_content`，后续内容质量类异议。 |

### 3.3 状态机

| 新状态 | 旧状态 / 旧动作 | 说明 |
| --- | --- | --- |
| `draft` | `status=1` 草稿 | 发起方保存但未提交。 |
| `submitted` | `status=2` 待受理 | 已提交，等待平台受理。 |
| `accepted` | `inspect_status=1` 已受理通过 | 平台确认异议合理。 |
| `platform_investigating` | `status=3` 待平台核查 | 责任归属平台或需平台先核查。 |
| `provider_investigating` | `status=4` 待数据提供方核查 / `inspect_status=3` | 转交提供方核查。 |
| `rejected` | `status=5` 已驳回 / `inspect_status=0` | 平台驳回或复核不通过。 |
| `resolved` | `status=6` 已核查 / `inspect_status=2` | 已完成核查并给出解决摘要。 |
| `closed` | 评价后关闭或无需评价关闭 | 业务闭环完成。 |

状态推进规则：

1. `draft` 只能由创建方编辑或提交。
2. `submitted` 只能受理、驳回或退回补充。
3. `accepted` 必须进入平台核查或提供方核查，不能直接关闭。
4. `provider_investigating` 的回复必须形成 `objection_process` 和 `objection_evidence`。
5. `resolved` 后允许评价；评价后进入 `closed`。
6. 每次状态推进必须同时写 `audit_event` 和 `capability_call`。

## 四、Capability 设计

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `objection.case.create` | 写 | `write-trace` | 创建草稿或直接提交异议。 |
| `objection.case.submit` | 写 | `write-trace` | 将草稿提交为待受理。 |
| `objection.case.accept` | 写 | `approval-trace` | 平台受理异议。 |
| `objection.case.reject` | 写 | `approval-trace` | 平台驳回异议并记录理由。 |
| `objection.case.assign` | 写 | `approval-trace` | 分发给平台方或数据提供方核查。 |
| `objection.case.reply` | 写 | `write-trace` | 责任方提交核查回复、整改说明和证据。 |
| `objection.case.review` | 写 | `approval-trace` | 平台复核，决定解决、退回或关闭。 |
| `objection.case.evaluate` | 写 | `write-trace` | 发起方评价处理结果。 |
| `objection.case.close` | 写 | `approval-trace` | 关闭异议。 |
| `objection.case.escalate` | 写 | `write-trace` | 生成督办事件，通知由 adapter 处理。 |
| `objection.case.query` | 读 | `read-trace` | 查询异议列表和详情。 |
| `objection.process.query` | 读 | `read-trace` | 查询处理过程。 |
| `objection.metric.query` | 读 | `read-trace` | 查询四方速率、超期率、解决率、满意度等 P6 指标。 |

消费面：

- WebUI：P5 提供方管理、P6 合规运营、P7 共享专区详情中的异议入口。
- REST：外部系统提交内容质量异议、查询过程和指标。
- CLI：运维 / 迁移回放查询、督办重放。
- MCP：Agent 查询异议证据、生成追责摘要。
- A2A：外部 Agent / Skill 发起质量异议或补充证据。

## 五、旧表到新表映射

| 旧字段 / 旧表 | 新落位 | 备注 |
| --- | --- | --- |
| `data_objection.id` | `legacy_object_mapping.legacy_id` + `objection_case.id` | 新主键不沿用旧 varchar ID。 |
| `objection_title` | `objection_case.title` | 标题。 |
| `objection_dept_id/name` | `complainant_org_id` + `complainant_org_snapshot` | 保存提出方快照。 |
| `contact`、`phone`、`creator_*` | `complainant_org_snapshot` / actor snapshot | 联系方式按敏感信息规则处理，不直接散落展示。 |
| `objection_type` | `objection_kind` / `target_type` | `1/2/3/4` 映射到 `catalog/resource/authorization/usage`，内容质量映射到 `quality`。 |
| `objection_data_id/name` | `target_id` + target snapshot evidence | 目标对象需通过 legacy 映射解析。 |
| `data_org_id/name` | `provider_org_id` + `provider_org_snapshot` | 保存提供方快照。 |
| `status` | `objection_case.status` | 按本文状态机映射。 |
| `objection_description` | `objection_evidence.content_json` 或 `basis_text` | 描述和依据拆分。 |
| `objection_basis` | `objection_case.basis_text` | 异议依据。 |
| `file_path` | `objection_evidence.blob_id` / legacy file ref | 不迁内部文件路径为公开字段。 |
| `data_objection_*` 扩展表 | `objection_evidence.content_json` | 按 evidence_type 保存结构化差异。 |
| `data_objection_process.*` | `objection_process.*` | 处理人、组织、意见保存快照。 |
| `data_objection_evaluate.*` | `objection_evaluation.*` | `solved`、`score` 和三类评分映射为布尔与整数评分。 |
| `data_message_info.*` | `notification adapter` + `audit_event` | 不进入核心模型。 |

## 六、读模型与指标

异议闭环需要以下 projection，但 projection 不反向驱动主状态：

| 读模型 / 指标 | 来源 | 用途 |
| --- | --- | --- |
| 待受理异议列表 | `objection_case.status=submitted` | 平台工作台。 |
| 提供方待核查列表 | `provider_investigating` + provider org | P5 提供方管理。 |
| 异议过程时间线 | `objection_process` + `audit_event` | 详情页、MCP 摘要、外部查询。 |
| 四方速率 | `objection_process` 时间差 | 替代旧 `/restapi/queryObjectFourRate`。 |
| 超期预警 | 状态停留时间 + SLA 规则 | P6 合规运营和通知 adapter。 |
| 解决率 / 满意度 | `objection_evaluation.solved_flag` + score | 质量和合规看板。 |
| 高频异议对象 | `target_type` / `target_id` 聚合 | 反哺目录质量、资源可靠性和服务契约治理。 |

## 七、外化边界

| 旧能力 | 新边界 |
| --- | --- |
| 站内信、短信、邮件 | `notification.*` adapter；核心只产生督办事件和审计。 |
| XXL-Job 每日预警 | 外部调度器或平台计划任务；核心提供 `objection.case.escalate`。 |
| Elasticsearch 搜索 | 统一搜索 / PostgreSQL FTS / 外部检索，不作为异议领域依赖。 |
| Dubbo 服务 | Capability contract。 |
| 旧目录 / 申请 / 资源查询 | 只读调用 canonical 聚合或 projection，不在异议域复制事实。 |
| 线下数据整改 | 外部整改证据；异议域只记录回复、摘要和附件。 |
| 旧开放 URL | 不兼容；通过 REST exposure 生成新 API。 |

## 八、迁移与验证策略

### 8.1 迁移步骤

1. 建立 `legacy_adapter_source`：登记 `dsp-objection-handling`、版本、数据库类型、抽取时间和字段口径。
2. 导入 `data_objection` 为 `objection_case` 候选，保留旧 ID 映射。
3. 按 `objection_type` 和扩展表生成 `objection_evidence`。
4. 导入 `data_objection_process` 为过程时间线。
5. 导入 `data_objection_evaluate` 为评价记录。
6. 将 `data_message_info` 只作为通知历史 evidence 或 audit 迁移，不进入核心表。
7. 对无法解析 `target_id` 的旧对象建立 `legacy_unresolved_reference` 清单，等待人工确认或后续 adapter 补齐。

### 8.2 验证样本

必须使用旧平台真实脱敏数据验证，禁止 Mock 业务数据。最小样本应覆盖：

1. 目录名称 / 数据项纠错。
2. 资源服务时间、并发、入参、返回值争议。
3. 授权审批时间长或驳回原因不明确。
4. 数据使用场景异议。
5. 内容质量错误清单。
6. 平台驳回。
7. 提供方核查后解决。
8. 超期督办。
9. 评价为已解决和未解决两类结果。

## 九、不做清单

1. 不复刻旧 `dsp-objection-handling` 菜单、Controller、Dubbo 服务和数据库 schema。
2. 不把异议压扁成目录 / 资源 / 申请上的备注字段。
3. 不在异议域直接修改目录、资源、服务或源数据。
4. 不迁入内部 IP、连接串、短信账号、邮件账号、Zookeeper、XXL-Job 地址。
5. 不把 `data_message_info` 变成新的消息中心。
6. 不为旧 `/restapi/*` 提供兼容层。
7. 不把统计指标作为可写事实源。

## 十、专题差异决策

全局 greenfield 口径、adapter 边界和旧平台逻辑继承原则以总览方案第八节为准。本专题只保留异议闭环的差异决策：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| O1 | 异议上报国家平台的范围 | 只上报涉及国家 / 上级资源、目录、申请、订阅的异议；本地资源异议默认不上报。 | 上报必须交由 `adapter.national.objection.sync`，不得在异议域内实现国家协议。 |
| O2 | 内容质量错误清单的敏感数据处理 | 默认视为可能含敏感数据，只保存脱敏摘要或受控对象存储引用。 | `objection_evidence` 可保存 hash、行数、脱敏样例、对象存储引用；明文样例不进主库。 |
| O3 | 多轮评价是否突破现有唯一评价模型 | 首版不支持多轮评价，保持一个异议一条最终评价。 | 补充说明写入 `objection_process`；如未来支持多轮评价，需先修订数据模型。 |

## 十一、证据来源

- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-objection-handling_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-objection-handling_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-objection-handling_外部SDK和接口文档.md`
- `old/12-datastructure/dsp_handling.xml`
- `old/old_codes/dsp-objection-handling/doc/handling-kingbase.sql`
- `old/old_codes/dsp-objection-handling/doc/共享条例sql/xxl-job-init-handling.sql`
- `old/old_codes/dsp-objection-handling/src/main/resources/application.properties`
- `old/integrated-bigdata-platform/README.md`
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/zw-brain-data-model.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
