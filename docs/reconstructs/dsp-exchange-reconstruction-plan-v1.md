# dsp-require / dsp-supply / dsp-exchange 相关模块重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-require`（目标版本 `v4.2.13`）、`old/old_codes/dsp-supply`（目标版本 `v4.9.13`）、`old/old_codes/dsp-exchange`（目标 tag `4.3.23`）、外部调用分析 `old/old_codes_analyse/dsp-exchange-apis.md`、旧结构数据 `old/12-datastructure` 与脱敏工单数据 `old/工单导出-列缩减.xlsx`。
> 结论：zw-brain 是全新 AI 原生项目，不兼容旧接口、旧菜单、旧库表，也不把 require / supply / exchange 原样迁成三个新子系统；本方案只吸收需求形成、申请审批、授权续期、交换交付、订阅直达、运行回执等承重业务语义，重建为围绕主旅程、统一 Capability、可审计、可外化扩展的能力面。
> 单一事实源：本文是 dsp-require / dsp-supply / dsp-exchange 专题映射、字段落位、能力迁移、工单解释和 ANP 外化边界的单一事实源；`docs/approved/*` 只保留 canonical 通用模型与本文引用。
>
> 事实审计口径：接口条目数和调用量只来自 `old/old_codes_analyse/dsp-exchange-apis.md`；旧表和字段只来自 `old/12-datastructure/*.xml`、旧 SQL、旧实体注解；工单统计只来自 `old/工单导出-列缩减.xlsx` 的关键词命中。本文的“应进入 / 不应进入 / 必须经 Capability”是基于 approved 约束和这些事实推出的目标架构判断，不等同于旧系统已经这样实现。

## 一、设计原则

### 1.1 Jobs：从“三个后台系统”改成“要数、批数、交付、追责”

旧 `dsp-require` 的表面形态是供需梳理、原始需求、需求拆分、任务、审核、统计；旧 `dsp-supply` 的表面形态是资源申请、资源审核、授权、续期、门户待办；旧 `dsp-exchange` 的表面形态是交换节点、数据源、管道、库表任务、订阅、执行监控和可视化统计。

zw-brain 不继承这些模块名，也不复刻它们的页面层级。它们在新系统中只保留五类用户可感知价值：

1. 要数方能把业务问题表达成清晰的数据需求，并看到是否已有目录、资源或模板可复用。
2. 管数方能围绕申请和需求做受理、审批、补正、授权、续期，不在多个后台间跳转。
3. 交付方能把授权后的资源稳定交付为交换任务、订阅、直达或下载，并留下可解释回执。
4. 监管方能从申请、审批、授权、交付、异常、统计追溯责任链。
5. 低频、基础设施耦合强、客户现场差异大的动作通过 ANP / 外部 Capability 包执行，不占用主产品心智。

### 1.2 OPC：单一事实源，不为供需和交换开第二套平台

- 需求、申请、审批、授权、交付继续进入 `brain_core` 的 canonical model，不建立并列的“供需中心”和“交换中心”。
- require / supply / exchange 专属映射、投影字段、迁移规则和能力边界以本文为单一事实源；approved 数据模型只保留通用结构与本文引用。
- 旧库、旧 API、旧 Controller、Kettle、NiFi、xxl-job 和 Spring Batch 只作为只读 adapter 输入、执行器线索或外部化候选，不成为新业务写入口。
- 页面、REST、CLI、MCP、A2A 都从统一 Capability contract 投影，不按旧 controller URL 兼容。
- 工单只作为脱敏后的真实问题证据，不把旧工单系统、客户环境、人员信息、IP、账号或连接串迁入 canonical model。

### 1.3 合并分析 require / supply / exchange 的原因

这三个旧仓库在技术上分离，在用户旅程上却是同一条链：

1. `dsp-require` 负责把“我要什么数据、为了什么业务、哪些材料可被数据替代”形成可处理需求。
2. `dsp-supply` 负责把“申请、审批、授权、续期、撤销”变成责任动作。
3. `dsp-exchange` 负责把“已授权的数据资源”转成可执行的库表交换、文件下载、订阅或直达任务。
4. 结构数据中 `data_require_resource`、`data_apply`、`data_apply_authrization`、`resource_applied`、`exchange_job.apply_id/resource_id`、`dc_subscribe`、`subscribe_job` 显示需求、资源、申请、授权和交换/订阅执行存在跨仓关联；其中 `dc_subscribe` 来自 `dsp_connect.xml`，`subscribe_job` 来自 `dsp-exchange` 实体与 Kingbase SQL，而不是 `init_sql/dsp_exchange.sql`。
5. 工单中“申请审核流程要拆分”“申请省里面的资源无法选择使用部门”“数据交换问题排查”“服务调用失败”“共享交换工作台整合”等问题跨越 require / supply / exchange 边界。

因此，新系统不应按旧仓库拆三个事实源，而应按 `ApplicationApprovalAggregate`、`DeliveryAggregate` 与主旅程重建一套事实源。

## 二、证据清单

### 2.0 事实、推断与待验证边界

| 类型 | 本文如何使用 | 例子 |
| --- | --- | --- |
| 直接事实 | 可从旧接口分析、XML、SQL、实体或工单文件直接核对 | 接口调用量、旧表名、字段名、工单关键词命中、旧实体注解 |
| 架构推断 | 由直接事实叠加 approved 约束推出，作为 zw-brain 目标设计 | 旧申请、授权、交换执行应收敛到 `ApplicationApprovalAggregate` / `DeliveryAggregate` |
| 实施待验证 | 需要后续真实数据迁移样本、运行日志或业务方确认 | 旧状态码到新状态机的完整映射、字段级必填规则、各地项目是否有二开表 |

