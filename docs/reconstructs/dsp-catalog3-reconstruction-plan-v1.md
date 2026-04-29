# dsp-catalog3 相关模块重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-catalog3`（3.12.15）、外部调用分析 `old/old_codes_analyse/dsp-catalog3-apis.md`、旧结构数据 `old/12-datastructure/dsp_catalog.xml` / `dsp_service.xml`，以及工单导出 `old/工单导出-列缩减.xlsx` 的目录域候选问题。
> 结论：zw-brain 不迁移旧目录门户、旧 URL 或旧表结构；它吸收 `dsp-catalog3` 中真正承重的目录模型、目录条目、信息项、资源关联、审批授权、共享开放与统计语义，重建为围绕 J1 发现、J2 申请审批、J4 供给侧治理、S1 合规运营的统一 Capability 与 canonical model。

## 一、设计原则

### 1.1 Jobs：目录系统不是菜单，是“找得到、看得懂、能申请、可追责”

旧 `dsp-catalog3` 的表面形态包括目录注册、目录审核、目录分组、开放目录、资源推送、质量检测、编制任务、统计页面与门户展示。zw-brain 不继承这些模块名，也不把旧门户信息架构搬进新产品。它只保留四类用户可感知价值：

1. 数据目录能被用户和 Agent 用同一语义发现、理解和追踪。
2. 目录信息项、资源、共享开放条件能支撑申请、审批和交付。
3. 编目、发布、变更、撤销、开放、授权都有显式状态机和审计证据。
4. 质量检测、开放推送、门户展示、项目化导入等长尾能力通过注册 Capability 或 adapter 承接，不成为主导航。

### 1.2 OPC：catalog3 迁移只有一个事实源

- 本文是 `dsp-catalog3` 专属迁移规则、字段映射、能力边界和工单归因的单一事实源。
- `docs/approved/zw-brain-data-model-v4-gpt55.md` 只保留 canonical model 通用结构，并引用本文；不回灌旧表、旧接口、工单统计等细节。
- 旧库、旧代码、旧 API 与工单只作为只读证据，不作为新系统写入口。
- 新契约以 Capability slug、状态机和审计等级为准，不以旧 URL 兼容为目标。
- 任何外部 ANP / adapter 只能经 Capability / policy / audit 写入 canonical 状态，不能直接改目录、资源、申请或审批事实。

### 1.3 与 v4 基线的对应关系

| v4 约束 | catalog3 落地方式 |
| --- | --- |
| 少数高频旅程优先 | 先覆盖目录发现、编目发布、审批、资源关联、申请入口和统计读面 |
| 五消费面共用 Capability | WebUI / API / CLI / MCP / A2A 读取同一 `catalog.*`、`resource.*`、`ops.catalog.*` contract |
| canonical model 优先 | 旧 `data_catalog*` / `data_resource*` / `data_apply*` 只进入 adapter 映射，不扩散到 domain 命名 |
| 强状态领域显式化 | 目录生命周期、资源发布、申请授权、审批轨迹、开放推送均保留状态与回执 |
| 长尾外部化 | 质量规则、导入脚本、门户项目化展示、开放平台推送执行、环境诊断走外部 Capability |
| 审计同步落库 | 目录/资源/申请/审批/授权写动作必须写 `capability_call` 与 `audit_event` |

## 二、旧 dsp-catalog3 能力理解

### 2.1 模块边界

旧工程版本在 `old/old_codes/dsp-catalog3/pom.xml` 中标记为 `3.12.15`，主模块包括 `dsp-catalog-common`、`dsp-catalog-console`、`dsp-catalog-service`、`dsp-catalog-job`。另有 `dsp-catalog-supply`，更像供需侧或项目化扩展，不应进入新平台核心主干。

| 旧模块 | 旧职责 | zw-brain 去向 |
| --- | --- | --- |
| `dsp-catalog-console` | 目录注册、审核、分组、开放目录、资源推送、统计 API、门户控制器 | WebUI / API 投影层；写动作统一回到 command + Capability |
| `dsp-catalog-service` | 目录、资源、申请、审批、开放推送、MQ 同步、权限查询等业务实现 | 领域语义拆入 `CatalogResourceAggregate`、`ApplicationApprovalAggregate`、`AuditAggregate` 与 adapter |
| `dsp-catalog-job` | 质量检测、目录同步、开放推送、统计任务 | 可重算投影或外部 worker；不进入普通用户主导航 |
| `dsp-catalog-common` | 公共对象、常量、工具 | 只吸收稳定语义，不迁移工具形态 |
| `dsp-catalog-supply` | 供需侧统计、汇聚、项目化页面 | 外部 Capability 或后续专题能力；默认不进核心事实源 |

