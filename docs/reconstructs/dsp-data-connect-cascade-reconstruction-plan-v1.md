# dsp-data-connect / dsp-cascade 直达级联重构方案 v1

> 角色权威源：[`docs/approved/zw-brain-roles.md`](../approved/zw-brain-roles.md) | 架构基线：[`docs/approved/zw-brain-architecture.md`](../approved/zw-brain-architecture.md)

> 范围：旧平台 `old/old_codes/dsp-data-connect`、`old/代码信息抽取/代码信息抽取-27newbranch/dsp-data-connect_*`、`dsp-cascade-platform_*`、`dsp-cascade-down_*`、旧结构数据 `old/12-datastructure/dsp_connect.xml`、`old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx`、旧平台业务说明 `old/integrated-bigdata-platform/README.md`，以及已批准的 zw-brain 架构、数据模型和既有重构方案。
> 结论：zw-brain 不把 `dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down` 迁成“国家平台镜像系统”或“第二套目录 / 申请 / 交付库”；只吸收上下级通道、国家平台对象映射、上报 / 下发、申请受理、订阅回执、异议同步、级联日志和重放等承重语义，重建为 canonical 聚合之外的 `adapter.national.*` / `adapter.cascade.*` 能力包。国家 / 上级接口以全国一体化政务数据共享数据直达接口规范 v0.55 为协议输入，政务外网逻辑隔离边界作为部署约束。
> 单一事实源：本文是数据直达与级联专题的旧表映射、Capability 边界、状态回执、外部通道和不做清单的单一事实源；目录、资源、申请、交付、异议的核心事实仍以对应 reconstructs 与 approved 数据模型为准；跨专题 greenfield 口径、统一 adapter 命名和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 〇、专题口径速览

- **本期不实施**：国家直达 + 跨地市级联是基线 §10.4 / Wave 3 延后子旅程；本文档**仅在本期落 adapter 接口骨架与映射规则**，不投入业务联调；先实施仅限 `legacy_object_mapping` + `external_object_mapping` 表导入与 receipt 占位。**`legacy-repository-reconstruction-priorities-v1.md` §四已同步把 `dsp-data-connect` / `dsp-cascade-platform` / `dsp-cascade-down` 三个仓库从 P0 降为 Wave 3 候选**（与本文一致）。
- **adapter 落位**：所有 `adapter.national.*` / `adapter.cascade.*` 代码落在 `zw_brain/shared/adapters/national_exchange/`（基线 §7.2 entry/command/domain/shared 分层）；不在 `domain/` 新建国家通道领域模型。
- **adapter 写入规则**：adapter 绝不作为新业务写入口（基线 §9.5）；外部状态必须先形成 receipt，再由本地 domain 能力按 R15 §8 注册流水线决定是否推进 canonical 状态。
- **UI 业务术语**：前端文案使用"省市间数据通道 / 国家直达"等业务术语，禁止暴露 `adapter` / `external_object_mapping` 等工程术语（基线 §11 R12）。
- **默认租户**：`tenant_id="sd-default"`，不启用 multi-tenant（基线 §8.2）。
- **主要执行角色**：本地侧 `ROLE_BUSIAUDIT`（平台受理 + 国家通道转报审核）/ `ROLE_ORGAN_MANAGER`（部门发起上报）；基线 §5.1 7 角色码集合（角色与方向解耦，R11）。

## 一、设计原则

### 1.1 Jobs：从“镜像上级平台”改成“外部通道可证迹”

旧数据直达的表面形态是组织、应用、目录、资源、需求、申请、订阅、异议、案例的上报 / 下发管理，几乎把本级共享平台所有能力镜像到纵向通道上。zw-brain 不继承这种系统形态，只保留五类用户可感知价值：

1. 本地目录、资源、申请、需求、异议、案例能按外部协议上报到国家 / 上级平台，并保存对方返回 ID 与 receipt。
2. 国家 / 上级平台下发的目录、资源、需求、申请能进入本地候选投影或正式申请处理链路。
3. 订阅、交付和授权状态能被同步、追踪、重试和解释。
4. 级联接口、Kafka 下行、批处理执行和补发能留下审计证据，失败可重放。
5. 用户面对的是 zw-brain 的 P1/P2/P3/P5/P7 主旅程 + B1.1 后台支撑面，而不是另一个"数据直达系统"菜单。