凡直接事实不足以唯一推出的结论，本文只作为目标设计约束，不把它写成旧系统事实。

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture-v4-gpt55.md` | 产品围绕少数高频旅程；人和 Agent 共用同一 Capability；新增能力默认外部生产、平台注册；合规可证迹内建。 |
| `docs/approved/zw-brain-data-model-v4-gpt55.md` | 模型围绕旅程与审计组织，不围绕 legacy 表名组织；申请、审批、交付、订阅必须保留显式状态机。 |
| `docs/approved/zw-brain-golden-path-r1-r3-r5-v1.md` | 首条黄金链路要把上级需求、资源/模板复用、基层补差、审核汇总和回流共享资源池打通。 |
| `docs/approved/zw-brain-user-roles-and-journeys-v1.md` | 用户不是抽象管理员，而是要数的人、管数的人、填数的人、审数的人、查责的人；供需和交换能力必须服务这些岗位。 |
| `docs/approved/research-yibiaotong-zw-brain-v4.md` | zw-brain 必须承接上级交换和基层填报链路；供需/交换不是孤立后台，而是上下级协同和直达交付的中枢。 |

### 2.2 外部使用证据

`dsp-require` 去重后 85 个接口，三项目合计 611,422 次调用。头部调用集中在：

| 旧能力 / 接口簇 | 调用特征 | 新系统解释 |
| --- | ---: | --- |
| `/restapi/countRequiresNumber` | 519,627 | 需求数量统计是 P1 / P6 的运营投影，不是新事实源。 |
| `/dsp/require/task/querytasks` | 937 | 需求任务是申请/需求处理轨迹，进入 `application_record`、`approval_case` 与待办投影。 |
| `/dsp/require/common/queryRequireByPage` | 225 | 需求列表应围绕用户“要什么、谁处理、是否响应”组织。 |
| `/dsp/require/inventory/requireApprove` | 91 | 需求审核必须进入统一审批状态机和审计链。 |
| `/restapi/addOriginalRequire` | 28 | 外部提交需求只允许经 Capability 接入，不保留旧开放 URL。 |
| `/restapi/getCatalogRequireMap` | 16 | 需求与目录资源映射是发现、申请和复用的核心证据。 |

`dsp-supply` 去重后 72 个接口，三项目合计 55,015 次调用。头部调用集中在：

| 旧能力 / 接口簇 | 调用特征 | 新系统解释 |
| --- | ---: | --- |
| `/home/apply/resource/query` | 3,797 | 资源申请列表进入 P3 申请/审批/跟踪，不保留 supply 门户。 |
| `/home/audit/resource/todo` | 1,487 | 审批待办进入统一待办投影，事实源仍是 `approval_case`。 |
| `/restapi/getcatalognew` | 1,147 | 目录发现回到 `catalog_entry` / `resource_asset`。 |
| `/restapi/getnewresource` | 821 | 新资源提醒是投影，不是新的资源状态。 |
| `/restapi/applyamountbysystem` | 452 | 申请量统计进入可重算运营投影。 |
| `/apply/renewal/queryApplyRenewal` | 60 | 授权续期是强责任链路，必须进入申请、审批、交付订阅状态机。 |
| `/dsp/resource/authrization/approve/*` | 33 / 15 / 14 | 授权审批不能散落在 supply 专属流程岛。 |

`dsp-exchange` 去重后 118 个接口，三项目合计 168,817 次调用。头部调用集中在：

| 旧能力 / 接口簇 | 调用特征 | 新系统解释 |
| --- | ---: | --- |
| `/cloud/wbService/visual/resourceStatisticsInfo` | 120,174 | 交换可视化和资源统计是 P6 / Dashboard 投影，不是交换事实源。 |
| `/dsp/exchange/custom/getCustomJobList` | 10,185 | 交换任务列表进入 `delivery_task` / `delivery_subscription` 的读模型。 |
| `/dsp/exchange/custom/getNifiJobHistory` | 4,039 | NiFi 历史是外部执行器 evidence，不能反向驱动业务状态。 |
| `/dsp/exchange/custom/getAllPipelines` | 1,862 | 管道是外部执行器配置引用，不在核心模型里复造调度平台。 |
| `/dsp/exchange/database/getDBList` | 690 | 数据源管理是外部基础设施能力；canonical 只保存引用和脱敏快照。 |
| `/dsp/exchange/custom/startJob`、`publishJob`、`offlineJob`、`stopJob` | 430 / 409 / 214 / 24 | 启停发布等写动作必须经 `delivery.exchange.*` Capability 与审计。 |
| `/dsp/subscribe/account/*`、`/dsp/exchange/subscribeJobDefine` | 144 / 76 / 140 | 订阅和直达进入 `delivery_subscription`。 |
| `/api/1.0/push-resource`、`/api/addResourceApplied`、`/api/dealAuthorization` | 119 / 33 / 1 | 对外接入只作为 adapter / Capability 入口，不兼容旧 URL。 |

## 三、结构数据证据

### 3.1 `dsp_require.xml`

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `data_original_require` | 原始需求、需求内容、需求部门、业务任务 | `application_record.intent_snapshot`，表示用户原始诉求和业务上下文。 |
| `data_original_require_column` | 原始需求数据项 | `application_record.requested_items_snapshot`，不单独长成数据项事实源。 |
| `data_original_require_resource` | 原始需求关联资源/目录 | `application_record.related_resource_snapshot` + `legacy_object_mapping`。 |
| `data_require` | 拆分后的数据需求、共享方式、更新频率、接口要求 | 需求处理后的结构化申请意图，进入 `application_record`；共享方式变成交付偏好。 |
| `data_require_column` | 数据需求信息项、检索项 | 申请项快照或目录字段引用，用于审批和交付范围确认。 |
| `data_require_resource` | 数据需求关联资源 | 连接需求、资源、目录和后续交付任务的 evidence。 |
| `data_require_approve` / `data_original_require_approve` | 需求审核意见、驳回原因、处理人 | `approval_case`、`approval_step`、`approval_decision`。 |
| `data_task` / `data_subtask` / `data_task_process` | 主任务、子任务、会议/处理过程 | 待办投影、审批过程和协同证据；不复造任务管理系统。 |
| `data_require_review` | 需求方、平台方、提供方评价 | 交付后评价 evidence；可进入 P6 满意度投影，不推进核心状态。 |
| `data_*_statistics` | 组织、资源、需求统计 | 可重算运营投影。 |
| `data_message` | 系统消息和告警 | `delivery_notice_projection` 或外部通知，不作为业务事实源。 |

### 3.2 `dsp_catalog.xml` / `dsp_service.xml` / `dsp_metaresource.xml`

这些结构文件显示供需和交换离不开目录、资源、服务、元数据，但专题细节分别以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 与 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` 为准。本文只记录与供需/交换链路直接相关的约束：

| 结构来源 | 关键旧表 / 字段 | 对本方案的约束 |
| --- | --- | --- |
| `dsp_catalog.xml` | `data_apply`、`data_apply_item`、`data_apply_course`、`data_apply_authrization`、`data_apply_authrization_approve`、`data_apply_renewal` | 申请、申请项、审批过程、授权、续期必须进入 `application_record`、`approval_case`、`delivery_task` 和审计回执。 |
| `dsp_catalog.xml` | `data_resource_statistics`、`data_resource_general_statistics`、`table_exchange_detail_num` | 资源、申请、交换统计是 read model，可重算，不反向驱动状态。 |
| `dsp_metaresource.xml` | `rc_resource`、`rc_resource_table`、`rc_resource_catalog_item_link` | 资源、库表和目录信息项挂接进入 `resource_asset`、`resource_channel_binding` 与 schema evidence。 |
| `dsp_metaresource.xml` | `db_meta_database`、`db_meta_table`、`db_meta_column`、`database_manage_history` | 数据源、库表、建表、字段结构是外部执行器证据；内部地址、端口、连接路径不得明文进入 canonical model。 |
| `dsp_service.xml` | `api_service_app`、`api_service_proxy`、`api_service_times` | API 授权、路由、频控和统计分别进入授权快照、通道策略与运营投影。 |
| `dsp_monitor.xml` | `matter_handle`、`warning_work_order_rules`、拨测和告警结果 | 告警与工单只作为 P6 运营投影和外部诊断 Capability 输入，不复制监控工单系统。 |
| `dsp_block.xml` | 申请、目录、资源、调用日志上链表 | 上链仍按 `anchor_outbox` + `audit_receipt` 处理；外链结果不反向驱动业务状态。 |

### 3.3 `dsp_connect.xml`

`dsp_connect.xml` 显示上下级对接、供需下发、资源申请、受理审核和资源订阅在旧平台已有独立结构：

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `dc_catalog` / `dc_catalog_item` | 上级目录与信息项 | 上级目录 adapter evidence；canonical 仍是 `catalog_entry` / `catalog_item`。 |
| `dc_require` / `dc_require_column` / `dc_require_resource` | 下发的需求、供需信息项、供需关联资源/目录 | 上级需求进入 `application_record`，关联资源进入申请/交付 evidence。 |
| `dc_resource_apply_info` / `dc_resource_apply_info_province` | 资源申请、省级资源申请 | `application_record` 与申请来源 evidence。 |
| `dc_resource_apply_audit` / `dc_resource_apply_audit_province` / `dc_resource_apply_accept_audit` | 审核、受理审核 | `approval_case`、`approval_step`、`approval_decision`。 |
| `dc_subscribe` / `dc_subscribe_table` / `dc_subscribe_folder` | 资源订阅、库表订阅、文件夹订阅 | `delivery_subscription`。 |
| `batch_job_execution*` | 同步 Job 执行历史 | `delivery_attempt` 或外部执行器 evidence。 |

### 3.4 `dsp_exchange` SQL 与实体

| 旧表 / 实体 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `exchange_job` | 库表交换任务、资源申请、目录资源、调度、发布状态、运行状态 | `delivery_task` + `delivery_subscription`；调度和执行器路径只存引用。 |
| `exchange_trans` | 源表、目标表、字段映射、增量参数、清表策略 | `delivery_task.execution_plan_snapshot`；高风险写入策略必须经审批确认。 |
| `data_piplines` / `exchange_pipelines*` | 通道、管道、管道订阅 | 外部执行器配置引用 + `delivery_subscription.pipeline_ref`。 |
| `meta_host` / `meta_datasource` / `meta_table` / `meta_table_column` | 主机、数据源、库表、字段 | 外部数据源投影和 schema evidence；敏感连接信息不得落 canonical 明文。 |
| `resource_applied` / `resource_status` | 交换侧资源申请与状态 | 旧交换侧申请只作为 `application_record` / `delivery_task` 的 legacy evidence。 |
| `subscribe_job` / `subscribe_detail*` / `subscribe_trans` | 订阅任务、订阅明细、订阅转换 | `delivery_subscription` + `delivery_attempt`；来源为 `dsp-exchange` 实体与 Kingbase SQL。 |
| `nifi_job_history` / `nifi_job_alarm_info` / `job_warning_info` | 执行历史和告警 | 执行器 evidence 与 P6 投影，不推进业务状态。 |
| `components_install*` / `exchange_executor*` | 组件安装、执行器步骤 | ANP 外部执行器能力，不进入主产品事实源。 |
| `stats_exchange` / `stats_resource` / `exchange_table_statisc` | 交换统计 | 可重算运营投影。 |
| `resource_file_download_log` | 文件下载使用日志 | 下载回执或审计事件输入，按敏感级别脱敏保存。 |

## 四、真实工单事实

### 4.1 工单命中概况

`old/工单导出-列缩减.xlsx` 的 `工单导出` sheet 共 791 条记录，列包括 `工单ID`、`工单标题`、`工单状态`、`工单升级状态`、`问题描述`、`处理描述`、`沟通记录`、`问题级别历史`。下表是全行文本关键词命中，不是互斥分类，也不代表工单根因；它只能说明这些词汇在真实问题描述中出现频率高，后续产品判断还必须回到具体样本。

| 主题关键词 | 命中条数 | 对本方案的启发 |
| --- | ---: | --- |
| 服务 | 715 | API / 数据服务仍是用户最常感知的资源形态，必须能落到统一资源和授权链路。 |
| 共享 | 655 | 共享不是门户栏目，而是贯穿发现、申请、审批、授权、交付的业务结果。 |
| 需求 | 540 | 真实问题不是“需求系统页面”，而是需求能否形成、受理、响应和交付。 |
| 资源 | 439 | 资源发现、挂接、申请和交付是主链路。 |
| 申请 | 244 | 申请、审批、受理、授权必须是统一状态机。 |
| 交换 | 179 | 交换问题多表现为任务、库表、接口、统计和排障。 |
| 接口 | 157 | API 服务和交换接口都需要契约化、审计化。 |
| 报错 | 132 | 现场问题需要可解释 evidence，而不是只给错误日志。 |
| 任务 | 92 | 任务语义应收敛为待办、审批过程、交付任务或执行尝试。 |
| 审批 | 72 | 审批轨迹必须可回放。 |
| 授权 | 60 | 授权和续期是强责任链路。 |
| 漏洞 | 45 | 安全漏洞和组件运维应外化到安全/运维执行器。 |
| 库表 | 40 | 库表交换和建表是高风险执行动作，需要审批、回执和脱敏引用。 |
| 订阅 | 9 | 订阅出现次数低，但属于长周期交付事实，需显式建模。 |

状态分布：已完成 698、挂起 63、处理中 21、升级中 7、撤销 2。问题级别历史中 `中心需求D3` 326、`请求R4` 137、`中心需求D2` 76、`中心需求D1` 51。这个分布只能支撑一个保守结论：真实问题大量来自需求请求和现场处理，不足以证明某个旧模块应原样保留；是否进入核心仍要看它能否服务发现、申请、审批、授权、交付和追责闭环。

### 4.2 工单样本对设计的约束

| 工单现象 | 新系统必须回答的问题 | 本方案落点 |
| --- | --- | --- |
| “申请审核系统中的受理环节需拆分为两步流程” | 受理、审核、授权是否是可配置且可审计的责任步骤？ | `approval_step` / `approval_decision`，通过 Capability 推进，不按页面硬编码。 |
| “一体化平台，申请省里面的资源，无法选择使用部门” | 上级资源申请时，申请方组织和使用部门是否有清晰快照与路由？ | `application_record.applicant_org_snapshot`、`approval_case.routing_snapshot`。 |
| “数据交换系统交换数据问题排查” | 交换失败时能否定位是授权、计划、执行器、源库、目标库还是字段映射问题？ | `delivery_task`、`delivery_attempt`、`delivery_receipt`、执行器 evidence。 |
| “某个数据服务接口调用失败” | 服务调用失败是资源契约问题、授权问题、网关问题还是调用方问题？ | dataservice 专题模型 + P6 调用统计投影 + 审计事件。 |
| “共享交换系统，新工作台整合数据直达工作台页面” | 用户应看到一个交付/直达工作台，而不是 supply 和 exchange 两个后台。 | P4 交付/交换/直达围绕 `delivery_task` 与 `delivery_subscription` 组织。 |
| “门户首页目录和资源统计异常” | 统计口径是否可重算、可解释、可回指事实源？ | P6 / Dashboard read model，不把统计表作为业务事实源。 |
| “资源系统注册 mysql 数据源报错” | 数据源注册和连通性是否会污染核心业务模型？ | ANP 外部执行器，核心只保存脱敏引用、审批和回执。 |
| “关于接口代理服务挂载方法” | 低频配置咨询是否应成为主导航能力？ | 外化为接入指南或 ANP 能力包，不进入普通用户主旅程。 |

## 五、目标 Agent-native 数据模型

### 5.1 聚合落位

| legacy 语义 | 目标聚合 / 表 | 说明 |
| --- | --- | --- |
| 原始需求、供需需求、数据项、材料替代诉求 | `application_record` | 统一为申请/需求意图；通过 `intent_snapshot`、`requested_items_snapshot` 保存结构化诉求。 |
| 需求拆分、任务分派、受理、校核、审核 | `approval_case`、`approval_step`、`approval_decision` | 统一审批与处理轨迹；旧任务不成为新任务系统。 |
| 资源申请、服务申请、场景申请 | `application_record` | 统一申请状态机。 |
| 申请附件、申请 PDF、补件材料 | `application_attachment` / `blob_object` | 附件只存元数据和对象存储引用。 |
| 授权、续期、频次变更、撤销授权 | `delivery_task.access_grant_snapshot`、`delivery_subscription`、`approval_case` | 授权是交付结果和持续关系，续期仍需审批。 |
| 交换任务、订阅任务、直达任务 | `delivery_task`、`delivery_subscription` | 统一 J3 交付事实源。 |
| 交换执行批次、调度历史、NiFi/Kettle 历史 | `delivery_attempt` + execution evidence | 执行细节只作为尝试和证据。 |
| 交换回执、下载回执、授权生效回执 | `delivery_receipt` | 交付结果必须可回放。 |
| 需求统计、申请统计、交换统计、资源统计 | `*_metric_projection` | 可重算 read model，不反向驱动业务状态。 |
| 操作日志、上链日志、访问日志 | `capability_call`、`audit_event`、`audit_receipt`、`anchor_outbox` | 所有写动作和关键读动作可审计。 |
| 外部 API、管道、组件安装、建表、连通性检测 | `capability_package` / `capability_version` / `capability_exposure` | 外部能力注册治理，不能直接写 canonical 状态。 |

### 5.2 建议补充的克制辅助结构

approved 数据模型已有 `application_record`、`approval_case`、`delivery_task`、`delivery_attempt`、`delivery_receipt`、`delivery_subscription`、`capability_call`、`audit_event` 等主结构。结合 require / supply / exchange 事实，实施阶段建议补充三个克制的辅助结构：

#### 5.2.1 `legacy_object_mapping`

用途：保存旧对象到新对象的迁移映射和证据引用，避免把旧 ID 当成新主键。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `legacy_system` | `dsp-require` / `dsp-supply` / `dsp-exchange` / `dsp-connect` |
| `legacy_table` | 旧表名 |
| `legacy_id` | 旧主键 |
| `canonical_type` | `application_record` / `approval_case` / `delivery_task` / `delivery_subscription` 等 |
| `canonical_id` | 新对象 ID |
| `source_ref` | XML、SQL、adapter 或迁移批次引用 |
| `mapped_at` | 映射时间 |

约束：`UNIQUE (tenant_id, legacy_system, legacy_table, legacy_id, canonical_type)`。

#### 5.2.2 `delivery_execution_evidence`

用途：保存交换执行器、外部脚本、NiFi/Kettle、Spring Batch、连通性检测、建表动作产生的证据引用。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `delivery_id` | 关联 `delivery_task` |
| `attempt_id` | 可选关联 `delivery_attempt` |
| `executor_kind` | `nifi/kettle/spring_batch/anp_script/database_probe/table_create/file_download` |
| `executor_ref` | 外部执行器任务 ID 或能力调用引用 |
| `evidence_kind` | `history/log/receipt/schema_diff/error/metric` |
| `sanitized_payload_ref` | 脱敏后的证据对象引用 |
| `result_status` | `succeeded/failed/partial/unknown` |
| `captured_at` | 采集时间 |

约束：只存脱敏证据引用，不存内部 IP、账号、密码、连接串明文。

#### 5.2.3 `exchange_metric_projection`

用途：支撑 P4 / P6 / Dashboard 查询交换运行、订阅、资源使用统计。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `metric_scope` | `delivery/resource/provider_org/consumer_org/pipeline/subscription` |
| `resource_id` | 资源 ID，可为空 |
| `delivery_id` | 交付任务 ID，可为空 |
| `subscription_id` | 订阅 ID，可为空 |
| `provider_org_id` / `consumer_org_id` | 提供方 / 使用方 |
| `time_bucket` / `bucket_granularity` | 时间窗口 |
| `exchange_count` / `success_count` / `failed_count` | 交换次数 |
| `record_count` / `file_count` / `table_count` | 业务量 |
| `last_error_code` / `last_error_at` | 最近错误 |
| `generated_at` | 投影生成时间 |

约束：这是 read model，可重算覆盖；不得作为 `delivery_task.state` 的权威来源。

## 六、字段级映射规则

| legacy 字段 / 语义 | canonical 落点 | 规则 |
| --- | --- | --- |
| `data_original_require.id` / `data_require.require_id` | `legacy_object_mapping` + `application_record.id` | 新主键重新生成 UUID，旧 ID 只进入映射证据。 |
| `require_title` / `require_content` | `application_record.title` / `intent_snapshot` | 文案按新产品口径重写，保留原始诉求证据。 |
| `data_require.share_type` | `application_record.delivery_preference_snapshot` | 映射为 API、文件、库表、订阅、直达等交付偏好，不作为资源类型权威。 |
| `data_require_column.name` / `is_major` | `requested_items_snapshot` / `catalog_item` 引用 | 数据项需求用于申请范围和检索条件。 |
| `data_*_approve.approve_result/opinion/handle_*` | `approval_decision` | 审批意见、处理人、处理时间进入审批轨迹。 |
| `data_task` / `data_subtask` | `approval_case.routing_snapshot` / 待办投影 | 任务分解是处理过程，不复造任务系统。 |
| `data_apply.id` | `legacy_object_mapping` + `application_record.id` | 申请统一进入申请状态机。 |
| `data_apply.apply_org_id/apply_org_name` | `application_record.applicant_org_snapshot` | 申请方快照保留；组织来源和 Governance 边界以 `dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。 |
| `data_apply.org_id/org_name` | `application_record.provider_org_snapshot` / `approval_case.routing_snapshot` | 提供方用于审批路由和责任边界。 |
| `data_apply_item` / `data_apply_column` | `application_record.requested_items_snapshot` | 字段级申请范围必须可回放。 |
| `data_apply_course` / `data_apply_dept_approve` / `data_apply_review` | `approval_case`、`approval_step`、`approval_decision` | 统一审批过程。 |
| `data_apply_authrization` / `data_apply_authrization_approve` | `approval_case` + `delivery_task.access_grant_snapshot` | 授权审批通过后写入授权快照和回执。 |
| `data_apply_renewal` / `data_apply_renewal_course` | `application_record(kind='grant_renewal')` + `delivery_subscription` | 续期是新申请和持续交付关系更新。 |
| `exchange_job.apply_id/resource_id/cata_id` | `delivery_task.application_id/resource_id/catalog_ref` | 交付任务关联申请、资源、目录。 |
| `exchange_job.cron_expr/publish_status/job_status` | `delivery_subscription.schedule_ref` / `delivery_task.state` | 旧状态码转语义状态；调度表达式只作外部执行引用。 |
| `exchange_job.kettle_job_*` / `nifi_job_history.*` | `delivery_execution_evidence` | 执行器路径、历史和日志只做 evidence。 |
| `exchange_trans.fields_mapping/src_table_id/target_table_id` | `delivery_task.execution_plan_snapshot` | 字段映射和源目标表是交付计划快照，变更必须走审批。 |
| `meta_host.host_ip` / `meta_datasource.db_host/db_user/db_passwd` | 外部密钥系统或脱敏 `source_ref` | 不得明文进入 canonical DB。 |
| `subscribe_job` / `subscribe_detail*` / `subscribe_trans` | `delivery_subscription` + `delivery_attempt` | 订阅是持续交付关系，执行批次是尝试；来源为旧实体和 Kingbase SQL，`dsp_connect.xml` 对应国家/上级订阅表为 `dc_subscribe*`。 |
| `stats_exchange` / `data_resource_statistics` | `exchange_metric_projection` | 可重算统计投影。 |
| `webfinal_audit_log` / `block_*` | `audit_event` / `anchor_outbox` / `audit_receipt` | 审计和上链是证据链，不直接改业务状态。 |

## 七、状态语义归并规则

本节不是旧状态码逐码兼容表，而是迁移到 zw-brain 状态机时的语义归并规则。已核对的直接事实包括：`dsp_require.xml` 中需求、业务、任务状态注释；`dsp_catalog.xml` 中 `data_apply_authrization.apply_status`、审批状态、续期/交换统计状态注释；`dsp_exchange.sql` 中 `exchange_job.publish_status`、`resource_applied.apply_status` 注释。旧 `exchange_job.job_status` 只能确认旧系统存在运行状态字段，已核对 SQL 未给出完整枚举，因此运行结果必须以后续迁移样本、执行日志和回执归并到 `delivery_attempt` / `delivery_receipt`，不能在本文写成精确码表。

### 7.1 需求 / 申请状态

| 已核对旧语义 | `application_record.status` | `approval_case.current_status` | 归并规则 |
| --- | --- | --- | --- |
| 草稿 | `draft` |  | 仅表示未提交；旧表名和旧状态码进入迁移 evidence，不进入新状态枚举。 |
| 待受理 / 待校核 / 申请提交待审核 | `submitted` | `pending_decision` | 已进入责任队列，但还没有形成最终审批结论。 |
| 审核中 / 受理中 / 处理中 | `under_review` | `in_progress` | 只表达当前仍在责任步骤中；具体步骤由 `approval_step` 承载。 |
| 补齐补正 / 校核驳回 / 驳回补正 | `needs_changes` | `returned` | 必须保留意见、处理人和退回节点，避免只留下状态码。 |
| 审核通过 / 校核通过 / 部门认领通过 | `approved` | `approved` | 只表示申请或需求处理结论通过，是否已经交付还要看 `delivery_task` / `delivery_receipt`。 |
| 驳回 / 不予提供 / 无法提供资源 / 部门认领驳回 | `rejected` | `rejected` | 必须保存原因和责任方；旧“不能提供资源”不自动等价于用户诉求结束。 |
| 已撤销 | `withdrawn` | `cancelled` | 逻辑关闭，不删除申请、审批和附件证据。 |
| 已响应 / 已反馈成效 | `fulfilled` | `approved` | 只在存在交付、反馈或成效 evidence 时使用；不能由统计表反推。 |

### 7.2 授权 / 续期状态

| 已核对旧语义 | `delivery_task.state` | `delivery_subscription.status` | 归并规则 |
| --- | --- | --- | --- |
| 授权申请提交 / 待受理 / 待审核 | `pending` |  | 授权仍是责任动作，先进入审批链，不直接生效。 |
| 授权审核通过 | `waiting_receipt` |  | 审批结论通过后，还需外部网关、服务或交换通道返回授权生效回执。 |
| 授权生效 | `succeeded` | `active` | 只有授权快照和回执齐备时才视为生效。 |
| 续期申请中 / 续期审核中 | `pending` | `renewal_pending` | 续期是新的责任动作，不能静默延长。 |
| 授权撤销 / 到期 | `revoked` / `expired` | `revoked` / `expired` | 撤销和到期不清除历史调用、审批和授权证据。 |

### 7.3 交换 / 订阅状态

| 已核对旧语义 | `delivery_task.state` | `delivery_subscription.status` | 归并规则 |
| --- | --- | --- | --- |
| 未发布 / 未启动 | `pending` | `draft` | `exchange_job.publish_status=0` 可支撑未发布语义；订阅未启动只作为持续关系未激活。 |
| 已发布 / 已启动 | `running` | `active` | `exchange_job.publish_status=1` 与交换/订阅统计注释可支撑启动语义，但不证明每次执行成功。 |
| 单次启动 / 手动执行 | `running` → `succeeded/failed` |  | 每次执行必须产生 `delivery_attempt`；成功失败来自执行证据和回执，不来自发布状态。 |
| 已停用 / 停止任务 | `suspended` | `paused` | `exchange_job.publish_status=2` 可归并为停用；停止动作必须保留操作审计。 |
| 执行失败 / 告警 | `failed` 或 `waiting_receipt` | `degraded` | 旧告警、NiFi 历史、执行日志只提供失败 evidence；核心状态由交付状态机裁决。 |
| 已删除 | `cancelled` | `cancelled` | 仅逻辑关闭，不清除审计、回执和执行历史。 |

实施要求：迁移 adapter 必须保存旧状态原值、来源表、来源字段和抽取时间；只有当旧状态语义可由注释、代码枚举或样本回放证明时，才允许写入 canonical 状态，否则写入 `legacy_status_snapshot` 并进入人工/规则复核队列。

## 八、Capability 迁移清单

| 新 Capability | 目标聚合 | 旧能力来源 | 审计等级 | 说明 |
| --- | --- | --- | --- | --- |
| `require.intent.submit` | `ApplicationApprovalAggregate` | `/restapi/addOriginalRequire`、`data_original_require` | `write-critical` | 提交原始需求或上级下发需求。 |
| `require.intent.refine` | `ApplicationApprovalAggregate` | 需求拆分、`data_require_resolve_link` | `write-normal` | 把原始诉求结构化为数据项、资源候选和交付偏好。 |
| `require.intent.review` | `ApplicationApprovalAggregate` | `data_original_require_approve`、`data_require_approve` | `write-critical` | 校核、驳回、通过、补正。 |
| `require.resource.match` | `CatalogResourceAggregate` + `ApplicationApprovalAggregate` | `data_original_require_resource`、`data_require_resource` | `write-normal` | 关联目录/资源候选。 |
| `application.resource.submit` | `ApplicationApprovalAggregate` | `data_apply`、`ResourceApplyController` | `write-critical` | 提交资源、服务、库表、文件申请。 |
| `application.resource.review` | `ApplicationApprovalAggregate` | `data_apply_course`、`data_apply_dept_approve` | `write-critical` | 受理、审批、补正、驳回、通过。 |
| `application.grant.approve` | `ApplicationApprovalAggregate` + `DeliveryAggregate` | `data_apply_authrization_approve` | `write-critical` | 审批授权、收回授权、频次变更。 |
| `application.grant.renew` | `ApplicationApprovalAggregate` + `DeliveryAggregate` | `data_apply_renewal` | `write-critical` | 续期申请和审批。 |
| `delivery.access.grant` | `DeliveryAggregate` | `data_apply_authrization`、`api_service_app` | `write-critical` | 写入授权快照、密钥引用和回执。 |
| `delivery.exchange.plan` | `DeliveryAggregate` | `exchange_job`、`exchange_trans`、`getCreateTableSql` | `write-critical` | 生成交换计划、字段映射、源目标引用。 |
| `delivery.exchange.publish` | `DeliveryAggregate` | `publishJob`、`custom/publishJob` | `write-critical` | 发布交换任务。 |
| `delivery.exchange.start` | `DeliveryAggregate` | `startJob`、`startOnce`、`startAllJob` | `write-critical` | 启动交换任务并生成 attempt。 |
| `delivery.exchange.stop` | `DeliveryAggregate` | `stopJob`、`offlineJob`、`offlineAllJob` | `write-critical` | 停止、停用或撤销交换任务。 |
| `delivery.subscription.manage` | `DeliveryAggregate` | `subscribe_job`、`PipelinesSubscribe` | `write-critical` | 创建、暂停、续期、取消订阅。 |
| `delivery.receipt.ingest` | `DeliveryAggregate` | 执行历史、下载日志、外部回执 | `write-normal` | 摄取交付回执和执行证据。 |
| `ops.exchange.statistics.query` | `exchange_metric_projection` | 可视化接口、`stats_exchange`、`table_exchange_detail_num` | `read-trace` | 查询交换统计。 |
| `ops.exchange.diagnose` | evidence / projection | `job_warning_info`、`nifi_job_alarm_info`、工单排障 | `read-trace` | 解释失败原因，不直接改状态。 |
| `adapter.legacy.exchange.ingest` | `legacy_object_mapping` + canonical aggregates | `api/1.0/push-resource`、`api/addResourceApplied` | `write-critical` | 外部旧系统接入 adapter，仍需走策略和审计。 |

## 九、ANP 外化扩展边界

| 能力 | 归属 | 边界 |
| --- | --- | --- |
| NiFi / Kettle / Spring Batch 编排执行 | ANP 执行器 | 只能执行 `delivery.exchange.plan` 已批准的计划；结果回写 evidence / receipt。 |
| 数据库连通性探测 | ANP 执行器 | 不保存连接串明文；只回写脱敏状态和错误分类。 |
| 建库建表 / 结构调整 / 清表 | 高风险 ANP 执行器 | 必须由核心审批授权后执行；执行 SQL 和结果进入脱敏证据。 |
| 主机、节点、组件安装 | 运维能力包 | 不进入普通 WebUI；只向 P6 暴露健康状态和风险摘要。 |
| 告警通知、安全漏洞处置 | 外部安全/运维能力包 | 告警是证据和待办输入，不成为交付状态权威。 |
| 客户专属统计报表 | 外部报表包 | 只能读 canonical 和投影，不允许写业务状态。 |
| 旧接口兼容代理 | adapter 包 | 只作为过渡接入输入，不承诺 URL 兼容，不绕过 Capability。 |
| 数据预览 / 下载 / 文件生成 | 外部资源交付包 | 需受授权快照约束，下载生成回执进入 `delivery_receipt` 或审计。 |

红线：外化能力不得直接写 `application_record.status`、`approval_case.current_status`、`delivery_task.state`、`delivery_subscription.status`；不得绕过 `capability_call` 和 `audit_event`；不得把内部 IP、账号、密码、密钥、连接串明文写入 canonical DB。

## 十、分波次落地建议

### Wave 0：打通供需到交付最小闭环

目标：上级/用户需求能进入申请，审批通过后形成可追踪交付任务。

- `data_original_require` / `data_require` 映射到 `application_record`。
- `data_*_approve` 映射到 `approval_case` / `approval_decision`。
- `data_require_resource` 与 `data_apply` 映射出资源申请和资源候选。
- 只实现 `require.intent.submit`、`require.intent.review`、`application.resource.submit`、`application.resource.review`。

### Wave 1：授权、续期和交付回执

目标：申请通过后能授权、续期、撤销，并留下回执。

- `data_apply_authrization*`、`data_apply_renewal*` 映射到授权快照、续期申请和 `delivery_subscription`。
- 引入 `delivery.access.grant`、`application.grant.renew`。
- 接入 `delivery_receipt` 和 `audit_receipt`。

### Wave 2：交换任务和订阅直达

目标：授权资源能形成交换计划、执行尝试和订阅关系。

- `exchange_job`、`exchange_trans`、`subscribe_job`、`PipelinesSubscribe` 映射到 `delivery_task`、`delivery_attempt`、`delivery_subscription`。
- NiFi/Kettle 执行器外化为 ANP capability。
- 引入 `delivery.exchange.plan/start/stop/publish` 与 `delivery.subscription.manage`。

### Wave 3：运营投影和排障解释

目标：P4 / P6 / Dashboard 能解释交换量、失败原因、授权到期、订阅健康。

- 建立 `exchange_metric_projection`。
- 摄取 `nifi_job_history`、`job_warning_info`、`resource_file_download_log` 的脱敏 evidence。
- 引入 `ops.exchange.statistics.query` 与 `ops.exchange.diagnose`。

## 十一、风险与反模式

| 风险 / 反模式 | 为什么不接受 | 防线 |
| --- | --- | --- |
| 按旧仓库建立 `require_center`、`supply_center`、`exchange_center` | 会复制旧后台岛，违背主旅程和 OPC | 只按聚合建模。 |
| 为兼容旧 URL 重建 controller | 会形成第二套业务入口，破坏 Capability 单一事实源 | 旧 URL 仅 adapter 输入，不承诺兼容。 |
| 把 `exchange_job` 当作唯一交付事实源 | 交换任务只是交付方式之一，无法覆盖 API、文件、订阅和直达 | 统一落 `delivery_task`。 |
| 把统计表当事实源 | 统计口径漂移会反向污染状态 | 统计全部为可重算 projection。 |
| 把连接串、主机 IP、账号密码迁入 canonical | 违反敏感信息和最小暴露原则 | 只保存外部密钥引用和脱敏证据。 |
| 外部执行器直接改交付状态 | 会绕过审批和审计 | 执行器只能回写 receipt / evidence，由核心状态机裁决。 |
| 把工单问题逐条做成菜单 | 会把现场噪音固化为产品复杂度 | 工单只提炼高频 Jobs 和风险边界。 |
| AI 对话替代审批确认 | 政务责任动作必须显式确认 | AI 只做减摩，不替代状态机。 |

## 十二、验收标准

1. 任一旧需求、申请、授权、交换、订阅对象都能找到 canonical 落点或明确外化边界。
2. 任一写动作都能回指唯一 Capability、目标聚合、审计等级和回执类型。
3. 任一旧统计、告警、日志类表都不能反向成为业务状态权威。
4. 任一外部执行器都只能消费已审批计划，并回写 evidence / receipt。
5. 工单高频问题能用“申请/审批/授权/交付/投影/执行器”解释，而不是要求新增旧式后台菜单。
6. `docs/approved/*` 不复制本文字段映射、Capability 清单、工单统计和波次计划。
7. `scripts/preflight.sh` 通过。

## 十三、证据索引

| 结论 | 证据 |
| --- | --- |
| require / supply / exchange 应合并为一条主旅程，而不是三个子系统 | `old/old_codes_analyse/dsp-exchange-apis.md` 的接口簇；`old/12-datastructure/dsp_require.xml`、`dsp_catalog.xml`、`dsp_connect.xml`、`dsp_exchange.sql` 中的关联字段 |
| 需求和任务进入申请/审批聚合 | `data_original_require`、`data_require`、`data_task`、`data_*_approve` |
| 申请、授权、续期进入申请/审批/交付聚合 | `data_apply`、`data_apply_course`、`data_apply_authrization`、`data_apply_renewal` |
| 交换任务和订阅进入交付聚合 | `exchange_job`、`exchange_trans`、`subscribe_job`、`PipelinesSubscribe` |
| 统计和可视化是 read model | `dsp-exchange` 头部调用 `/cloud/wbService/visual/resourceStatisticsInfo` 120,174 次；`stats_exchange`、`data_resource_statistics`、`table_exchange_detail_num` |
| 运行执行器应外化 | `nifi_job_history`、`exchange_pipelines*`、`components_install*`、`exchange_executor*` |
| 真实工单支持聚焦申请、资源、交换、服务、授权和排障 | `old/工单导出-列缩减.xlsx` 关键词命中：服务 715、共享 655、需求 540、资源 439、申请 244、交换 179、授权 60；该统计为非互斥命中，不作为根因分类 |

## 十四、反上帝视角自检

- 如果用户问“我提出的数据需求现在谁在处理”，本文能回答：`application_record` 保存诉求，`approval_case` 保存当前责任步骤，待办投影只负责展示。
- 如果用户问“申请通过后为什么没拿到数据”，本文能回答：授权是否生效看 `delivery_task.access_grant_snapshot`，交付是否成功看 `delivery_receipt`，执行问题看 `delivery_execution_evidence`。
- 如果用户问“交换任务为什么失败”，本文能回答：计划、授权、源库、目标库、字段映射、执行器和外部回执分别在哪里留证。
- 如果现场要求“保留旧供需/交换后台”，本文能回答：旧后台只是实现形态；用户真正需要的是需求、审批、授权、交付和追责闭环。
- 如果外部 ANP 能力声称可以直接启动交换，本文能回答：可以执行，但必须消费核心已审批计划，并只回写 evidence / receipt。