### 2.2 关键旧入口与流程

旧代码中的承重入口集中在：

| 旧入口 / 类 | 证据 | 承重语义 | 新系统处理 |
| --- | --- | --- | --- |
| `OpenApiController` | `@RequestMapping("/restapi")` | 对外目录统计、目录查询、申请相关查询 | `ops.catalog.*` 与 `catalog.search/query` 读能力 |
| `CatalogRegisterController` | `/dsp/catalog/register`；`submitCatalogApprove`、`catalogVersionCompare`、`importCatalogColumnExcel`、`catalogVersionBack` | 目录注册、提交审核、版本对比、信息项导入、回滚 | `catalog.entry.*` 写能力 + `catalog_entry_version` |
| `CatalogApproveController` | `/dsp/catalog/catalogApprove`；`updateApproveCatalogStatus` | 目录审核通过/驳回 | `approval_case` + `approval_decision` |
| `CatalogGroupPermissionController` | `/dsp/catalog/grouppermission` | 分组授权与可见范围 | `tenant_capability_policy` + `catalog_visibility_policy` 投影 |
| `ResourcePushController` | `/dsp/resource/resourcepush` | 目录与资源、服务的关联查询与推送 | `resource_asset` / `resource_channel_binding` 关联与外部 adapter |
| `PushOpenCatalogServiceImpl` | `inspur_catalog_resource_open_catalog`、`DATA_PUSH_CATALOG_OPEN` | 开放目录推送外部平台 | 外部开放平台 adapter；结果只写回执/投影 |
| `CatalogServiceImpl` | `approveCatalogPass`、`approveCatalogRefuse`、`submitCatalogApprove`、`sendDataToDspMq` | 状态推进、审计、MQ 同步 | command 状态机 + audit + outbox |

### 2.3 旧实体与表映射证据

关键实体在旧代码中有明确 `@TableName` 映射：

| 旧实体 | 旧表 | 承重语义 |
| --- | --- | --- |
| `Catalog` | `data_catalog` | 目录主实体 |
| `CatalogColumn` | `data_catalog_column` | 目录信息项 |
| `CatalogGroup` | `data_catalog_group` | 目录分类 / 分组 |
| `CatalogGroupPermission` | `data_group_permission` | 分组授权 |
| `CatalogApproveInfo` / `WebfinalAuditLog` | `data_catalog_approve` | 目录审批与审核日志 |
| `Resource` | `data_resource` | 目录下可申请/交付资源 |
| `ResourceApply` | `data_apply` | 资源申请 |

这些映射证明 `dsp-catalog3` 的核心不是门户页面，而是目录、信息项、资源、审批、权限和申请之间的强关系链。

### 2.4 外部调用 Pareto 结论

`old/old_codes_analyse/dsp-catalog3-apis.md` 显示，三项目日志中 `dsp-catalog3` 去重接口条目为 163，调用总量为 186,679。头部接口说明迁移优先级：

| 优先级 | 旧接口 / 能力 | 调用量特征 | 新系统处理 |
| --- | --- | --- | --- |
| P0 | `/restapi/getDeptTotalCataNumAndResourceNum` | 21,198 次；部门目录与资源统计 | `ops.catalog.summary.query`，读统计投影，不作为业务事实源 |
| P0 | `/dsp/catalog/register/getCatalog` | 13,432 次；目录列表/注册管理主查询 | `catalog.entry.query` / P5 提供方管理 |
| P0 | `/api/model/catalog-template-info` | 13,051 次；目录模板信息 | `catalog.model.query` |
| P1 | `/restapi/dict/getDictInfo` | 9,192 次；字典辅助 | 外部字典/IAM adapter + 本地快照，不重建字典中心 |
| P1 | `/dsp/catalog/group/queryCatalogGroupList` | 6,668 次；目录分组 | `catalog.group.query`，仅作为目录组织/可见性结构 |
| P1 | `/dsp/resource/resourcepush/getLinkCatalogResource` | 6,648 次；目录资源关联 | `resource.catalog_binding.query` |
| P1 | `/dsp/resource/resourcepush/getResourceData` | 6,380 次；资源数据查询 | `resource.asset.query` |
| P1 | `/restapi/getCatalogStatisticWithUser` | 6,017 次；用户维度统计 | P6 / Dashboard 运营投影 |
| P1 | `/dsp/catalog/getOpenCataNum`、`getSharedCataNum`、`getStatisticCataNum` | 约 6,017 次；开放/共享/统计数量 | `catalog.visibility_metric_projection` |
| P1 | `/dsp/catalog/catalogApprove/getApproverOptLog` | 4,956 次；审批日志 | `approval_decision` + `audit_event` 查询 |