### 1.2 OPC：canonical 主事实不被外部通道反向切分

- 目录事实仍归属 `catalog_entry` / `catalog_item` / `resource_asset`。
- 申请事实仍归属 `application_record` / `approval_case`。
- 交付和订阅事实仍归属 `delivery_task` / `delivery_subscription` / `delivery_receipt`。
- 异议事实仍归属 `objection_case` / `objection_process` / `objection_evidence`。
- 国家 / 上级返回 ID、协议版本、上报批次、接口回执、下发日志进入 adapter 映射和 receipt，不生成第二套事实表。
- 旧 `dc_*`、`cata_*`、`data_require_*`、`supply_*`、`api_service_*` 表只作为迁移、映射和 adapter 证据。

### 1.3 为什么合并 data-connect 与 cascade 分析

`dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down` 在旧平台中技术拆分不同，但领域上都是纵向通道：

1. `dsp-data-connect` 处理国家 / 上级平台的目录、资源、申请、需求、订阅、异议、案例和组织映射。
2. `dsp-cascade-platform` 处理国家目录、国家资源、国家资源申请、目录上报、目录下载、应用上报和组织接口。
3. `dsp-cascade-down` 处理下行数据消费、Kafka 消息、级联日志、补发、发布下行、需求、目录、申请等落地。
4. 三者都不能成为新系统事实源，只能成为 external adapter / sync package。

### 1.4 旧业务逻辑继承规则

目录、资源、申请、订阅、异议、案例的上报 / 下发 / 对账 / 重放流程，默认以旧 `dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down` 代码实现和全国一体化数据直达 v0.55 规范为实施依据。只有当旧逻辑试图把外部通道变成第二套 canonical 事实源、直接覆盖本地审批 / 交付 / 异议状态、或要求迁入敏感网络配置时，才进入独立决策。

### 1.5 全新项目口径

本专题不提供旧 `/apply/*`、`/country/*`、`/manage/*`、`/consumer/reinsert` 等 URL 兼容层，不迁旧“数据直达系统”菜单和镜像平台形态。旧 data-connect / cascade 的业务流转可作为 adapter 行为依据，但外部状态必须先形成 receipt，再由本地域能力决定是否推进 canonical 状态。

## 二、证据清单

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture.md` | 国家平台保持外部依赖关系，不在大脑内复造；Legacy Adapters 是架构边界之一。 |
| `docs/approved/zw-brain-data-model.md` | `dsp-data-connect`、`dsp-catalog-platform` 等不原样迁入，承重语义收敛到 CatalogResource / ApplicationApproval / Delivery / Objection / Audit 聚合。 |
| `docs/approved/zw-brain-architecture.md` | 国家直达与跨地市级联是 J1 / J2 之外的独立子旅程，按 §10.4 Wave 3 延后实施；本期仅以 adapter 形态接入，不进 J1/J2 主导航。 |
| `docs/approved/research-yibiaotong.md` | zw-brain 必须连接上级交换和基层填报链路；双向流动服务基层报表减负。 |
| `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md` | `dsp_connect.xml` 中的订阅、需求、申请语义应进入申请 / 交付链路，但外部通道作为 adapter。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | `dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down` 被列为 P0，合并成上下级直达与级联 adapter 专题。 |

### 2.2 旧 data-connect API 证据

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/apply/save/resource/apply`、`/apply/submit/resource/apply`、`/apply/reject/resource/apply` | 资源申请保存、提交、驳回、补正、撤销 | 映射到 `application.*` 主能力；直达 adapter 只负责上报和 receipt。 |
| `/apply/accept/*` | 申请受理、预审核、审核、审核日志 | 映射到 `approval_case` 和 `audit_event`，不保留直达侧审批事实源。 |
| `/api/example/report/*` | 案例上报、撤销、驳回 | P7 专题包 / 纵向案例上报 adapter，不恢复本级案例系统。 |
| `/auth/queryPublishedServicePage`、`/auth` | 查询已发布服务与认证 | 与 dataservice capability / access grant 关联，授权结果写 receipt。 |
| `/organ/report/regionLeftTreeNodesFromBsp` | 区域树 / 组织 | 组织投影和外部编码映射。 |
| `/admin/refreshApplyStatus`、`/admin/refreshAuth`、`/admin/objectionStatusRefresh` | 刷新申请、授权、异议状态 | 状态同步 / reconcile capability，不对用户暴露。 |
| `/api/metrics/probe`、`/api/metrics` | 指标探测 | B1.1 通道健康 projection。 |

