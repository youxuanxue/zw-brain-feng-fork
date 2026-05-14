# dsp-catalog3 / dsp-metadata3 相关模块重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-catalog3`（目标版本 3.12.15）、`old/old_codes/dsp-metadata3`（目标版本 3.9.15）、外部调用分析 `old/old_codes_analyse/dsp-catalog3-apis.md` / `old/old_codes_analyse/dsp-metadata3-apis.md`、旧结构数据 `old/12-datastructure` 与脱敏工单数据 `old/工单导出-列缩减.xlsx`。
> 结论：zw-brain 是全新 AI 原生项目，不兼容旧接口、旧菜单、旧库表，也不把 catalog3 / metadata3 原样迁成两个新子系统；本方案只吸收目录、元数据、资源、申请、授权、发布、质量、血缘等承重业务语义，重建为围绕主旅程、统一 Capability、可审计、可外化扩展的能力面。
> 单一事实源：本文是 dsp-catalog3 / dsp-metadata3 专题映射、字段落位、能力迁移和 ANP 外化边界的单一事实源；`docs/approved/*` 只保留 canonical 通用模型与本文引用。

## 一、设计原则

### 1.1 Jobs：从“目录后台 + 元数据后台”改成“找得到、要得清、交付稳、证据可追”

旧 `dsp-catalog3` 的表面形态是目录注册、目录审批、目录发布、目录分组、资源推送、共享专区、质量检测、统计任务等后台模块；旧 `dsp-metadata3` 的表面形态是数据源管理、表/文件/接口资源注册、资源审核、资源发布、元数据采集、血缘、物化、标准推荐等后台模块。

zw-brain 不继承这些模块名，也不复刻它们的页面层级。它们在新系统中只保留五类用户可感知价值：

1. 用户能发现目录、资源、字段口径和可申请边界。
2. 提供方能把目录、资源和元数据证据发布为可治理资产。
3. 申请、审批、授权、发布、撤回能进入统一状态机和审计链。
4. 元数据采集、血缘、质量和物化证据能解释资源是否可信、能否交付。
5. 低频、项目化、基础设施耦合强的动作通过 ANP / 外部 Capability 注册，不占用主产品心智。

### 1.2 OPC：单一事实源，不为 catalog / metadata 开第二套治理中心

- 目录模型、目录条目、资源资产、通道绑定继续进入 `brain_core` 的 canonical model，不再建立并列的“目录中心”和“元数据中心”。
- catalog3 / metadata3 专属映射、投影字段、迁移规则和能力边界以本文为单一事实源；approved 数据模型只保留通用结构与本文引用。
- 旧库、旧 API、旧 Dubbo、旧 Kafka、旧 xxl-job 只作为只读 adapter 输入、执行器线索或外部化候选，不成为新业务写入口。
- 页面、REST、CLI、MCP、A2A 都从统一 Capability contract 投影，不按旧 controller URL 兼容。
- 工单只作为脱敏后的真实问题证据，不把旧工单系统、客户环境、人员信息或内部地址迁入 canonical model。

### 1.3 合并分析 catalog3 / metadata3 的原因

catalog3 与 metadata3 在旧平台中表面上是两个仓库，但在业务事实上是同一条资源治理链：

1. catalog3 负责把“目录、分组、共享、申请、授权、发布”呈现给共享侧用户。
2. metadata3 负责把“数据源、表字段、文件、接口、血缘、采集、资源审核”沉淀成资源证据。
3. 结构数据中 `data_catalog.cata_id`、`data_catalog_column.cata_id`、`data_apply.cata_id/resource_id`、`rc_resource.cata_id`、`rc_resource_catalog_item_link.catalog_item_id/table_column_id` 已经证明目录信息项、资源、元数据字段和申请授权相互绑定。
4. 工单中“目录发布后门户不显示”“资源申请授权看不到申请”“反向编目失败”“挂接资源不显示列”“物化资源结构调整报错”等问题都跨越 catalog 与 metadata 边界。

因此，新系统不应按旧仓库拆两个事实源，而应按 `CatalogResourceAggregate` 与主旅程重建一套事实源。