这意味着迁移顺序不是“复刻 163 个 URL”，而是先重建目录模板、目录查询、目录资源关联、统计读面与审批日志这些真实高频能力。

## 三、真实数据结构理解

### 3.1 `dsp_catalog.xml` 证明的核心对象

`old/12-datastructure/dsp_catalog.xml` 含 161 张表，其中与目录、资源、申请、审批、开放共享直接相关的表族如下：

| 表族 | 关键旧表 | zw-brain 去向 |
| --- | --- | --- |
| 目录模型 | `model_property_group`、`model_properties`、`model_catalog_step`、`model_dimension`、`model_catalog_template`、`model_catalog_properties`、`model_catalog_column_properties` | `catalog_model`、`catalog_model_step`、`catalog_model_field` |
| 目录主数据 | `data_catalog_group`、`data_catalog_group_lk`、`data_catalog`、`data_catalog_column`、`data_catalog_version`、`data_catalog_column_version` | `catalog_entry`、`catalog_item`、`catalog_entry_version` |
| 目录审批 | `data_catalog_approve`、`standard_catalog_approve`、`data_refund_theme_approve` | `approval_case`、`approval_step`、`approval_decision` |
| 资源主数据 | `data_resource`、`data_resource_api`、`data_resource_file`、`data_resource_table`、`data_resource_table_column` | `resource_asset`、`resource_channel_binding` |
| 申请授权 | `data_apply`、`data_apply_item`、`data_apply_course`、`data_apply_authrization`、`data_apply_authrization_approve`、`data_apply_renewal` | `application_record`、`application_attachment`、`approval_case`、`delivery_task.access_grant_snapshot` |
| 共享开放 | `open_catalog_group_type`、`open_catalog_group`、`open_catalog_group_link`、`push_open_catalog`、`open_catalog_standard`、`open_catalog_column_standard` | P7 专题/共享专区投影 + 外部开放平台 adapter |
| 标签与专题 | `base_taginfo`、`base_taginfo_group`、`data_catalog_tag`、`basesubject_info` | `subject_tags` / 搜索投影；不重建标签中心 |
| 质量检测 | `catalog_quality_template`、`catalog_quality_rule`、`catalog_quality_task*` | 外部质量规则 Capability；结果作为 P6 质量投影 |
| 统计报表 | `data_catalog_*_statistics`、`data_resource_*_statistics`、`data_apply_statistics` | 可重算统计投影；不得反向驱动业务状态 |
| 互动门户 | `news_*`、`data_score`、`data_recommend*`、`data_interact_user_collection`、`data_comment_info` | 默认不进核心；确有价值时走 P7 投影或外部 Capability |

### 3.2 `dsp_service.xml` 对 catalog3 的约束

`dsp_service.xml` 中的服务分类、服务基本信息和授权策略说明 catalog 与 service 的边界：

| 旧表 | 与 catalog3 的关系 | 新系统处理 |
| --- | --- | --- |
| `api_group`、`api_group_lk` | 服务分类与服务关联，类似目录组织结构 | 作为 `catalog_entry` / `catalog_item` 或搜索投影输入 |
| `api_service_info`、`api_service_catalog` | API 服务本体和详情 | 服务本体以 `resource_asset(resource_kind='api')` 表达；细节以 dataservice 方案为准 |
| `api_service_app` | 服务授权与应用密钥 | 授权快照进入申请/交付；密钥只保存引用，禁止明文 |
| `api_service_proxy`、`api_service_data`、`api_service_general` | 代理、数据服务、通用服务通道 | `resource_channel_binding`；网关细节以 `dsp-dataservice` 方案为准 |
| `api_service_times`、`api_service_statistic` | 调用统计 | P6 / Dashboard 投影；不作为目录事实源 |