### 2.3 旧 data-connect 表证据

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `dc_area_mapping`、`dc_organ_mapping` | 本地与国家 / 上级区划、组织编码映射 | `external_object_mapping` / `legacy_object_mapping`，用于 adapter 解析。 |
| `dc_catalog`、`dc_catalog_item`、`dc_catalog_group` | 上报 / 下发目录、目录项、分组 | 只读映射到 `catalog_entry` / P7 projection，不创建第二套目录事实源。 |
| `dc_resource_base_info`、`dc_resource_*_detail` | 上报 / 下发资源及库表、文件、接口详情 | 映射到 `resource_asset` / `resource_channel_binding` 和 evidence。 |
| `dc_resource_apply_info`、`dc_resource_apply_audit`、`dc_resource_apply_accept_audit` | 国家资源申请、受理、审核状态 | 映射到 `application_record` / `approval_case` / `delivery_receipt`。 |
| `dc_require`、`dc_require_column`、`dc_require_resource` | 跨级数据需求、供需、责任部门、关联资源 | 映射到 `application_record.intent_snapshot` 和 ROLE_ORGAN_OPERATER 任务投影。 |
| `dc_subscribe`、`dc_subscribe_table`、`dc_subscribe_folder`、`dc_to_subscribe` | 资源订阅、待确认订阅 | 映射到 `delivery_subscription` / `delivery_attempt` / receipt。 |
| `dc_objection_*` | 异议上报、受理、流程、目录、资源、使用 | 映射到 `objection_case` / `objection_process` / `objection_evidence`。 |
| `dc_example_*` | 案例事项、资源、信息项 | P7 专题包 evidence 或纵向案例上报 adapter。 |
| `dc_sync_job`、Spring Batch 表 | 同步任务和执行历史 | 外部执行器 / adapter run record，不进入核心聚合。 |
| `dc_datasource` | 数据源连接信息 | 不迁明文连接；只保留脱敏 endpoint ref 或外部通道引用。 |
| `dc_opt_log` | 操作日志 | `audit_event` 或迁移 evidence。 |

### 2.4 旧 cascade-platform 证据

`dsp-cascade-platform_对外提供API清单.md` 显示：

| 旧接口簇 | 新系统解释 |
| --- | --- |
| `/require/restapi/*` | 纵向需求上报 / 查询；本地事实仍是 `application_record`。 |
| `/country/getCountryCatalogByPage` / `Details` | 国家目录拉取 projection。 |
| `/country/getCountryResourceByPage` / `Details` | 国家资源拉取 projection。 |
| `/country/subjectApplyCountryResourceFrom` | 对国家资源发起申请；写本地 `application_record`，adapter 提交外部申请。 |
| `/country/cancelCountryResourceApply` | 取消外部申请；写本地状态和外部 receipt。 |
| `/country/countryResourceApplyStatus` | 同步国家申请状态。 |
| `/country/CountryAuthorization` | 同步国家授权结果。 |
| `/manage/report/catalog/*` | 本地目录上报到上级。 |
| `/manage/catalog/download/*` | 上级目录下载和纠错；只作为候选投影或异议。 |
| `/manage/report/app/*` | 应用系统上报；外部应用目录 adapter。 |
| `/upload/serviceUpload` | 文件上传执行器；不进入核心。 |