## 二、证据清单

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture-v4-gpt55.md` | 产品围绕少数高频旅程；人和 Agent 共用同一 Capability；长尾新增能力默认外部生产、平台注册；合规可证迹内建。 |
| `docs/approved/zw-brain-data-model-v4-gpt55.md` | 模型围绕旅程与审计组织，不围绕 legacy 表名组织；legacy schema 只作为 adapter 输入；目录、申请、交付等强状态领域必须保留显式状态机。 |
| `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` | 目录 / 元数据涉及的组织、角色、权限裁决和租户策略只消费 zw-brain Governance 与 Capability policy，不复刻旧 IAM / 菜单 / 权限后台。 |
| `docs/approved/zw-brain-golden-path-r1-r3-r5-v1.md` | 首条黄金链路要把上级需求、资源/模板复用、基层补差、审核汇总和回流共享资源池打通。 |
| `docs/approved/zw-brain-user-roles-and-journeys-v1.md` | 用户不是抽象管理员，而是要数的人、管数的人、填数的人、审数的人、查责的人；目录/元数据能力必须服务这些岗位。 |
| `docs/approved/zw-brain-data-standards-utilization-scheme-v1.md` | 标准样本和历史实现只能作为证据层；正式标准资产进入 `CatalogModel`、`catalog_model_field` 和 Registry，不重建标准平台。 |

### 2.2 外部使用证据

`dsp-catalog3` 去重后 163 个接口、三项目合计 186,679 次调用。头部调用集中在：

| 旧能力 / 接口簇 | 调用特征 | 新系统解释 |
| --- | ---: | --- |
| `/restapi/getDeptTotalCataNumAndResourceNum` | 21,198 | 部门目录/资源统计是 P6 / Dashboard 运营投影，不是新事实源。 |
| `/dsp/catalog/register/getCatalog` | 13,432 | 目录详情与编辑是 `catalog_entry` / `catalog_entry_version` 的强状态能力。 |
| `/api/model/catalog-template-info` | 13,051 | 目录模板是 `CatalogModel`，支撑标准业务表和基层预填。 |
| `/restapi/dict/getDictInfo` | 9,192 | 字典是标准/字段口径证据，不应散落在页面逻辑。 |
| `/dsp/catalog/group/queryCatalogGroupList` | 6,668 | 目录分组是搜索/共享专区投影，不应成为独立核心系统。 |
| `/dsp/resource/resourcepush/getLinkCatalogResource` | 6,648 | 资源挂接是目录与资源交付能力的核心链路。 |
| `/dsp/resource/resourcepush/getResourceData` | 6,380 | 资源数据预览/挂接证据进入资源详情和交付前校验。 |
| 目录统计、开放数、共享数 | 单项约 6,000 | 运营统计进入可重算投影。 |
| 目录审批日志 `/getApproverOptLog` | 4,956 | 审批意见必须进入 `approval_case` / `approval_decision` / `audit_receipt`。 |

`dsp-metadata3` 去重后 100 个接口、三项目合计 32,342 次调用。头部调用集中在：

| 旧能力 / 接口簇 | 调用特征 | 新系统解释 |
| --- | ---: | --- |
| `/manage/list` | 5,793 | 元数据资源列表是 P2 / P5 资源发现和提供方管理视图。 |
| `/manage/index` | 3,141 | 后台入口不迁入，但其背后的资源管理语义迁入。 |
| `/checklog/list` | 2,683 | 资源审核流转日志进入审批与审计回放。 |
| `/table/view` | 2,323 | 表结构详情进入 `resource_schema_snapshot` / `resource_channel_binding.schema_ref`。 |
| `/review/list` | 2,021 | 资源审核进入统一 `approval_case`。 |
| `/table/queryTableList` | 1,277 | 数据表候选清单是元数据 adapter 读面。 |
| `/database/query` | 1,028 | 数据源查询是外部数据源投影，不做数据库管理后台。 |
| 资源统计 `/resource/statistic/*` | 800+ | 进入 P6 运营投影。 |
| `/catalog/list`、`/catalog/queryItemList` | 683 / 408 | 证明 metadata3 反向依赖目录信息项。 |
| `/metadata/gather/list` | 428 | 采集任务事实进入证据和执行器，不进入普通主导航。 |

### 2.3 结构数据证据

| 结构来源 | 关键旧表 / 字段 | 对本方案的约束 |
| --- | --- | --- |
| `old/12-datastructure/dsp_catalog.xml` | `data_catalog`、`data_catalog_column`、`data_catalog_column_version` | 目录和目录信息项进入 `catalog_entry`、`catalog_entry_version`、`catalog_item`；字段口径进入 `catalog_model_field` 或目录项快照。 |
| `dsp_catalog.xml` | `data_catalog_tag` | 标签是目录检索、专题聚合和推荐证据，不单独长成标签平台。 |
| `dsp_catalog.xml` | `catalog_quality_task`、`catalog_quality_task_log`、`catalog_quality_task_result`、`catalog_quality_task_report` | 目录质量检测进入质量证据投影；任务执行器可外化。 |
| `dsp_catalog.xml` | `data_apply`、`data_apply_item`、`data_apply_course`、`data_apply_authrization`、`data_apply_authrization_approve`、`data_apply_renewal` | 申请、申请项、审批过程、授权、续期必须进入 `application_record`、`approval_case`、`delivery_task` 和审计回执。 |
| `dsp_catalog.xml` | `dockapply`、`dockapply_approve_info`、`dockapply_service_info`、`dockapply_theme_info` | 垂管对接是项目化/国家或上级通道适配，默认外化为 Capability 包或 adapter。 |
| `dsp_catalog.xml` | `share_zone_catalog_link`、`share_zone_org_auth`、`catalog_share_group`、`share_group_permission` | 共享专区保留为 P7 主题/分组投影；权限裁决仍走统一租户策略。 |
| `old/12-datastructure/dsp_metaresource.xml` | `meta_baseinfo`、`meta_baseinfo_history` | 元数据本体和版本进入资源证据与 schema 快照，不成为独立元数据产品首页。 |
| `dsp_metaresource.xml` | `rc_resource`、`rc_resource_table`、`rc_resource_file`、`rc_resource_url` | 表、文件、链接等资源统一进入 `resource_asset` 与 `resource_channel_binding`。 |
| `dsp_metaresource.xml` | `rc_resource_catalog_item_link` | 目录信息项与表字段的挂接关系是核心事实，必须可回放。 |
| `dsp_metaresource.xml` | `meta_relation`、`meta_relation_column` | 血缘关系进入 lineage read model / evidence，不反向驱动业务状态。 |
| `dsp_metaresource.xml` | `graphdb_node`、`graphdb_relation`、`graphdb_relation_attr`、`graphdb_relation_column` | 图谱结构是血缘/关系查询投影或外部图谱 adapter，不作为 Phase 1 核心写模型。 |
| `dsp_metaresource.xml` | `meta_gather_task`、`meta_gather_task_log` | 采集任务进入外部执行器和审计证据；调度不进普通用户产品心智。 |
| `dsp_metaresource.xml` | `audit_todo_task`、`resource_flow_log` | 资源审核待办与流转日志进入统一审批轨迹，不保留 metadata3 自有流程岛。 |
| `dsp_metaresource.xml` | `rc_catalog_materialize` | 目录物化证明 catalog 与 metadata 共享同一资源交付链；物化执行外化，核心只保存映射、版本和回执。 |
| `dsp_metaresource.xml` | `db_database_node`、`database_manage_history` | 数据源、前置库、建表执行和数据库操作日志是外部执行器证据；内部地址、端口、连接路径不得明文进入 canonical model。 |
| `dsp_metaresource.xml` | `meta_log` | 元数据操作日志进入 `audit_event` 或迁移证据。 |
| `old/12-datastructure/dsp_monitor.xml` | `matter_manage`、`matter_handle`、`warning_work_order_rules` 等工单/告警语义 | 告警与工单只作为 P6 运营投影和外部诊断 Capability 输入，不复制监控工单系统。 |
| `old/12-datastructure/dsp_connect.xml` | 上级目录 ID、对接目录等同步语义 | 级联 / 上下级对接进入 adapter 与外部通道，不改变 canonical 主事实源。 |

## 三、真实工单事实

### 3.1 工单命中概况

`old/工单导出-列缩减.xlsx` 的 `工单导出` sheet 共 791 条记录，列包括 `工单ID`、`工单标题`、`工单状态`、`工单升级状态`、`问题描述`、`处理描述`、`沟通记录`、`问题级别历史`。按关键词粗分，相关主题命中如下：

| 主题关键词 | 命中条数 | 对本方案的启发 |
| --- | ---: | --- |
| 目录 | 195 | 目录发布、展示、统计、字段口径是最高频问题域。 |
| 门户 | 118 | 旧问题常表现为门户不显示/统计异常；新系统应把展示一致性变成投影和证据问题，而不是门户补丁问题。 |
| 发布 | 79 | 目录/资源发布必须有显式状态机、版本和回执。 |
| 授权 | 60 | 资源申请后的授权、续期、频次变更是强责任链路。 |
| 资源申请 | 51 | 申请、审批、受理、授权不能散落在旧系统。 |
| 漏洞 | 45 | 运行环境和组件漏洞是外部运维/安全执行器，不进入核心业务模型。 |
| dsp-catalog | 29 | 工单多与目录显示、应用注册、共享门户适配有关。 |
| dsp-metadata | 16 | 工单多与 job、资源更新、物化、漏洞、数据库适配有关。 |
| 挂接 | 10 | 目录项与资源/表字段挂接是实际交付问题。 |
| 元数据 | 8 | 中文注释、采集、数据库适配是元数据质量证据。 |
| 标签 | 8 | 标签影响目录分类与发现，但不应独立成核心平台。 |
| 编目 | 7 | 反向编目和智能编目是能力包/外部执行器候选。 |

本文不摘录工单中的人员、组织、内部地址、附件链接或客户环境细节；只保留脱敏后的问题模式。

### 3.2 高频问题模式

| 工单问题模式 | 旧平台表现 | zw-brain 处理 |
| --- | --- | --- |
| 目录发布后门户不显示 | 目录系统已发布，门户或共享站点没有同步展示 | 目录发布写 `catalog_entry_version` + `audit_receipt`；搜索/门户投影异步生成并带 `projection_status`，P6 可解释卡在哪一步。 |
| 目录 / 资源统计异常 | 部门调整、区划变更、门户统计与资源系统不一致 | 统计只作为可重算 projection；组织/区划保存快照和来源，不反向改业务事实。 |
| 资源申请授权缺失 | 用户申请后在授权系统看不到记录，或频次变更缺少审批接口 | 申请、审批、授权、续期统一进入 `application_record`、`approval_case`、`delivery_task.access_grant_snapshot`。 |
| 目录字段新增与门户筛选 | 客户要求目录列表新增回流、筛选字段 | 字段进入 `catalog_model_field` / `catalog_item` 扩展口径；展示配置是投影，不为每个客户 fork 后端。 |
| 反向编目差异 | 反向编目时英文名、中文名、表字段关系与在线编制不同 | 反向编目作为外部 Capability 草拟目录项，最终写入仍走 catalog capability、确认和审计。 |
| 挂接资源不显示表列 | Excel 转库表、资源挂接后列不展示 | `rc_resource_catalog_item_link` 语义迁入目录项-字段挂接事实；表字段快照必须可追溯。 |
| 物化资源结构调整报错 | 已物化多版本资源调整结构时报错 | 物化与结构调整是高副作用执行器；核心只管理资源版本、schema 快照、审批和回执。 |
| 元数据中文注释缺失 | 模板文字字段显示未知，补充元数据中文注释后解决 | 字段中文名、说明、数据类型、敏感级别是 `catalog_item` / `schema_ref` 的基本质量要求。 |
| job / 漏洞 / 中间件适配 | metadata job 报错、GBase / TongWeb / Elasticsearch / `dsp-catalog-console` / `dsp-metadata-job` 漏洞修补 | 属于运行时和项目环境能力，通过 ANP 诊断/修复包外化；新产品只沉淀脱敏故障模式、影响范围、处置回执。 |

### 3.3 工单对产品边界的校准

工单证明用户真正关心的不是“有没有目录管理菜单”或“有没有元数据管理菜单”，而是：

1. 发布后的目录能不能被发现。
2. 申请后的授权能不能生效。
3. 资源挂接后的字段能不能解释和交付。
4. 统计口径能不能追溯。
5. 采集、物化、调度失败时能不能定位责任和证据。

因此，新方案必须把目录/元数据后台压缩成少数主旅程能力，而不是把旧后台菜单换皮。

## 四、旧 dsp-catalog3 能力理解

### 4.1 模块边界

| 旧模块 / 入口 | 旧职责 | zw-brain 去向 |
| --- | --- | --- |
| `CatalogRegisterController` | 目录注册、详情、版本、提交审批、删除/撤销 | `catalog_entry`、`catalog_entry_version`、`approval_case`，写动作走 Capability。 |
| `CatalogApproveController` | 目录审批、审批日志、状态更新、版本对比 | `approval_case`、`approval_step`、`approval_decision`、`audit_receipt`。 |
| `CatalogPublish` / `topublish` | 待发布、发布、退回发布 | `catalog.entry.publish` / `catalog.entry.withdraw` 等写 Capability。 |
| `CatalogGroup*` / `CatalogGroupPermission*` | 目录分组、共享分组、用户/部门权限 | P7 共享专区 projection + `tenant_capability_policy`，不复刻权限后台。 |
| `ResourcePushController` | 目录挂接资源、资源数据预览、推送 | `resource_asset`、`resource_channel_binding`、目录项-资源绑定。 |
| `OpenApiController` | 对外目录统计、申请查询、资源查询 | 新 REST 由 Capability 投影，统计进入 read model。 |
| `catalogModel` API | 目录模板、字段、历史字段、导入模板 | `CatalogModel` 与 `catalog_model_field`。 |
| `catalogCompile` / 反向编目 | 编目任务、替换任务、国家目录、历史目录 | 外部编目/反向编目 Capability 草拟，最终写入走核心确认。 |
| `catalogquality` | 质量规则、任务、报告、人工检测 | 质量证据 projection；任务执行外化。 |
| `dsp-catalog-job` | 统计、推送开放目录、导入导出、预警、短信 | worker / adapter / 外部 Capability，不进普通主导航。 |

### 4.2 catalog3 承重语义

| 旧实体 / 语义 | 承重价值 | canonical 落点 |
| --- | --- | --- |
| `data_catalog` | 目录本体、提供方、区划、共享类型、发布状态 | `catalog_entry` |
| `data_catalog_version` / `data_catalog_column_version` | 目录与信息项版本 | `catalog_entry_version` + schema snapshot |
| `data_catalog_column` | 目录信息项、字段名称、类型、长度、敏感级别、共享条件 | `catalog_item` / `catalog_model_field` |
| `data_catalog_tag` | 目录标签、事项、主题分类 | 搜索/专题投影，必要字段写 `catalog_entry.tags_snapshot` |
| `data_apply` | 资源申请本体 | `application_record` |
| `data_apply_item` | 申请的数据项范围 | `application_attachment` 或 `application_record.requested_items_snapshot` |
| `data_apply_course` / `data_apply_dept_approve` / `data_apply_review` | 审批过程、意见、部门审批 | `approval_case`、`approval_step`、`approval_decision` |
| `data_apply_authrization` / `data_apply_renewal` | 授权和续期 | `delivery_task.access_grant_snapshot`、`delivery_subscription` |
| `catalog_quality_task*` | 目录质量检测任务和结果 | `quality_evidence_projection` + 外部执行器回执 |
| `share_zone_catalog_link` / `catalog_share_group` | 共享专区、目录专题分组 | P7 topic projection，不单独成为事实源 |
| `dockapply*` | 垂管/上级对接申请 | 外部通道 adapter + `delivery_task` / `approval_case` 摘要 |

### 4.3 catalog3 源码校准

| 源码事实 | 设计校准 |
| --- | --- |
| `StandardCatalogServiceImpl` 同时承接目录提交、审批通过/驳回、撤销和发布后变更逻辑，`StandardCatalogVersionServiceImpl` 基本为空 | 旧系统并没有一个干净的“版本子域”；zw-brain 必须把版本、审批和发布重新收敛到 `catalog_entry_version` + `approval_case`，不能照搬旧 service 分层。 |
| `PushOpenCatalogServiceImpl` 在推送开放目录时读取目录关联资源，并组装 `catalogItemColumnLinks` | 目录对外可见、资源挂接和字段映射是一条链；`catalog.resource.bind` 必须是强审计写能力，而非展示层动作。 |
| `CatalogModelServiceImpl` 会根据模板字段写 `data_catalog_column` 并执行动态扩展表创建/调整 | 模板字段是承重口径；动态建表属于高副作用执行器，不能进入普通 catalog capability 的直接写路径。 |
| `CatalogCompileServiceImpl` 的反向编目会处理共享/开放字段映射并设置反向标识 | 反向编目只能生成草稿和建议；最终发布必须回到人工确认、核心状态机和审计链。 |
| `CatalogQualityTaskServiceImpl`、`CatalogGroupServiceImpl`、`CatalogShareGroupServiceImpl` 主要围绕任务、分组、共享包装运行 | 质量、分组、共享专区保留产品价值，但应作为 projection / 外部执行器 / 策略解释，不独立成长为事实源。 |

## 五、旧 dsp-metadata3 能力理解

### 5.1 模块边界

| 旧模块 / 入口 | 旧职责 | zw-brain 去向 |
| --- | --- | --- |
| `ManageContoller` | 元数据资源列表、详情、状态检查、删除、撤销、审核 | `resource_asset` 与统一审批状态机。 |
| `TableController` | 数据表资源注册、表列表、字段列表、数据源列表、结构变更 | 表资源 channel/schema 证据；结构变更写动作需审批。 |
| `FileController` / `FolderController` | 文件/文件夹资源注册 | `resource_asset(resource_kind='file/folder')`。 |
| `ReviewController` | 资源审核、批量审核、驳回 | `approval_case` 与审计回执。 |
| `PublishController` | 资源发布、回调 | `resource.asset.publish` / `resource.api.withdraw` Capability。 |
| `DataBaseController` / `DataBaseManageController` | 数据源、前置库、连通性、表管理、建表 | 数据源 read projection + 外部执行器；不做数据库管理后台。 |
| `MetaGatherTaskController` | 元数据采集任务列表、添加、触发、删除 | 外部采集 Capability + `metadata_gather_evidence_projection`。 |
| `MetaRelationController` / `TableColumnRelationController` | 血缘、字段关系 | lineage projection / evidence。 |
| `CatalogController` | 查询目录、目录项、目录分组 | 证明 metadata3 消费 catalog 语义；新系统统一回到 `catalog_entry`。 |
| `CatalogMaterialize` tools | 目录物化、结构调整、字段检查 | 高副作用外部执行器，核心只接收版本、schema、回执。 |
| `dsp-metadata-job` | ETL、DB、文件、开放资源推送、数据量更新、监控 | ANP / worker / adapter，不进入普通主导航。 |

### 5.2 metadata3 承重语义

| 旧实体 / 语义 | 承重价值 | canonical 落点 |
| --- | --- | --- |
| `meta_baseinfo` | 元数据对象本体、模型类型、组织、区划、版本、描述 | `metadata_object_snapshot` 或 `resource_schema_snapshot`，作为资源证据。 |
| `meta_baseinfo_history` | 元数据历史版本 | schema/evidence version，不直接当业务状态机。 |
| `rc_resource` | 资源本体、资源类型、关联目录、共享类型、组织区划 | `resource_asset` |
| `rc_resource_table` | 库表资源、数据库、表名、交换方式、开放状态 | `resource_channel_binding(channel_type='table')` + schema ref |
| `rc_resource_file` / `rc_resource_url` | 文件/链接资源 | `resource_asset` + `resource_channel_binding` |
| `rc_resource_catalog_item_link` | 目录信息项与表字段绑定 | `catalog_resource_item_binding` 或 `resource_schema_mapping` |
| `meta_relation` | 表/库级血缘、来源、目标、关系来源 | `lineage_relation_projection` |
| `meta_relation_column` | 字段级血缘 | `lineage_column_projection` |
| `graphdb_node` / `graphdb_relation` | 图谱节点和关系 | 外部图谱 adapter 或 lineage projection |
| `meta_gather_task` / `meta_gather_task_log` | 采集任务与执行日志 | `metadata_gather_evidence_projection` + `audit_event` |
| `meta_log` | 元数据操作日志 | `audit_event` / `legacy_object_mapping` evidence |
| `audit_todo_task` / `resource_flow_log` | 资源审核待办、节点、角色、意见、时间 | `approval_case`、`approval_step`、`approval_decision` |
| `rc_catalog_materialize` | 目录物化资源、数据源、表名、库类型 | 外部物化执行器证据 + `resource_schema_mapping` / `delivery_receipt` |
| 数据源 / 建表操作日志 | 连接节点、执行记录、结果、错误信息 | 外部诊断/执行 evidence；敏感连接信息只保存引用或脱敏摘要 |

### 5.3 metadata3 源码校准

| 源码事实 | 设计校准 |
| --- | --- |
| `ResourceReviewServiceImpl` 同时处理资源审核、发布/撤销状态推进、资源变更事件、开放事件和链路回写 | 资源审核不是 metadata3 后台的局部动作；它必须并入统一 `approval_case`、`resource_asset.status` 和审计事件。 |
| `ResourceManageServiceImpl` 删除表资源时清理关联资源、目录项映射和物化记录 | 资源、目录项字段绑定和物化结果存在生命周期耦合；新系统必须保留 `resource_schema_mapping` 的状态与回执，而不是只存资源列表。 |
| `DatabaseManageServiceImpl` 建表后触发元数据创建，连接测试、建表、元数据同步连成副作用链 | 建库建表和结构调整必须外化为受审批授权的执行器；核心只保存意图、审批、schema 快照和执行回执。 |
| `MetaBaseinfoServiceImpl` 会拉取 DB schema、列、索引、外键并用摘要判断结构变化、生成历史版本 | 元数据采集是 evidence 生成过程；采集失败或结构变化不能绕过资源状态机直接改变业务发布状态。 |
| `CatalogMaterialServiceImpl`、`RcCatalogMaterialize` 与 `ResourceManageServiceImpl` 共同证明物化记录会随资源生命周期清理 | 目录物化是目录项-字段映射后的交付执行结果，应进入外部执行器回执和 schema evidence，不成为第二套资源事实源。 |
| `RcResourceCatalogItemLink`、`CatalogItemLinkServiceImpl` 和 `ResourceManageMapper.xml` 大量查询绑定关系 | 目录信息项到真实表字段的绑定是 metadata 侧最承重的事实，必须显式建模为 `resource_schema_mapping`。 |
| metadata3 migration 长期给 `rc_resource_catalog_item_link`、资源字段精度、脱敏、默认值、标准引用补列 | 字段证据会随项目持续演化；zw-brain 应保存版本化 schema/mapping evidence，避免把字段结构固化进页面逻辑。 |

### 5.4 catalog3 / metadata3 合流判断

旧代码最强的信号不是“两个后台都很大”，而是二者不断互相调用和清理：catalog 推送需要资源与字段绑定，metadata 查询目录项，资源删除会清理物化和目录项链接，反向编目又从 metadata 证据生成 catalog 草稿。因此 zw-brain 的边界应按主旅程合流：目录定义、资源证据、字段映射、申请审批、交付回执进入同一 canonical 事实链；采集、建表、物化、质量、血缘作为外部执行器或 projection 回写证据。

## 六、zw-brain 数据模型设计

本节是 dsp-catalog3 / dsp-metadata3 相关数据模型与迁移映射的单一事实源；`docs/approved/zw-brain-data-model-v4-gpt55.md` 只保留 canonical model 通用结构，并引用本文。

### 6.1 CatalogResourceAggregate 的专题落位

| 领域对象 | 物理落点 | 说明 |
| --- | --- | --- |
| 目录模板 | `catalog_model` | 承接标准业务表、目录模板、台账模板，不承接旧后台导入页面。 |
| 模板字段 | `catalog_model_field` | 承接字段名、类型、长度、值域、敏感级别、共享条件、来源证据。 |
| 目录条目 | `catalog_entry` | 承接旧 `data_catalog` 的目录本体和生命周期。 |
| 目录版本 | `catalog_entry_version` | 承接目录变更、发布、撤销、回滚所需版本快照。 |
| 目录信息项 | `catalog_item` | 承接旧 `data_catalog_column`，与资源字段映射分离。 |
| 资源资产 | `resource_asset` | 承接旧 `rc_resource` 及 catalog 侧资源概念，按 table/file/folder/api/url 等统一建模。 |
| 通道绑定 | `resource_channel_binding` | 承接表、文件、API、链接、交换方式、schema、认证引用、策略快照。 |
| 目录项-资源字段绑定 | `resource_schema_mapping`（建议新增为 `brain_core` 表或作为 `resource_channel_binding.schema_ref` 内的强结构） | 承接 `rc_resource_catalog_item_link`，支撑“目录项为什么能由这张表这个字段交付”。 |
| 元数据证据快照 | `resource_schema_snapshot`（建议作为 `brain_core` read/evidence table 或对象存储引用） | 承接 `meta_baseinfo`、表字段、中文注释、版本、采集来源。 |
| 血缘投影 | `lineage_relation_projection` / `lineage_column_projection` | 承接 `meta_relation`、`meta_relation_column`、graphdb 关系，只读可重算。 |
| 质量证据投影 | `quality_evidence_projection` | 承接目录质量、采集质量、字段完整性、挂接一致性检查结果。 |

### 6.2 建议补充的 canonical 辅助表

approved 数据模型已有 `catalog_entry`、`catalog_item`、`resource_asset`、`resource_channel_binding`、`application_record`、`approval_case`、`delivery_task`、`audit_event` 等主结构。结合 catalog3 / metadata3 事实，建议在实现阶段补充三个克制的辅助结构：

#### 6.2.1 `resource_schema_mapping`

用途：表达目录信息项与资源实际字段的稳定绑定，解决工单中“挂接后不显示列”“字段口径不一致”“目录发布后无法交付”的证据链问题。

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `catalog_entry_id` | 目录 |
| `catalog_item_id` | 目录信息项 |
| `resource_id` | 资源资产 |
| `channel_binding_id` | 表/API/文件等通道绑定 |
| `source_schema_ref` | 表字段/API 参数/文件列引用 |
| `mapping_rule_json` | 映射、转换、脱敏、值域规则 |
| `confidence_level` | `confirmed/suggested/conflicted` |
| `evidence_ref` | 元数据采集、人工确认或 adapter 证据 |
| `status` | `draft/active/superseded/revoked` |
| `confirmed_by` / `confirmed_at` | 人工确认回执 |

约束：`UNIQUE (tenant_id, catalog_item_id, resource_id, channel_binding_id, status)` 对 active 记录做部分唯一，防止同一目录项被多个当前字段无解释地覆盖。

#### 6.2.2 `metadata_gather_evidence_projection`

用途：承接采集任务、采集日志和字段快照，让 P5 / P6 能解释“这个资源 schema 从哪里来、何时采集、是否可信”。

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `resource_id` | 资源 |
| `gather_task_ref` | 旧 `meta_gather_task.task_id` 或外部执行器任务引用 |
| `source_system_ref` | 数据源 / 文件服务器 / 前置库引用 |
| `schema_snapshot_ref` | schema 快照对象或 JSON 引用 |
| `status` | `pending/running/succeeded/failed/stale` |
| `started_at` / `finished_at` | 执行时间 |
| `error_summary` | 脱敏错误摘要 |
| `audit_event_id` | 审计事件 |
| `generated_at` | 投影生成时间 |

约束：它是 projection，不是采集调度事实源；调度由 ANP / 外部执行器承接。

#### 6.2.3 `lineage_relation_projection`

用途：承接表级、字段级、图谱关系查询，服务 P5 资源治理和 P6 审计解释。

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `relation_scope` | `table/column/graph_node/graph_relation` |
| `source_resource_id` / `source_schema_ref` | 来源资源或字段 |
| `target_resource_id` / `target_schema_ref` | 目标资源或字段 |
| `relation_type` | `etl/manual/materialized/derived/imported` |
| `relation_rule_json` | 清洗、转换、关联条件摘要 |
| `source_evidence_ref` | ETL 解析、人工维护、graphdb adapter 等证据 |
| `generated_at` | 生成时间 |

约束：血缘是只读解释和影响分析能力，不反向推进目录、申请、授权状态。

### 6.3 字段级映射规则

| legacy 字段 / 语义 | canonical 落点 | 规则 |
| --- | --- | --- |
| `data_catalog.cata_id` | `legacy_object_mapping` + `catalog_entry.id` | 新主键重新生成；旧 ID 只作映射证据。 |
| `data_catalog.cata_title` | `catalog_entry.title` | 标题可保留，但展示文案按新产品口径清理。 |
| `data_catalog.org_code/org_name` | `owner_org_id` / `owner_org_snapshot` | 组织来源和 Governance 边界以 `dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准，本专题只保存调用时快照。 |
| `data_catalog.region_code/region_name` | `region_code` / 组织区划快照 | 用于发现、审批路由、统计，不作为权限权威。 |
| `data_catalog.shared_type/shared_way/share_condition` | `access_policy_json` | 映射共享方式、共享条件和不予共享原因。 |
| `data_catalog_column.name_cn/data_format/length` | `catalog_item` / `catalog_model_field` | 字段口径必须可被资源 schema 映射解释。 |
| `data_catalog_column.sensitive_level` | `catalog_item.policy_snapshot` | 敏感级别参与申请、脱敏、授权策略。 |
| `data_catalog_tag.tag_code/tag_name/tag_type` | `catalog_entry.tags_snapshot` / 搜索投影 | 标签服务发现与专题，不单独成为事实源。 |
| `data_apply.id/cata_id/resource_id` | `application_record` | 申请围绕目录和资源，不再按旧申请表分叉。 |
| `data_apply.apply_org_id/apply_org_name` | `application_record.applicant_org_snapshot` | 保存申请方快照。 |
| `data_apply_authrization.*` | `delivery_task.access_grant_snapshot` / `delivery_subscription` | 授权结果与续期要可回放。 |
| `rc_resource.id/res_name/res_type/cata_id` | `resource_asset` | 资源统一建模，旧类型映射为 `table/file/folder/api/url` 等。 |
| `rc_resource.share_type` | `resource_asset.access_policy_json` | 共享条件进入访问策略。 |
| `rc_resource_table.database_id/table_id/exchange_type` | `resource_channel_binding` | 数据源与表名只保存引用或脱敏快照，交换方式进入通道策略。 |
| `rc_resource_catalog_item_link.catalog_item_id/table_column_id` | `resource_schema_mapping` | 目录项和真实字段的核心绑定。 |
| `meta_baseinfo.meta_id/meta_name/model_id/version` | `resource_schema_snapshot` / evidence | 元数据对象作为资源 schema 证据。 |
| `meta_relation.source_meta_id/target_meta_id/relation_from` | `lineage_relation_projection` | 来源、目标、关系来源进入血缘投影。 |
| `meta_gather_task.job_id/cron_exp/file_ip/file_path` | `metadata_gather_evidence_projection` / external task ref | 调度细节和内部地址不明文进入核心模型；只保存任务引用和脱敏证据。 |
| `audit_todo_task.node_code/actor_code/status`、`resource_flow_log.check_status/check_note` | `approval_step` / `approval_decision` | metadata3 资源审核并入统一审批流；保留节点、角色、意见、时间，不保留旧流程后台。 |
| `rc_catalog_materialize.cata_id/datasource_id/res_id/table_name/db_type` | `resource_schema_mapping` evidence / external materialize receipt | 物化是目录项-资源字段绑定后的执行结果，不改变目录事实源。 |
| `db_database_node.*`、`database_manage_history.*` | external executor evidence | 连接地址、端口、路径、执行错误只存密钥引用或脱敏摘要，不能进入产品文案或审计明文。 |
| `graphdb_node/relation.*` | `lineage_relation_projection` / external graph ref | 图谱运行时外部化。 |
| 工单标题/描述/沟通记录 | `ops_issue_pattern_projection`（可选） | 只保留脱敏主题类型、故障模式、处置摘要和证据引用。 |

## 七、Capability 迁移设计

### 7.1 原生核心产品业务能力

核心能力只保留围绕目录、资源、申请、审批、交付、审计主旅程，跨项目高频、强状态、强责任、可回放的部分。

| 新 Capability | 目标聚合 | 旧能力来源 | 审计等级 | 说明 |
| --- | --- | --- | --- | --- |
| `catalog.group.query` | P2 / P7 projection | `/dsp/catalog/group/queryCatalogGroupList`、`queryCatalogGroupTree` | `read-trace` | 目录分组只服务发现、专题和权限解释，不成为核心事实源。 |
| `catalog.model.query` | `CatalogModel` | `/api/model/catalog-template-info` | `read-trace` | 查询目录/台账模板。 |
| `catalog.model.field.query` | `CatalogModel` | `/api/model/history-column-info`、字段导入模板 | `read-trace` | 查询字段口径、历史字段和模板字段。 |
| `catalog.entry.query` | `CatalogResourceAggregate` | `/dsp/catalog/register/getCatalog`、`/restapi/require/queryCatalogByPage` | `read-trace` | 目录详情与列表。 |
| `catalog.entry.create_draft` | `CatalogResourceAggregate` | 目录注册、导入、反向编目草稿 | `write-normal` | 仅建草稿，未发布前不可被默认申请。 |
| `catalog.entry.submit_review` | `ApprovalAggregate` | `/submitCatalogApprove` | `write-critical` | 提交目录审核。 |
| `catalog.entry.review` | `ApprovalAggregate` | `/catalogApprove/updateApproveCatalogStatus` | `write-critical` | 审核通过、驳回、退回。 |
| `catalog.entry.publish` | `CatalogResourceAggregate` + `AuditAggregate` | `/topublish/catalogPublish`、发布列表 | `write-critical` | 发布目录版本并触发投影生成。 |
| `catalog.entry.withdraw` | `CatalogResourceAggregate` | 目录撤销、取消、删除 | `write-critical` | 受监管领域不物理删除。 |
| `catalog.resource.bind` | `CatalogResourceAggregate` | `ResourcePushController`、`rc_resource_catalog_item_link` | `write-critical` | 绑定目录项与资源字段，必须保留证据。 |
| `catalog.share_zone.query` | P7 projection | `share_zone_catalog_link`、`catalog_share_group` | `read-trace` | 查询共享专区专题包。 |
| `resource.asset.query` | `CatalogResourceAggregate` | metadata `/manage/list`、`/table/view` | `read-trace` | 资源发现、详情、schema 证据。 |
| `resource.asset.submit_review` | `ApprovalAggregate` | metadata `ReviewController` | `write-critical` | 资源发布前审核。 |
| `resource.asset.review` | `ApprovalAggregate` | `/review/passResource`、`/review/rejectResource` | `write-critical` | 资源审核。 |
| `resource.asset.publish` | `CatalogResourceAggregate` | `PublishController` | `write-critical` | 资源进入可发现/可申请状态。 |
| `application.resource.submit` | `ApplicationApprovalAggregate` | `data_apply`、资源申请门户 | `write-critical` | 提交资源申请。 |
| `application.resource.review` | `ApplicationApprovalAggregate` | `data_apply_course`、授权审批 | `write-critical` | 审批、补件、驳回、通过。 |
| `delivery.access.grant` | `DeliveryAggregate` | `data_apply_authrization` | `write-critical` | 授权、续期、频次变更。 |
| `metadata.schema.query` | schema projection | `/table/queryColumnList`、`meta_baseinfo` | `read-trace` | 查询表字段、中文注释、敏感级别。 |
| `metadata.catalog_item.query` | schema / mapping projection | metadata `/catalog/queryItemList`、`rc_resource_catalog_item_link` | `read-trace` | metadata3 对目录项的反向依赖只作为绑定证据。 |
| `metadata.lineage.query` | lineage projection | `meta_relation`、graphdb、`/metadata/relation/*` | `read-trace` | 查询血缘和影响分析。 |
| `ops.catalog.statistics.query` | P6 projection | catalog 统计 REST API | `read-trace` | 目录、资源、部门、区划统计。 |
| `ops.catalog.quality.query` | quality projection | `catalog_quality_task_result` | `read-trace` | 质量结果查询与解释。 |

### 7.2 可通过 ANP / 外部 Capability 外化的能力

外化能力应声明输入输出 contract、审计等级、租户策略、失败回写方式和可观察证据；不得绕过核心 Capability 直接写 canonical 状态。

| 外化能力 | 外化形态 | 边界 |
| --- | --- | --- |
| 元数据采集任务执行 | ANP 执行器 / metadata adapter | 可读外部数据源、生成 schema 快照和证据；不得直接发布资源。 |
| 数据源连通测试 | 外部诊断 Capability | 返回脱敏连通性结果和错误摘要；密钥只走密钥引用。 |
| 建库建表 / 结构调整 | 高风险外部执行器 | 必须由核心审批授权后执行；执行结果回写 `delivery_receipt` / evidence。 |
| 目录物化 / 资源物化 | ANP 执行器 | 只执行已确认的目录项-字段映射；`checkColumns`、`submit`、`adjustStructure`、`adjustSubmit` 等动作必须由核心审批授权并回写回执，不成为事实源。 |
| 反向编目 / 智能编目 | 外部编目 Capability | 只生成 catalog draft 和 mapping suggestion；`getDataCenterTree`、`getTableForCatalogList` 证明它依赖数据中心和表结构，但人工确认后才能发布。 |
| 目录质量检测 | 外部质量检测包 | 输出质量证据，不直接改目录状态。 |
| 血缘解析 / 图谱构建 | 外部 lineage adapter | 输出 lineage projection，不反向驱动业务流程。 |
| 级联 / 上下级同步 | 外部 exchange adapter | 按 canonical 事件和投影同步，不创建第二套目录事实源。 |
| 共享分组维护与共享专区授权 | P7 投影配置 / 外部治理包 | `sharegroup` 的新增、授权、挂接动作只影响专题可见性和策略解释，不创建第二套权限事实源。 |
| 短信 / 通知 / 工单联动 | 外部通知/工单 adapter | 只发送通知或同步摘要，不承接审批事实。 |
| 漏洞修补 / 中间件适配 | 运维安全执行器 | 处理环境问题，不进入产品主旅程。 |
| 客户专属字段展示 | 配置 / 投影 / 外部包 | 后端不 per-tenant fork；字段先进入模型或投影配置。 |

### 7.3 Drop：不迁入

- 旧登录、门户首页、菜单、收藏、评分、评论等门户岛能力。
- 目录后台、元数据后台的页面层级和 controller URL。
- 完整消息中心、监控工单系统、Zabbix/xxl-job 管理台。
- graphdb 运行时管理页面。
- 旧导入导出 Excel 模板页面作为一等产品能力；模板字段语义只进入 `catalog_model_field`。
- 旧流程后台、待办表和审核日志页面；审批事实统一进入 `approval_case` 与审计回放。
- 明文数据库地址、文件服务器地址、联系人、电话、内部附件链接。
- 为单个客户临时新增的后端分支逻辑。

## 八、状态映射规则

### 8.1 目录生命周期

| legacy 语义 | `catalog_entry.status` | `approval_case.current_status` | 说明 |
| --- | --- | --- | --- |
| 新建 / 导入草稿 / 反向编目草稿 | `draft` |  | 可编辑，不默认可申请。 |
| 提交审核 | `pending_review` | `pending_decision` | 对应 `catalog.entry.submit_review`。 |
| 审核驳回 / 退回修改 | `draft` 或 `rejected` | `rejected` | 保留审批意见。 |
| 审核通过待发布 | `approved_pending_publish` | `approved` | 仍不可等同 active。 |
| 已发布 | `active` | `approved` | 可被发现、申请、挂接共享专区。 |
| 发布后变更待审 | `pending_review` | `pending_decision` | 线上版本保持 active，新版本待审。 |
| 撤销 / 下线 / 删除 | `revoked` 或 `retired` | `approved` | 监管场景不物理删除。 |

### 8.2 资源生命周期

| legacy 语义 | `resource_asset.status` | `approval_case.current_status` | 说明 |
| --- | --- | --- | --- |
| 元数据采集到候选资源 | `discovered` |  | 仅作证据，不可直接申请。 |
| 资源注册草稿 | `draft` |  | 提供方可编辑。 |
| 资源提交审核 | `pending_review` | `pending_decision` | 对应 `resource.asset.submit_review`。 |
| 审核通过待发布 | `approved_pending_publish` | `approved` | 等待发布或挂接。 |
| 已发布 / 已开放 | `active` | `approved` | 可被发现和申请。 |
| 结构变更中 | `changing` | `pending_decision`（高风险时） | 保持上一 active 版本可回放。 |
| 停用 / 撤销 | `suspended` / `revoked` | `approved` | 保留历史授权和审计。 |

### 8.3 申请授权生命周期

| legacy 语义 | `application_record.status` | `delivery_task.status` | 说明 |
| --- | --- | --- | --- |
| 填写申请 | `draft` |  | 可编辑。 |
| 提交申请 | `submitted` |  | 进入审批。 |
| 受理 / 合规检查 | `under_review` |  | 可拆为审批步骤，不新增系统。 |
| 审批通过 | `approved` | `pending` | 等待授权或交付。 |
| 授权生效 | `effective` | `succeeded` | 写授权快照和回执。 |
| 频次变更 / 续期 | `change_pending` | `pending` | 高风险策略需审批。 |
| 驳回 / 撤回 / 过期 | `rejected/withdrawn/expired` | `cancelled/expired` | 保留原因与审计。 |

## 九、adapter 迁移规则

### 9.1 输入源

| adapter source | 读取对象 | 输出 |
| --- | --- | --- |
| `dsp_catalog_catalog` | `data_catalog`、`data_catalog_column`、`data_catalog_tag`、版本表 | `catalog_entry`、`catalog_entry_version`、`catalog_item`、`legacy_object_mapping` |
| `dsp_catalog_apply` | `data_apply*`、授权、续期、审批过程 | `application_record`、`approval_case`、`delivery_task`、`audit_event` |
| `dsp_catalog_share_zone` | `share_zone_catalog_link`、`catalog_share_group`、权限表 | P7 共享专区 projection、策略草案 |
| `dsp_catalog_quality` | `catalog_quality_task*` | `quality_evidence_projection` |
| `dsp_metadata_resource` | `rc_resource*` | `resource_asset`、`resource_channel_binding` |
| `dsp_metadata_schema` | `meta_baseinfo*`、表字段、数据源、中文注释 | `resource_schema_snapshot`、`metadata_gather_evidence_projection` |
| `dsp_metadata_mapping` | `rc_resource_catalog_item_link` | `resource_schema_mapping` |
| `dsp_metadata_lineage` | `meta_relation*`、graphdb 表 | `lineage_relation_projection`、`lineage_column_projection` |
| `dsp_metadata_gather` | `meta_gather_task*`、job 日志 | 采集 evidence + 外部执行器任务引用 |
| `work_order_pattern` | 脱敏工单主题、故障模式、处理摘要 | P6 运营问题模式 projection（可选） |

### 9.2 输出纪律

- adapter 只读旧系统，不回写旧 catalog、metadata、数据库、文件服务器或调度中心。
- 每个旧对象写入 `legacy_object_mapping`；冲突进入 `mapping_status='conflicted'`，不得自动覆盖。
- 任何 canonical 写入必须经 command / Capability / policy / audit。
- 密钥、内部 IP、数据库连接串、文件路径、联系人、电话、附件链接不得明文进入文档、日志或 canonical 字段。
- 统计、质量、血缘、采集状态都是可重算 projection；业务状态不得由 projection 反推。
- 外化执行器只能回写受控回执、证据引用和脱敏错误摘要。

## 十、落地波次

### Wave 0：目录 / 资源 / 元数据证据读面

目标：先让目录、资源、字段、挂接、统计和质量问题可以被统一看见。

- 建立 catalog / resource / schema / mapping 的只读 adapter。
- 生成 `catalog_entry`、`catalog_item`、`resource_asset`、`resource_channel_binding` 草案与 `legacy_object_mapping`。
- 建立 `resource_schema_mapping` 草案，专门承接目录项-表字段绑定。
- 建立目录/资源统计 projection，对齐旧高频统计接口语义。
- P6 能解释目录发布、门户投影、资源挂接、字段缺失问题卡在哪一步。

### Wave 1：目录发布与资源申请主旅程

目标：目录与资源进入发现、申请、审批、授权、交付链路。

- 目录注册、提交审核、审批、发布、撤销能力化。
- 资源注册、审核、发布能力化。
- `data_apply*` 迁入 `application_record`、`approval_case`、`delivery_task`。
- 授权、续期、频次变更进入统一审批和交付回执。
- P2 / P3 / P5 能完成目录发现、资源申请、提供方治理。

### Wave 2：元数据采集、质量、血缘证据化

目标：让资源可信度、字段口径、血缘和质量可以解释，但不膨胀成元数据后台。

- 元数据采集任务外化为 ANP 执行器。
- 采集结果进入 `metadata_gather_evidence_projection`。
- 血缘进入 lineage projection。
- 目录质量检测进入 quality projection。
- 反向编目 / 智能编目只生成草稿和建议，人工确认后才写核心状态。

### Wave 3：共享专区、级联和长尾外部化

目标：保留共享专区产品价值，外化长尾项目化能力。

- `share_zone_catalog_link` 和 `catalog_share_group` 进入 P7 主题投影。
- 垂管、上下级同步、国家/省级通道通过外部 adapter 接入。
- 建库建表、物化、GBase/TongWeb 等项目化适配通过 ANP 包承接。
- 通知、短信、工单、监控、安全修补全部走外部能力包，不进主仓核心模型。

## 十一、验收标准

1. 任一 catalog3 / metadata3 迁移对象必须能回指 `legacy_object_mapping`。
2. 任一目录、资源、申请、授权、发布写动作必须经 Capability、policy、audit，不允许页面、adapter 或外化执行器直接写状态。
3. 目录和元数据在 WebUI 中首先表现为可发现、可申请、可交付、可追责的资源能力，而不是两个后台系统。
4. 目录项与资源字段的绑定必须可解释；否则不能算完成资源挂接迁移。
5. 统计、质量、血缘、采集状态必须标注来源和生成时间，且只能作为 projection。
6. 工单素材只允许沉淀脱敏后的主题类型、故障模式和处置摘要，不得写入个人、组织、内部地址、附件链接或密钥原文。
7. 旧 URL 不作为兼容契约；新契约以 Capability slug 与统一 contract 为准。
8. ANP / 外部 Capability 必须声明输入输出 contract、审计等级、租户策略和失败回写方式。
9. 外化能力不得绕过核心状态机、审计总线和策略裁决。
10. 如果某项能力不能服务 J1-J4 / S1 / S2，也不能解释真实工单中的高频问题，默认不进核心模型。

## 十二、源码与事实证据索引

| 结论 | 证据 |
| --- | --- |
| catalog3 外部使用高频集中在统计、目录详情、模板、分组、资源挂接 | `old/old_codes_analyse/dsp-catalog3-apis.md` |
| metadata3 外部使用高频集中在资源列表、审核日志、表结构、数据源、采集任务 | `old/old_codes_analyse/dsp-metadata3-apis.md` |
| 目录注册、审批、发布是强状态写动作，且旧版本逻辑并未形成干净独立子域 | `dsp-catalog-service/src/main/java/com/inspur/dsp/catalog/service/impl/StandardCatalogServiceImpl.java` 承接提交、审批、撤销、发布后变更；`StandardCatalogVersionServiceImpl.java` 基本为空。 |
| 目录分组、共享分组、反向编目和质量检测是投影/执行器语义，不是新事实源 | `CatalogGroupServiceImpl.java`、`CatalogShareGroupServiceImpl.java`、`CatalogCompileServiceImpl.java`、`CatalogQualityTaskServiceImpl.java`。 |
| 目录和资源挂接是 catalog3 核心链路，且会携带目录项-字段映射 | `dsp-catalog-service/src/main/java/com/inspur/dsp/catalog/service/impl/PushOpenCatalogServiceImpl.java`，推送开放目录时读取目录关联资源并组装 `catalogItemColumnLinks`。 |
| 目录模板字段会触发动态扩展表创建/调整，证明字段口径承重而建表副作用应外化 | `dsp-catalog-service/src/main/java/com/inspur/dsp/catalog/service/impl/catalogModel/CatalogModelServiceImpl.java`。 |
| catalog3 对外 REST 主要服务统计、目录查询、申请查询 | `dsp-catalog-console/src/main/java/com/inspur/dsp/catalog/console/api/OpenApiController.java` |
| metadata3 资源审核、发布、撤销、事件发布和链路回写是统一资源治理逻辑 | `dsp-metadata-service/src/main/java/com/inspur/dsp/metaresource/service/impl/resource/ResourceReviewServiceImpl.java`。 |
| metadata3 资源管理证明资源删除会清理目录项映射和物化记录 | `dsp-metadata-service/src/main/java/com/inspur/dsp/metaresource/service/impl/resource/ResourceManageServiceImpl.java`。 |
| metadata3 建表、连通性和元数据同步是高副作用执行链 | `DatabaseManageServiceImpl.java` 调用 `createTable` 后触发 `createTableMetaDate`。 |
| metadata3 元数据采集会拉取 schema、列、索引、外键并生成结构变化历史 | `MetaBaseinfoServiceImpl.java`。 |
| metadata3 结构数据证明资源、元数据、字段映射、血缘、采集任务是承重对象 | `old/12-datastructure/dsp_metaresource.xml` 中 `rc_resource*`、`rc_resource_catalog_item_link`、`meta_baseinfo`、`meta_relation*`、`meta_gather_task*` |
| metadata3 代码证明目录物化和字段映射是执行器语义，不是独立事实源 | `CatalogMaterialController.java`、`CatalogMaterialServiceImpl.java`、`RcCatalogMaterialize.java`、`CatalogItemLinkServiceImpl.java`、`RcResourceCatalogItemLink.java`。 |
| metadata3 代码证明血缘和目录项查询是解释性投影 | `MetaRelationController.java`、`TableColumnRelationController.java`、`CatalogController.java` |
| metadata3 migration 证明资源字段、目录项绑定、标准、脱敏和开放状态长期演进 | `dsp-metadata-console/src/main/resources/db/migration/V1__base.sql`、`V202106151705__rc_resource_catalog_item_link_add_column.sql`、`V202111050949__resource_column_add_data_standard.sql`、`V20241025100000__rc_resource_change.sql`、`V20251203095000__rc_resource_add_open.sql` |
| 工单事实证明目录展示、发布、授权、资源申请、挂接、元数据、漏洞和物化是主要真实问题 | `old/工单导出-列缩减.xlsx` 的 `工单导出` sheet |

## 十三、反上帝视角自检

- 如果用户问“目录发布了为什么门户看不到”，本文能回答：发布状态、版本、投影状态、审计回执分别在哪里，而不是让用户去找门户补丁。
- 如果用户问“申请通过后为什么没有授权”，本文能回答：申请、审批、授权、续期分别进入哪条状态机和回执链。
- 如果用户问“这个目录项到底对应哪张表哪个字段”，本文能回答：`resource_schema_mapping` 是核心证据，必须连接目录项、资源、通道和字段。
- 如果用户问“元数据采集失败是否影响资源状态”，本文能回答：采集是 evidence projection；只有经审批的资源状态变更才能改变业务状态。
- 如果客户要求新增地区专属字段，本文能回答：先进入模型字段或投影配置，不允许 per-tenant 后端 fork。
- 如果现场要求建库建表或物化，本文能回答：这是外部执行器，必须由核心 Capability 授权并回写回执。
- 如果旧表里有 `audit_todo_task`、`resource_flow_log`、`database_manage_history`，本文不会把它们升级成新后台；它们只证明审批、执行和故障必须可追责。
- 如果旧表里有数据库节点、文件路径、端口、联系人或电话，本文不会把这些明文写进 canonical model；它们只允许成为密钥引用、脱敏证据或外部执行器上下文。

结论：本方案经得起旧 API 调用量、旧 XML 表结构和真实工单三类事实推敲；它迁移的是承重语义，不是旧平台形状。