因此，catalog3 方案只定义“目录如何组织资源、如何支撑发现与申请”；API 服务运行时、网关策略和调用日志的细节继续以 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` 为主。

### 3.3 字段级迁移规则

| legacy 字段 / 语义 | canonical 落点 | 规则 |
| --- | --- | --- |
| `cata_id` | `legacy_object_mapping` + `catalog_entry.id` | 新主键重新生成 UUID；旧 ID 只作映射证据 |
| `cata_code` | `catalog_entry.catalog_code` | 作为租户内稳定编码，需检测重复与冲突 |
| `cata_title` | `catalog_entry.title` | 保留业务名称，面向客户文案可重写 |
| `cata_group_id` / `cata_group_name` | `catalog_entry.subject_tags` / 分类投影 | 不把旧分组等同于新权限边界 |
| `org_code` / `org_name` | `owner_org_id` / `owner_org_snapshot` | IAM 仍是权威，本地保存快照用于回放 |
| `region_code` | `catalog_entry.region_code` / 指标区划字段 | 用于发现、统计和审批路由，不单独成为权限权威 |
| `data_catalog_column.*` | `catalog_item` | 信息项作为目录内结构化字段治理，不落到资源通道 schema |
| `data_resource.res_id` | `legacy_object_mapping` + `resource_asset.id` | 资源主键重建；旧 ID 只作证据 |
| `data_resource.res_type` | `resource_asset.resource_kind` | 映射为 `table/api/file/stream/dataset` 等受控枚举 |
| `data_resource_api.url` / `inType` / `canProxy` | `resource_channel_binding.endpoint_ref` / `gateway_policy_json` | 只保存通道引用与策略，不保存明文密钥 |
| `data_catalog_approve.business_type` | `approval_case.business_type` | 映射目录发布、变更、撤销、分组调整等强责任动作 |
| `approve_opinion` / `approver_*` | `approval_decision` | 审批意见追加保存，不覆盖历史 |
| `data_apply.*` | `application_record` | 申请目的、申请方、资源范围、状态进入统一申请状态机 |
| `data_apply_item.*` | `application_record.requested_items` | 记录申请的信息项范围 |
| `data_apply_authrization.*` | `delivery_task.access_grant_snapshot` | 授权结果是交付快照，不是独立权限权威 |
| `open_catalog*` / `push_open_catalog` | P7 投影 + 外部开放平台 adapter | 开放展示和推送结果不反向驱动目录事实 |
| `catalog_quality_*` | 质量检测 Capability + P6 投影 | 规则可外化，发现的问题回到异议/整改或审计证据 |
| 统计临时表 / 报表表 | P6 / Dashboard 投影 | 可重算；禁止用统计结果反推生命周期状态 |

## 四、zw-brain 数据模型设计

本节是 `dsp-catalog3` 相关数据模型与迁移映射的单一事实源。

### 4.1 目录模型：`CatalogModel`

旧目录模板、步骤、属性和维度进入 `catalog_model` 表族：

- `catalog_model` 承接模板与适用范围，如政务目录、开放目录、共享专区、自定义目录。
- `catalog_model_step` 承接目录编制步骤，但不复刻旧页面流程。
- `catalog_model_field` 承接目录属性和信息项属性，包括字典、UI 组件、必填、展示、导入导出、校验规则。

约束：目录模型是供给侧治理工具，不是前台“配置中心”。普通用户只在 P2/P3/P5 感知到清晰字段和缺项提示。

### 4.2 目录主实体：`CatalogEntry` 与 `CatalogItem`

`data_catalog` 与 `data_catalog_column` 进入 `catalog_entry` / `catalog_item`：

- `catalog_entry` 表达目录名称、编码、提供方、区划、共享条件、开放条件、生命周期状态和版本号。
- `catalog_item` 表达目录信息项，包括名称、编码、数据类型、长度、敏感级别、共享条件和来源字段引用。
- `catalog_entry_version` 保存完整快照，支撑版本对比、回放、回滚和审计。

状态建议：

| legacy 语义 | `catalog_entry.lifecycle_status` | `approval_case.current_status` | 说明 |
| --- | --- | --- | --- |
| 草稿 / 驳回后修改 | `draft` |  | 可编辑但不可发布 |
| 提交审核 / 变更待审 | `pending_review` | `pending_decision` | 线上版本不被未审变更覆盖 |
| 审核通过并发布 | `published` | `approved` | 可发现、可申请、可进入共享/开放投影 |
| 撤销 / 下线审核中 | `revoking` | `pending_decision` | 保留历史版本和引用关系 |
| 已撤销 | `revoked` | `approved` | 受监管场景不物理删除 |
| 归档 | `archived` |  | 不再作为新申请入口 |

### 4.3 资源关联：`ResourceAsset` 与 `ResourceChannelBinding`

旧 `data_resource*` 是 catalog3 与 dataservice 的交界面。新系统中：

- 资源本体进入 `resource_asset`，通过 `catalog_id` 回指目录。
- 库表、文件、API、订阅、国家直达等交付方式进入 `resource_channel_binding`。
- API 服务的网关、鉴权、熔断、统计等细节以 `dsp-dataservice` 重构方案为准；catalog3 只负责该资源是否属于某目录、能否被发现、申请和交付。

### 4.4 申请、审批与授权

旧 `data_apply*` 和 `data_catalog_approve` / `data_resource_approve` 进入统一申请审批模型：

- `application_record`：保存申请方、申请目的、申请目录/资源、申请信息项范围、使用期限与状态。
- `approval_case`：统一承载目录发布、资源发布、申请审批、授权续期、撤销等强责任动作。
- `approval_step` / `approval_decision`：保存审批节点、审批人快照、意见和证据。
- `delivery_task.access_grant_snapshot`：保存审批通过后的授权结果和策略快照。

不可外化：审批状态机、授权裁决、租户策略、审计事件不能交给外部执行器维护。

### 4.5 共享专区、开放目录与统计投影

- 共享专区 / 专题包对应 P7，消费 `catalog_entry`、`resource_asset` 与专题投影，不新增独立事实源。
- 开放目录推送对应外部开放平台 adapter；推送状态、失败原因、回执写入 outbox / audit / 投影，不反向覆盖目录生命周期。
- 目录、资源、开放、共享、申请统计进入 `catalog_visibility_metric_projection` 或 P6 / Dashboard 投影，可重算、可解释来源，不反向改业务状态。

### 4.6 legacy 映射与冲突处理

每个旧对象迁移必须写入 `legacy_object_mapping`：

| 字段 | 规则 |
| --- | --- |
| `legacy_system` | 固定为 `dsp-catalog3` 或具体 adapter source |
| `legacy_table` | 旧表名，如 `data_catalog` |
| `legacy_id` | 旧主键，如 `cata_id` |
| `canonical_type` | `catalog_entry/resource_asset/application_record/approval_case` 等 |
| `canonical_id` | 新 UUID |
| `mapping_status` | `mapped/conflicted/ignored` |
| `evidence_json` | 旧字段摘要、来源文件、抽取时间、冲突说明 |

冲突规则：

- 同一 `tenant_id + catalog_code` 多个旧目录命中时，不自动合并，进入 `conflicted`。
- 缺少提供方组织或区划时，可以进入 draft，但不得发布。
- 信息项编码缺失时生成临时导入键，但必须在发布前补齐稳定编码。
- 已发布目录的变更必须生成新版本，不允许覆盖当前线上快照。

## 五、Capability 迁移矩阵

旧接口只作为证据，新系统按 Capability 命名。

| 新 Capability | 目标聚合 / 投影 | 旧能力来源 | 审计等级 |
| --- | --- | --- | --- |
| `catalog.model.query` | `catalog_model*` | `/api/model/catalog-template-info`、`catalog-detail-info` | `read-trace` |
| `catalog.model.import` | `catalog_model*` | 目录模板导入、信息项模板导入 | `write-critical` |
| `catalog.entry.query` | `catalog_entry` / 搜索投影 | `/dsp/catalog/register/getCatalog`、`/restapi/catalog-*` | `read-trace` |
| `catalog.entry.create` | `catalog_entry` + `catalog_item` | 目录注册、新增目录 | `write-critical` |
| `catalog.entry.change` | `catalog_entry_version` | 目录编辑、字段变更、版本对比 | `write-critical` |
| `catalog.entry.submit_review` | `approval_case` | `submitCatalogApprove` | `write-critical` |
| `catalog.entry.review` | `approval_decision` | `updateApproveCatalogStatus`、`approveCatalogPass/Refuse` | `write-critical` |
| `catalog.entry.publish` | `catalog_entry` + audit | 发布 / 上架 | `write-critical` |
| `catalog.entry.withdraw` | `catalog_entry` + `approval_case` | 撤销 / 下线 | `write-critical` |
| `catalog.item.import` | `catalog_item` | `importCatalogColumnExcel` | `write-critical` |
| `catalog.version.compare` | `catalog_entry_version` | `catalogVersionCompare` | `read-trace` |
| `catalog.version.restore` | `catalog_entry_version` + `approval_case` | `catalogVersionBack` | `write-critical` |
| `catalog.group.query` | 分类 / 专题投影 | `queryCatalogGroupList`、`queryCatalogGroupTree` | `read-trace` |
| `catalog.visibility.policy.update` | `tenant_capability_policy` / 可见性投影 | `grouppermission/*` | `write-critical` |
| `resource.catalog_binding.query` | `resource_asset` + `catalog_entry` | `getLinkCatalogResource`、`getLinkCatalogService` | `read-trace` |
| `resource.catalog_binding.change` | `resource_asset` / `resource_channel_binding` | 资源挂接、资源推送 | `write-critical` |
| `application.catalog.apply` | `application_record` | `data_apply*`、申请入口 | `write-critical` |
| `ops.catalog.summary.query` | 统计投影 | `getDeptTotalCataNumAndResourceNum`、`getCatalogStatisticWithUser` | `read-trace` |
| `ops.catalog.visibility.query` | 开放/共享统计投影 | `getOpenCataNum`、`getSharedCataNum`、`getStatisticCataNum` | `read-trace` |
| `ops.catalog.quality.query` | 质量投影 | `catalog_quality_*` | `read-trace` |
| `ops.catalog.open_push.sync` | 外部开放平台 adapter + outbox | `PushOpenCatalogServiceImpl`、`push_open_catalog` | `write-critical` |

## 六、原生核心能力与 ANP 外化能力

### 6.1 zw-brain 原生核心产品业务能力

| 原生核心能力 | 承接对象 | 判定依据 |
| --- | --- | --- |
| 目录模型与字段治理 | `catalog_model*`、`catalog_item` | 高频模板接口与工单中的字段/信息项变更反复出现 |
| 目录发现与详情 | `catalog_entry`、搜索投影 | `/dsp/catalog/register/getCatalog` 与 `/restapi/*` 为头部调用 |
| 目录生命周期 | `catalog_entry.lifecycle_status`、`catalog_entry_version` | 旧注册、发布、变更、撤销、版本回滚是强责任链路 |
| 目录审批 | `approval_case`、`approval_decision` | 旧审核日志和 `updateApproveCatalogStatus` 有明确承重语义 |
| 资源挂接与申请入口 | `resource_asset`、`application_record` | 目录必须支撑“能不能要、怎么要、拿什么” |
| 分组/区域/可见性策略 | `tenant_capability_policy` + 可见性投影 | 旧分组权限影响目录可见范围，存在越权风险 |
| 共享专区 / 专题包 | P7 投影 | v4 已确认共享专区为必保留功能，但不另起事实源 |
| 目录统计与运营读面 | P6 / Dashboard 投影 | 高频统计接口与工单统计口径问题均证明其必要性 |
| 审计与证据回放 | `capability_call`、`audit_event`、`audit_receipt` | 政务目录发布、授权、撤销必须可追责 |

### 6.2 可通过 ANP / 外部 Capability 外化的能力

| 外化能力 | 外化形态 | 边界 |
| --- | --- | --- |
| 目录质量检测规则 | ANP 质量规则包 | 可读目录快照并输出问题，不直接改目录状态 |
| 项目化导入/清洗脚本 | 导入 adapter / 执行器 | 生成 draft 和 mapping evidence，发布仍走核心审批 |
| 开放平台推送执行 | 外部开放平台 adapter | 执行推送与回执采集，不成为开放状态事实源 |
| 门户展示插件 | 外部展示或投影消费端 | 只能消费搜索/专题投影，不写 canonical |
| 环境与接口诊断 | 监控、日志、数据库、网关诊断 Capability | 输出证据和建议，不直接变更业务状态 |
| 特殊地区目录规范 | 行业/地区模板包 | 注册为 `catalog_model` 草案，启用前走审核 |
| 长尾 Job | worker / registered package | 只处理可重算投影或 outbox，不新建后台岛 |
| 工单系统联动 | 工单 adapter | 只同步脱敏主题、状态摘要和证据引用，不复制工单系统 |

### 6.3 不可外化红线

- 目录、资源、申请、审批、授权、发布、撤销的核心状态机不可外化。
- 租户、权限、可见性策略裁决不可外化。
- 审计总线、审计回执、本地 outbox 事实不可外化。
- 外部 Capability 不得绕过 command / policy / audit 写 canonical DB。
- 明文密钥、内部地址、工单个人信息不得进入文档、日志或 canonical 明文字段。

## 七、工单事实画像

### 7.1 归因边界

`old/工单导出-列缩减.xlsx` 只有 1 个 sheet、791 条记录、8 列：工单 ID、标题、状态、升级状态、问题描述、处理描述、沟通记录、问题级别历史。该文件没有“项目名称/代码仓库”列，因此不能严格按 `dsp-catalog3` 仓库归因。

核验结果：

- 直接命中 `dsp-catalog3` / `catalog3`：0 条。
- 使用目录域专有词（目录、编目、信息项、目录字段、目录编码、门户目录、开放目录、目录系统、catalog、cata）保守筛选：237 条候选。
- 候选工单状态：已完成 209、挂起 20、处理中 7、升级中 1。

因此，工单只作为目录域能力边界证据，不作为旧项目精确工作量统计。

### 7.2 目录域候选问题聚类

同一工单可命中多个主题，聚类用于识别产品能力，不用于考核口径。

| 主题 | 候选命中 | 对新系统的启发 | 归属 |
| --- | ---: | --- | --- |
| 接口/API 报错或性能 | 98 | 目录相关 API 需要可解释的调用证据、错误归因和运营投影 | Core + External |
| 权限申请审批 | 90 | 申请、受理、审批、授权必须有显式状态机和可见进度 | Core |
| 字段/信息项变更 | 83 | 目录字段治理要有版本、差异、导入校验和发布前确认 | Core |
| 发布后门户不可见 / 上下线 | 54 | 发布状态、门户/专题投影、开放推送需要一致性校验 | Core + External |
| 统计口径异常 | 29 | 统计投影必须可回指来源，不可用临时表反推事实 | Core |

### 7.3 工单对产品边界的反证

工单暴露的真实问题不是“缺更多后台菜单”，而是旧系统把状态、投影、门户、接口、权限分散在多个位置：

- 字段变更后，目录列表、门户筛选、开放目录和资源申请未必同步。
- 目录发布后，门户或专题投影可能不可见。
- 申请受理、审批、授权的步骤容易被项目化配置拆散。
- 统计口径依赖临时表或页面逻辑，无法解释“为什么这里有、那里没有”。
- 接口报错常混杂数据库、网关、资源、目录和外部系统问题，需要诊断 Capability，但不能把诊断结果直接当业务状态。

因此，zw-brain 应把状态机和事实源收紧，把投影和诊断外化或可重算，而不是继续堆功能入口。

## 八、adapter 迁移规则

### 8.1 输入源

| adapter source | 读取对象 | 输出 |
| --- | --- | --- |
| `dsp_catalog_model` | `model_*` 表族 | `catalog_model`、`catalog_model_step`、`catalog_model_field` 草案 |
| `dsp_catalog_entry` | `data_catalog`、`data_catalog_column`、版本表 | `catalog_entry`、`catalog_item`、`catalog_entry_version`、`legacy_object_mapping` |
| `dsp_catalog_resource` | `data_resource*`、`api_service*` 关联 | `resource_asset`、`resource_channel_binding`、目录资源绑定证据 |
| `dsp_catalog_approval` | `data_catalog_approve`、`data_resource_approve`、标准目录审批 | `approval_case`、`approval_step`、`approval_decision`、`audit_event` |
| `dsp_catalog_application` | `data_apply*` | `application_record`、`requested_items`、授权快照 |
| `dsp_catalog_open_share` | `open_catalog*`、`push_open_catalog`、共享专区表 | P7 / 开放目录投影、外部 adapter outbox |
| `dsp_catalog_metrics` | 统计表、质量检测结果 | P6 / Dashboard 投影 |
| `ticket_catalog_evidence` | 脱敏工单主题与证据引用 | 故障主题、能力缺口、诊断线索，不写业务事实 |

### 8.2 输出纪律

- adapter 只读旧库、旧文件和旧接口，不回写旧系统。
- adapter 输出 canonical draft 后，后续写入必须经 Capability、policy、audit。
- 每个旧对象必须有 `legacy_object_mapping`；冲突进入 `mapping_status='conflicted'`，不得自动覆盖。
- 统计投影允许重算；业务状态不允许由统计表反推。
- 旧门户展示、旧菜单、旧页面状态不作为新系统事实源。
- 工单素材只允许沉淀脱敏主题、故障模式、证据引用和处置摘要，不写客户姓名、联系方式、内部地址、密钥或工单原文。

## 九、落地波次

### Wave 0：目录读面、统计投影与审计证据

目标：先让旧系统高频目录查询和统计能力在 zw-brain 中有可解释读面。

- 建立 `catalog_entry` / `catalog_item` 的只读 adapter 映射。
- 建立 `ops.catalog.summary.query`、`catalog.entry.query`、`catalog.model.query`。
- 建立目录、资源、开放、共享统计投影，来源必须可回指旧统计表、审计事件或 adapter 快照。
- 把旧 `getDeptTotalCataNumAndResourceNum`、`getCatalogStatisticWithUser`、开放/共享数量类接口收敛到 P6 / Dashboard 读面。

### Wave 1：目录编目、发布与审批主链

目标：让供给侧可以在新系统中完成目录草稿、字段治理、提交审核、发布、版本留痕。

- `model_*` → `catalog_model*`。
- `data_catalog` / `data_catalog_column` → `catalog_entry` / `catalog_item`。
- `submitCatalogApprove` / `updateApproveCatalogStatus` → `approval_case` / `approval_decision`。
- `catalogVersionCompare` / `catalogVersionBack` → `catalog_entry_version`。
- 所有写动作经 Capability 调用并同步写审计。

### Wave 2：资源挂接、申请授权与共享专区

目标：把目录从“能看”推进到“能申请、能交付、能共享”。

- `data_resource*` → `resource_asset` / `resource_channel_binding`。
- `data_apply*` → `application_record` / `approval_case` / `delivery_task.access_grant_snapshot`。
- 分组权限和可见性策略进入 `tenant_capability_policy` 与可见性投影。
- P7 共享专区消费专题投影，不新建共享专区事实源。

### Wave 3：外化能力注册与 legacy 退役

目标：把长尾质量、开放推送、门户展示、地区模板、诊断脚本迁出主仓核心。

- 质量检测规则注册为 ANP / Capability 包。
- 开放目录推送执行器注册为外部 adapter。
- 门户展示和专题渲染只消费投影。
- 以主旅程替代程度和外部能力覆盖程度判断 legacy 退役，而不是以旧菜单迁移率判断。

## 十、验收标准

1. 任一目录、资源、申请、审批迁移对象必须能回指 `legacy_object_mapping`。
2. 任一写动作必须经过 Capability、policy、audit；页面、adapter、外部包不得直接写 canonical 状态。
3. 目录在 WebUI 中首先表现为可发现、可申请、可治理的资源入口，不是旧后台菜单。
4. 目录字段变更必须有版本快照、差异和发布前确认。
5. 统计查询必须说明来源：审计事件、旧统计表快照、adapter 日志或可重算投影。
6. 开放/共享/门户投影不可反向覆盖目录生命周期状态。
7. 分组/区域/权限只作为策略输入或可见性投影；IAM 仍是组织身份权威。
8. 任一 ANP / 外部 Capability 必须声明输入输出 contract、审计等级、租户策略和失败回写方式。
9. 工单素材不得泄露个人、组织、内部地址、联系方式或密钥原文。
10. 新契约以 Capability slug 为准，旧 URL 不作为兼容承诺。

## 十一、事实推敲清单

| 结论 | 证据 | 反证处理 |
| --- | --- | --- |
| catalog3 核心是目录/资源/审批/申请链 | 旧实体 `@TableName`、`dsp_catalog.xml` 表族 | 若某旧功能无法回指主链，默认外化或不迁入 |
| 高频能力集中在查询、模板、分组、资源关联、统计 | `dsp-catalog3-apis.md` 头部接口 | 不复制低频 URL；只抽象 Capability |
| 工单只能做目录域候选归因 | Excel 缺项目列，直接命中 catalog3 为 0 | 文档不写“catalog3 工单精确数量” |
| 字段/信息项治理必须内建 | XML 中目录模型/信息项表族 + 工单字段问题 | 质量检测规则可外化，但字段事实和版本不可外化 |
| 开放/共享是投影与适配，不是第二事实源 | `open_catalog*` / `push_open_catalog` 与 v4 P7 约束 | 外部开放平台失败只写回执/告警，不改目录事实 |
| 统计不能反推状态 | 大量统计表与工单统计口径问题 | 统计投影可重算，生命周期以 canonical 状态为准 |

## 十二、源码证据索引

| 结论 | 源码 / 数据证据 |
| --- | --- |
| 旧仓库版本为 `3.12.15` | `old/old_codes/dsp-catalog3/pom.xml` |
| 主模块为 common / console / service / job | `old/old_codes/dsp-catalog3/pom.xml` |
| 目录注册主入口 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/catalog/CatalogRegisterController.java` |
| 目录审核主入口 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/catalog/CatalogApproveController.java` |
| 对外目录 API 主入口 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/api/OpenApiController.java` |
| 目录模型 API | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/api/catalogModel/CatalogModelController.java` |
| 分组权限入口 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/catalog/CatalogGroupPermissionController.java` |
| 资源推送入口 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/resource/ResourcePushController.java` |
| 目录状态推进与 MQ 同步 | `dsp-catalog-service/src/main/java/com/inspur/dsp/catalog/service/impl/CatalogServiceImpl.java` |
| 开放目录推送 | `dsp-catalog-service/src/main/java/com/inspur/dsp/open/service/impl/PushOpenCatalogServiceImpl.java` |
| 旧表结构事实 | `old/12-datastructure/dsp_catalog.xml`、`old/12-datastructure/dsp_service.xml` |
| 外部调用 Pareto | `old/old_codes_analyse/dsp-catalog3-apis.md` |
| 工单目录域候选画像 | `old/工单导出-列缩减.xlsx` |