其表结构中的 `api_service_*` 表说明旧平台还承载 API 服务申请、应用、黑名单、调用日志、服务目录等网关能力。zw-brain 不迁网关，只把服务授权和调用证据映射到 dataservice capability、`delivery_receipt`、`audit_event`。

### 2.5 旧 cascade-down 证据

`dsp-cascade-down_对外提供API清单.md` 与表结构显示：

| 旧能力 | 新系统解释 |
| --- | --- |
| `/consumer/reinsert` | `adapter.cascade.replay`，按日志 ID 重放失败下行数据。 |
| `ICascadePullService.pullCascadeData` | `adapter.cascade.pull`，外部通道拉取 / 消费。 |
| `cascadeResourcePushJobHandler`、`cascadeCatalogPushJobHandler`、`cascadeRequirePushHanlder`、`cascadeBspPushJobHandler` | 外部调度器 / adapter job，不进入主旅程。 |
| Kafka Topic `级联数据同步主题` | 外部消息输入，解析后写候选映射、receipt 或 canonical command。 |
| `data_cascade_record_log` | adapter run record / `audit_event`。 |
| `data_cascade_interface_log` | 通道调用日志 / B1.1 健康 projection。 |
| `data_cascade_plat_info` | 外部平台连接信息；敏感字段不得入库明文。 |
| `cata_catalog*`、`data_require*`、`supply_catalog_apply*` | 下行目录、需求、申请投影，最终归属 canonical 聚合。 |
| `data_interact_feedback` | 可转为 `objection_case` 或 B1.1 反馈 evidence。 |

### 2.6 旧业务说明证据

旧平台说明中“国家资源对接（数据直达）”明确：

1. 数据直达是省 / 市与国家之间的双向通道。
2. 国家到本省：推送国家目录、资源，分发给本省的需求 / 申请。
3. 本省到国家：上报本省目录、资源、申请、需求、异议、案例。
4. 所有交互均通过国家平台 API。
5. 数据直达接口仅在政务网内可访问，公网不可达。
6. 直达链路监控承载国家接口调用情况和业务督办预警。
7. 实际高频使用集中在目录、资源、申请三块。

### 2.7 全国一体化数据直达规范证据

`old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx` 明确数据直达由国家端和地方端两部分组成，地方端由各地方建设；数据目录、数据资源、供需对接、资源申请、异议处理、创新应用等业务数据通过服务接口对接，库表资源和文件资源复用既有数据交换通道。该规范对本专题形成四个约束：

1. adapter 必须覆盖目录查询、详情、注册、变更、撤销和审查驳回信息查询。
2. adapter 必须覆盖资源查询、注册、变更、撤销、共享申请、审批状态、订阅任务和服务资源调用频次变更。
3. 异议填报、异议处理、异议评价属于国家直达业务范围，需通过 `adapter.national.objection.sync` 与本地 `ObjectionAggregate` 分离。
4. 部署边界需遵守“接入政务外网的逻辑隔离区域，与部门其他网络之间有明确边界”，敏感连接参数只能以环境配置或密钥引用存在。

## 三、目标 adapter 模型

### 3.1 Adapter 边界

本专题建议新增逻辑 adapter 包，不新增主事实聚合：

- `NationalExchangeAdapter`：对接国家 / 上级平台 API。
- `CascadeDownAdapter`：消费下级 / 上级下发消息、Kafka、批量下行数据。
- `CascadeReplayAdapter`：按失败日志重放。
- `ExternalObjectMapping`：记录本地对象与外部对象 ID、批次、协议版本、方向。
- `AdapterRunRecord`：记录每次同步、上报、下发、重放、对账执行结果。

### 3.2 方向模型

| 方向 | 触发 | 处理方式 |
| --- | --- | --- |
| `outbound_report` | 本地目录 / 资源 / 需求 / 申请 / 异议 / 案例需要上报 | 从 canonical 读取快照，转换协议，调用外部 API，保存 external ID 与 receipt。 |
| `inbound_pull` | 主动拉取国家目录 / 资源 / 状态 | 写候选 projection、external mapping 或触发 canonical command。 |
| `inbound_push` | Kafka / API 下发 | 解析消息，校验幂等，写 adapter run record，再投递 canonical command。 |
| `status_reconcile` | 定时 / 人工刷新申请、授权、异议状态 | 对账外部状态，生成 receipt，不直接覆盖本地状态。 |
| `replay` | 失败补发 / 补消费 | 基于日志 ID 和幂等键重放，保留新 run record。 |

### 3.3 外部映射字段建议

| 字段 | 说明 |
| --- | --- |
| `id` | 映射记录 ID。 |
| `tenant_id` | 租户。 |
| `external_system` | `national_platform/cascade_up/cascade_down/legacy_connect`。 |
| `direction` | `outbound/inbound`。 |
| `local_aggregate_type` | `catalog/resource/application/delivery/objection/topic_package/org/system`。 |
| `local_aggregate_id` | 本地 canonical ID，可为空；无法解析时先进入 unresolved。 |
| `legacy_table` / `legacy_id` | 旧表和旧 ID。 |
| `external_object_type` | 外部对象类型。 |
| `external_object_id` | 国家 / 上级返回 ID，例如 `up_cata_id`、`up_apply_id`、`up_sub_id`。 |
| `protocol_version` | 外部协议版本。 |
| `batch_no` | 上报 / 下发批次。 |
| `status` | `pending/mapped/unresolved/retired`。 |
| `last_receipt_json` | 最近一次外部回执脱敏摘要。 |

### 3.4 Adapter run record 字段建议

| 字段 | 说明 |
| --- | --- |
| `id` | 执行记录 ID。 |
| `adapter_slug` | adapter 名称。 |
| `operation` | `report/pull/consume/reconcile/replay`。 |
| `direction` | `inbound/outbound`。 |
| `source_ref` | 旧日志 ID、Kafka offset、批处理 ID 或 API request ID。 |
| `idempotency_key` | 幂等键。 |
| `status` | `running/succeeded/failed/partial/replayed`。 |
| `target_count` | 涉及对象数量。 |
| `success_count` | 成功数量。 |
| `failure_count` | 失败数量。 |
| `receipt_json` | 外部回执脱敏摘要。 |
| `error_summary` | 错误摘要，不含密钥和内部连接串。 |
| `started_at` / `finished_at` | 执行时间。 |

## 四、Capability 设计

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `adapter.national.catalog.pull` | 写 | `write-trace` | 拉取国家 / 上级目录候选投影。 |
| `adapter.national.resource.pull` | 写 | `write-trace` | 拉取国家 / 上级资源候选投影。 |
| `adapter.national.catalog.report` | 写 | `approval-trace` | 上报本地目录并保存 receipt。 |
| `adapter.national.resource.report` | 写 | `approval-trace` | 上报本地资源并保存 receipt。 |
| `adapter.national.application.submit` | 写 | `approval-trace` | 向国家 / 上级提交资源申请。 |
| `adapter.national.application.receive` | 写 | `approval-trace` | 接收外部对本地资源的申请，转为 canonical 申请。 |
| `adapter.national.application.reconcile` | 写 | `write-trace` | 同步申请和授权状态。 |
| `adapter.national.delivery.receipt.sync` | 写 | `write-trace` | 同步订阅、交付、授权回执。 |
| `adapter.national.objection.sync` | 写 | `approval-trace` | 同步异议上报、受理、核查和结案状态。 |
| `adapter.national.topic.report` | 写 | `write-trace` | 上报案例 / 专题包证据。 |
| `adapter.cascade.consume` | 写 | `write-trace` | 消费下行消息并投递 canonical command。 |
| `adapter.cascade.replay` | 写 | `approval-trace` | 按失败日志重放。 |
| `adapter.cascade.health.query` | 读 | `read-trace` | 查询通道健康、接口调用、失败率。 |
| `adapter.external.mapping.query` | 读 | `read-trace` | 查询本地对象与外部对象映射。 |

## 五、旧表到新系统映射

| 旧表 / 字段 | 新落位 | 说明 |
| --- | --- | --- |
| `dc_catalog.up_cata_id` | external mapping `external_object_id` | 国家返回目录 ID。 |
| `dc_resource_base_info.up_resource_id` | external mapping | 国家返回资源 ID。 |
| `dc_resource_apply_info.up_apply_id` | external mapping + `delivery_receipt` | 国家返回申请 ID 和状态。 |
| `dc_require.up_require_id` | external mapping | 国家返回需求 ID。 |
| `dc_subscribe.up_sub_id` | external mapping + `delivery_subscription` | 国家返回订阅 ID。 |
| `dc_organ.up_organ_id` | org projection mapping | 国家返回组织 ID。 |
| `dc_system.up_system_id` | external app mapping | 应用系统上报返回 ID。 |
| `dc_resource_apply_info.status` | `approval_case` / receipt | 外部状态作为 receipt，不直接覆盖本地审批事实。 |
| `dc_catalog.status`、`dc_system.status` | external mapping status | 上报、变更、撤销、驳回。 |
| `dc_datasource.host/port/user/password` | 不迁明文字段 | 只允许保存密钥引用或脱敏 endpoint ref。 |
| `data_cascade_record_log` | adapter run record | 下行记录和补发依据。 |
| `data_cascade_interface_log` | `audit_event` + B1.1 projection | 接口调用日志。 |
| `data_cascade_plat_info.link_ip` 等 | adapter config reference | 敏感连接配置不得入 canonical。 |
| Spring Batch `batch_*` 表 | adapter run record | 执行历史摘要。 |
| `api_service_*` | dataservice capability / access grant / audit | 不复造 API 网关。 |
| `data_interact_feedback` | `objection_case` 或 feedback evidence | 互动反馈按问题类型转异议或运营反馈。 |

## 六、状态与回执策略

### 6.1 本地状态与外部状态分离

本地 canonical 状态不能被外部状态直接覆盖。外部返回值必须先形成 receipt，再由领域能力决定是否推进本地状态。

示例：

1. 本地 `application_record=submitted`。
2. 调用 `adapter.national.application.submit`。
3. 国家返回 `up_apply_id` 和受理状态。
4. 写 external mapping 与 `delivery_receipt`。
5. 若 receipt 符合规则，触发 `application.external_receipt.accepted` 领域事件。
6. `approval_case` / `delivery_task` 根据领域规则推进。

### 6.2 幂等键

| 场景 | 幂等键建议 |
| --- | --- |
| 目录上报 | `tenant_id + catalog_entry_id + version + external_system` |
| 资源上报 | `tenant_id + resource_asset_id + version + external_system` |
| 申请提交 | `tenant_id + application_record_id + external_system` |
| 订阅同步 | `tenant_id + delivery_subscription_id + external_system` |
| 异议同步 | `tenant_id + objection_case_id + external_system` |
| Kafka 下行消费 | `topic + partition + offset` 或 `table_name + data_id + change_type + batch_no` |
| 补发重放 | `original_run_id + replay_attempt` |

### 6.3 失败处理

- 网络不可达、政务网接口失败：记录 adapter run failed，进入 B1.1 通道健康告警。
- 外部协议校验失败：记录 unresolved mapping，等待人工或协议修订。
- 本地目标不存在：进入 unresolved，不自动创建核心事实。
- 重放成功：保留原失败记录，新建 replay run record。
- 部分成功：保存每个对象 receipt，批次状态为 partial。

## 七、读模型与运营指标

| 读模型 / 指标 | 来源 | 用途 |
| --- | --- | --- |
| 外部对象映射查询 | external mapping | 解释本地对象对应国家 / 上级对象 ID。 |
| 上报批次列表 | adapter run record | B1.1 合规运营与运维排障。 |
| 下行消费日志 | adapter run record + cascade logs | 查询失败、补发和重放结果。 |
| 国家接口健康 | adapter run record + probe | 直达链路监控。 |
| 申请 / 授权状态同步差异 | receipt + canonical 状态 | 发现外部状态和本地状态不一致。 |
| 目录 / 资源上报覆盖率 | catalog/resource mapping | 统计哪些对象已上报。 |
| 失败率 / 超时率 | adapter run record | B1.1 预警。 |
| 高频 unresolved 对象 | unresolved mapping | 指导字段映射和协议适配。 |

## 八、迁移与验证策略

### 8.1 迁移步骤

1. 登记 `legacy_adapter_source`：`dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down`、版本、数据库类型、抽取时间。
2. 导入 `dc_*`、`cata_*`、`data_cascade_*` 等旧对象 ID 到 external mapping。
3. 对目录、资源、申请、订阅、异议、组织、应用系统分别解析本地 canonical 对象。
4. 无法解析的对象进入 unresolved 清单，禁止自动写入核心事实。
5. 导入同步批次、Spring Batch 和级联日志摘要为 adapter run record。
6. 对包含连接信息、IP、账号、密码、文件路径的字段做脱敏或只保留密钥引用。
7. 用真实脱敏样本回放上报、下发、状态对账、失败重放。

### 8.2 验证样本

最小样本必须覆盖：

1. 本地目录上报国家并返回 `up_cata_id`。
2. 本地资源上报国家并返回 `up_resource_id`。
3. 本省申请国家资源，返回 `up_apply_id` 与状态。
4. 国家 / 上级下发目录和资源，本地形成候选投影。
5. 外部对本地资源发起申请，本地生成 `application_record`。
6. 订阅任务状态同步。
7. 异议上报或异议状态同步。
8. Kafka 下行新增、更新、删除各一条。
9. 失败日志补发成功。
10. 外部状态与本地状态不一致时进入差异清单。

## 九、不做清单

1. 不复刻“数据直达系统”菜单和镜像平台形态。
2. 不把 `dc_catalog`、`dc_resource_base_info`、`dc_resource_apply_info` 当作新事实源。
3. 不兼容旧 `/apply/*`、`/country/*`、`/manage/*`、`/consumer/reinsert` URL。
4. 不迁入明文 host、port、用户名、密码、link_ip、政务网地址、证书、API key。
5. 不在 adapter 内实现完整 API 网关、应用中心、组织中心、监控中心。
6. 不因外部 receipt 自动覆盖本地审批、交付、异议状态。
7. 不把 Spring Batch、XXL-Job、Kafka 运行表迁入用户产品模型。
8. 不把低频案例推广恢复为本级横向应用案例系统。

## 十、专题差异决策

全局 adapter 部署边界、外部下发对象生效方式和 greenfield 口径以总览方案第八节为准。本专题只保留数据直达 / 级联协议与通道差异：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| C1 | v0.55 地方扩展或新版修订 | 以 v0.55 为基线 contract，地方扩展只进入 adapter mapping，不进入 canonical 模型。 | 地方字段保存到 `receipt_json`、`external_object_mapping.extra_json` 或 adapter 专属 schema。 |
| C2 | 外部申请进入本地后的生效方式 | 外部申请先进入待确认候选池，通过规则校验或人工确认后再生成正式 `application_record`。 | adapter 先写 external mapping、adapter run record 和 receipt，不直接创建审批事实。 |
| C3 | 国家 / 上级下发目录资源的发布方式 | 默认只进入候选投影，不自动发布到 P2 发现页；需提供方或平台确认后发布。 | 外部目录 / 资源不得反向驱动本地目录事实。 |
| C4 | 下行通道形态 | adapter 层兼容 Kafka / API 拉取 / 文件批量同步，核心只认统一 `adapter_run_record` 和 canonical command。 | 核心不绑定 Kafka、Spring Batch 或具体文件交换实现。 |

## 十一、证据来源

- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-data-connect_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-data-connect_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-data-connect_外部SDK和接口文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-cascade-platform_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-cascade-platform_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-cascade-down_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-cascade-down_数据库表结构文档.md`
- `old/12-datastructure/dsp_connect.xml`
- `old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx`
- `old/integrated-bigdata-platform/README.md`
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/zw-brain-data-model.md`
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/research-yibiaotong.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-objection-handling-reconstruction-plan-v1.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
