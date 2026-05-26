# dsp-dataservice 相关模块重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-dataservice`（3.16.15）、外部调用分析 `old/old_codes_analyse/dsp-dataservice-apis.md` 与旧结构数据 `old/12-datastructure`。
> 结论：zw-brain 是全新 AI 原生项目，迁移目标不是兼容旧接口与旧表，而是吸收承重业务语义，重建为围绕主旅程、统一 Capability、可审计的数据服务能力面。

## 〇、专题口径速览

- **旅程归属**：API 服务资源在 **J1 找数→用数**中是 P2/P3/P4 主要消费对象（资源发现 / 申请审批 / 凭据领取与调用）；服务发布 / 撤回归 **J2 挂数→维数**（P5 提供方管理）；网关健康 / 调用统计归 **B1.1 合规与运营**只读 projection（基线 §5.1）。
- **物理实现**：本文 §3.3-3.4 投影表 `gateway_runtime_status_projection` / `service_invocation_metric_projection` 作为 B1.1 read model（基线 §3.4 "运行监控由集团统一运维监控平台承担" 兼容），schema 通过 `Base.metadata.drop_all + create_all` 管理（基线 §9.6），**不进入 alembic**；这两张表是审计派生投影，**不是网关管理事实源**。
- **R15 桥接面**：§3.5 Capability 清单（`resource.api.*` / `ops.gateway.*` / `ops.service.*`）通过统一 contract 投影到 5 消费面（WebUI / API / CLI / MCP / A2A），MCP / A2A 投影由 AgentRuntime `AGENT.yaml` 声明（基线 §8.1 / R15）。
- **R14 三引擎**：API 服务的"服务发布审批节点 / 选人规则"由 Wave 2 R14 审批流可视化引擎承接（基线 §10.3），本文档 Wave 0 仍用硬编码 5 步流程。
- **默认租户**：`tenant_id="sd-default"`，不启用 multi-tenant（基线 §8.2）。
- **本文 Wave 编号** = 基线 §10 Wave 的专题子集；本文档原标 Wave 0-3 与基线 Wave 0-4 节奏对齐：网关心跳 / 调用统计投影属基线 Wave 0；API 服务资源化属基线 Wave 1；治理动作属基线 Wave 2；编排外部化属基线 Wave 3。

## 一、设计原则

### 1.1 Jobs：从“数据服务后台”改成“数据拿得到、用得稳、可追责”

旧 `dsp-dataservice` 的表面形态是服务管理、网关、调度、编排、Hystrix 监控等后台模块；新系统不继承这些模块名，也不复刻运维页面。它们在 zw-brain 中只保留四类用户可感知价值：

1. 数据资源能被发现、理解和申请。
2. 数据服务能被安全开通、调用和交付。
3. 调用、失败、限流、上链等过程能被运营与审计回放。
4. 少量真正有价值的自动编排能成为注册 Capability，而不是新建一个流程平台。

### 1.2 确定性自动化运营和运维：单一事实源，不为旧系统开第二套治理中心

- 服务定义进入 `resource_asset` 与 `resource_channel_binding`，不再建立并列的“数据服务中心”；`dsp-dataservice` 专属映射、投影字段与迁移规则以本文为单一事实源，approved 数据模型只保留 canonical 通用结构与引用。
- 服务调用、网关日志、上链回执进入 `brain_audit`，不再维护独立日志岛。
- 服务发布、撤回、审核复用 `approval_case` 与 Capability 写审计，不重建旧审批控制器。
- 网关黑白名单、频控、熔断、认证信息作为通道策略快照或外部网关策略引用，不扩散成主旅程之外的后台产品。
- 旧库与旧 API 只作为只读 adapter 输入源，不允许成为新业务写入口。

## 二、旧 dsp-dataservice 能力理解

### 2.1 模块边界

| 旧模块 | 旧职责 | zw-brain 去向 |
| --- | --- | --- |
| `dsp-service-mgmt` | 服务目录、发布审核、代理导入、统计查询、应用授权、网关配置管理 | 核心语义拆入 `CatalogResourceAggregate`、`ApplicationApprovalAggregate`、`AuditAggregate` 与 B1.1 运营投影 |
| `dsp-service-gateway` | Zuul 网关、路由、鉴权、限流、元数据缓存、调用上报 | 外部网关/运行时 adapter；策略元数据进入 `resource_channel_binding` |
| `dsp-service-work` | 刷新网关缓存、上传调用日志到区块链 | 异步 worker；缓存刷新成为运行时内部动作，上链进入 `anchor_outbox` |
| `dsp-service-orchestrator` | 轻量工作流，支持 HTTP、DATA_SERVICE 等任务 | 长尾编排能力；只保留为可注册 Capability 包，不进入主旅程核心状态机 |
| `hystrix-dashboard` | 熔断监控页面 | 不迁入 WebUI；由外部观测底座或 B1.1 只读指标摘要承接 |

### 2.2 高频外部使用形态

旧仓库已核验为 `3.16.15` detached HEAD。外部调用量最高的 `/openapi/report` 不是业务报表查询，而是 `dsp-service-gateway` 通过 `Report2MgmtJob` 每分钟调用 `MgmtService.report2Mgmt()` 上报网关地址，`dsp-service-mgmt` 的 `AdminApiController.report()` 写入 Redis `GATEWAY_REPORT`。因此它在 zw-brain 中应落为“网关运行状态投影”，而不是服务调用统计接口。

外部使用集中在四类能力：

1. 网关实例心跳与运行状态上报：`/openapi/report`。
2. 服务调用统计：`/openapi/getServiceInvokedBySystemStatisticInfos`、`StatisticsApiController` 中按提供方、调用方、地区、时间维度的统计查询。
3. 服务目录与详情查询：按目录、服务 ID、分组查询服务。
4. 服务发布、审核、代理导入、测试、撤回、策略优化等管理动作。

因此迁移优先级不是“先复刻所有 controller”，而是：

1. 先把网关心跳和服务调用统计变成 B1.1 可读的运营与审计投影。
2. 再把服务资源定义变成可发现、可申请、可交付的 `api` 类 `resource_asset`。
3. 最后处理低频服务管理动作，将其收敛到目录/资源发布、通道策略和能力注册治理。

### 2.3 外部调用 Pareto 结论

`old/old_codes_analyse/dsp-dataservice-apis.md` 显示，去重后 89 个接口、三项目合计 636,710 次调用。头部调用决定迁移顺序：

| 优先级 | 旧接口/能力 | 调用量特征 | 新系统处理 |
| --- | --- | --- | --- |
| P0 | `/openapi/report` | 最高频，362,407 次；实际是网关心跳 | 进入 `gateway_runtime_status_projection`，不作为业务报表 |
| P0 | `/openapi/getServiceInvokedBySystemStatisticInfos` | 173,072 次；调用方/系统统计 | 进入 `service_invocation_metric_projection` 与 `ops.service.invocation.query` |
| P1 | `/openapi/sendCallThresholdMessage` | 30,443 次；阈值通知 | 不重建消息中心；作为 B1.1 告警/通知 adapter 输出 |
| P1 | 服务列表、详情、目录查询 | 千级到百级；支撑发现 | API 服务资源化后由 P2/B1.1 读 `resource_asset` 与 projection |
| P2 | 服务维护、发布、审核、撤回、代理导入 | 百级以下但责任强 | 进入写 Capability 与 `approval_case`，不按旧 URL 兼容 |
| P3 | Hystrix、WSDL、低频后台页 | 低频或运维/长尾 | 外部化或不迁入主产品 |

这符合 Jobs/确定性自动化运营和运维：先替代最高频真实价值链路，同时不给长尾后台页面永久席位。

### 2.4 旧实体语义映射

| 旧实体/对象 | 承重语义 | zw-brain 去向 |
| --- | --- | --- |
| `ApiServiceInfo` | API 服务本体、提供方、区域、发布状态、开放状态、业务场景 | `resource_asset(resource_kind='api')` |
| `ApiServiceCatalog` / `ApiGroup` | 服务分类与展示分组 | `catalog_entry` / `catalog_item` / 搜索投影 |
| `ApiServiceProxy` / `ApiServiceNode` / `ApiInputParam` / `ApiServiceGeneral` | 代理路由、节点、入参、通用服务绑定 | `resource_channel_binding` |
| `ApiServiceFuse` / `ApiAccessIp` / `ApiServiceFilter` / `ApiServicePool` | 熔断、黑白名单、过滤、线程池/池化策略 | `resource_channel_binding.gateway_policy_json` 或外部网关策略引用 |
| `ApiServiceApp` | 应用授权关系 | `application_record` + `delivery_task.access_grant_snapshot` |
| `ApiServiceTimes` | 按 API、提供方、调用方、地区、应用、时间维度聚合调用次数和错误类型 | `service_invocation_metric_projection` |
| `ApiServiceStatistic` | 调用、浏览、收藏、申请、评分等服务市场指标 | 调用/申请进入 `service_invocation_metric_projection`；评分/收藏默认不进核心事实源 |
| Redis `GATEWAY_REPORT` / `Report2MgmtJob` | 网关实例心跳与地址上报 | `gateway_runtime_status_projection` |
| 网关调用日志 / 错误日志 | 调用证据、失败证据、运营指标来源 | `capability_call`、`audit_event`、`service_invocation_metric_projection` |
| `UploadApiLog2BlockchainJob` 文件搬运与外部 deposit 调用 | 网关日志异步存证 outbox | `anchor_outbox` + `audit_receipt` |
| `WorkflowDef` / `TaskDef` | 轻量编排定义，支持 HTTP、DATA_SERVICE、DECISION、LOOP、PARALLEL | `capability_package` / `capability_version.runtime_binding_ref`，不进入核心聚合 |

## 三、zw-brain 数据模型设计

本节是 `dsp-dataservice` 相关数据模型与迁移映射的单一事实源；`docs/approved/zw-brain-data-model.md` 只保留 zw-brain canonical model 的通用结构，并在相关模块引用本节。

### 3.1 API 服务资源

API 服务不再是独立后台模块，而是 `resource_asset` 的一种资源类型：

- `resource_kind = 'api'`
- `resource_code` 承接稳定服务编码
- `resource_name` 承接服务名称
- `owner_org_id` / `owner_org_snapshot` 承接提供方
- `status` 承接草稿、待审、已发布、暂停、撤回、退役等生命周期
- `access_policy_json` 承接共享、申请、授权边界
- `qos_policy_json` 承接通用 QoS、SLA、配额策略

这样 P2 资源发现、P3 申请审批、P4 交付开通可以自然消费 API 服务，而不是让用户切换到“服务管理后台”。

### 3.2 API 通道绑定

API 服务的真实调用通道进入 `resource_channel_binding`：

- `channel_type = 'api'`
- `endpoint_ref` 保存路由、网关、代理目标、外部服务引用，不保存明文密钥。
- `schema_ref` 保存参数、响应、错误码、样例等契约引用。
- `auth_ref` 保存认证方式与密钥引用。
- `gateway_policy_json` 保存限流、熔断、黑白名单、过滤、日志采集级别等策略快照，或指向外部网关策略 ID。
- `delivery_capability_slug` 指向实际开通/调用/交付能力。

### 3.3 网关运行状态投影

旧 `/openapi/report` 是网关心跳，zw-brain 不应把它伪装成业务报表。建议在 B1.1 读侧使用 `gateway_runtime_status_projection`：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `gateway_instance_id` | 网关实例稳定标识，可由地址、部署单元、租户组合生成 |
| `gateway_address` | 上报地址或外部网关引用 |
| `runtime_profile` | 运行 profile 或部署模式 |
| `status` | `online/degraded/offline/unknown` |
| `last_reported_at` | 最近心跳时间 |
| `source_ref` | 来源 adapter、Redis key 或外部网关观测引用 |
| `generated_at` | 投影生成时间 |

它是运行状态 read model，不是新的网关管理事实源；真正的路由、认证、限流策略仍应回到 `resource_channel_binding.gateway_policy_json` 或外部网关策略系统。

约束与索引建议：

- `UNIQUE (tenant_id, gateway_instance_id)`，确保一个租户内同一网关实例只有一条当前状态。
- `INDEX (tenant_id, status, last_reported_at DESC)`，支撑 B1.1 查询在线、降级、离线实例。

legacy 对应：`AdminApiController.report`、`Report2MgmtJob`、`MgmtService.report2Mgmt`、Redis `GATEWAY_REPORT`。

### 3.4 服务调用统计投影

旧系统最常被外部消费的是统计查询，因此 zw-brain 需要显式承认一个读侧投影：`brain_audit.service_invocation_metric_projection`。

它不是业务事实源，事实源仍是 `capability_call`、`audit_event` 与网关调用日志 adapter；它的职责是支撑 B1.1、API 查询与运营排障。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `tenant_id` | 租户 |
| `metric_scope` | 统计粒度：`service/provider_org/consumer_org/provider_region/consumer_region/consumer_app/tenant` |
| `resource_id` | 对应 API 类 `resource_asset`；非服务粒度可为空 |
| `capability_slug` | 对应调用能力 |
| `provider_org_id` / `consumer_org_id` | 提供方与调用方 |
| `provider_region_code` / `consumer_region_code` | 提供方与调用方区划 |
| `consumer_app_ref` | 调用应用引用，不保存 `ApiServiceApp.secret` / `superiorAppSecret` 明文 |
| `time_bucket` / `bucket_granularity` | 统计窗口；支持 `minute/hour/day/week/month/year/all` |
| `invoke_count` / `success_count` / `failed_count` | 调用量 |
| `provider_error_count` / `consumer_error_count` / `gateway_error_count` / `other_error_count` | 错误归因统计 |
| `apply_count` | 服务申请次数，仅作为运营指标 |
| `avg_latency_ms` / `p95_latency_ms` | 延迟指标 |
| `last_error_code` / `last_error_at` | 最近错误 |
| `source_event_ref` | 审计或网关日志来源 |
| `generated_at` | 投影生成时间 |

约束与索引建议：

- `UNIQUE (tenant_id, metric_scope, resource_id, provider_org_id, consumer_org_id, provider_region_code, consumer_region_code, bucket_granularity, time_bucket)`，保证同一统计粒度和时间窗可重算覆盖，不累积重复口径。
- `INDEX (tenant_id, metric_scope, time_bucket DESC)`，支撑租户运营查询。
- `INDEX (resource_id, time_bucket DESC)`，支撑单服务调用趋势。
- `INDEX (provider_org_id, time_bucket DESC)` 与 `INDEX (consumer_org_id, time_bucket DESC)`，支撑提供方/调用方维度排障。

legacy 对应：`ApiServiceStatistic`、`ApiServiceTimes`、网关调用日志、错误日志、`/openapi/getServiceInvokedBySystemStatisticInfos` 以及按服务、提供方、调用方、区划、应用、时间维度的统计查询接口。

### 3.5 服务治理动作能力化

旧 controller 动作不按 URL 兼容，而按 Capability 重命名：

| 新 Capability | 目标聚合 | 旧能力来源 | 审计等级 |
| --- | --- | --- | --- |
| `resource.api.register` | `resource_asset` + `resource_channel_binding` | 代理导入、数据服务注册、`ProxyOperateController.addApi` | `write-critical` |
| `resource.api.change` | `resource_asset` + `resource_channel_binding` | 代理服务编辑/变更、`ProxyOperateController.updateApi` | `write-critical` |
| `resource.api.submit_review` | `approval_case` + `resource_asset` | `ServiceManageController.submit` | `write-critical` |
| `resource.api.review` | `approval_case` + `resource_asset` | `ServiceManageController.examine` / `batchExamine` | `write-critical` |
| `resource.api.publish` | `catalog_entry` / `resource_asset` / `approval_case` | `ServiceManageController.publishService` | `write-critical` |
| `resource.api.withdraw` | `resource_asset` / `approval_case` | `ServiceManageController.withdraw` | `write-critical` |
| `resource.api.revoke` | `resource_asset` / `approval_case` | `ServiceManageController.revert` / `checkRevert` | `write-critical` |
| `resource.api.test` | `delivery_attempt` 或测试投影 | 服务测试 | `write-normal` |
| `resource.api.policy.update` | `resource_channel_binding` | `optimizeService`、黑白名单、频控、熔断、线程池 | `write-critical` |
| `ops.gateway.heartbeat.ingest` | `gateway_runtime_status_projection` | `/openapi/report` | `read-trace` |
| `ops.service.report.query` | `service_invocation_metric_projection` | 统计查询 | `read-trace` |
| `ops.service.invocation.query` | `service_invocation_metric_projection` | `/openapi/getServiceInvokedBySystemStatisticInfos` | `read-trace` |
| `ops.gateway.log.anchor` | `anchor_outbox` | `UploadApiLog2BlockchainJob` | `write-critical` |

### 3.6 字段级映射规则

| legacy 字段/语义 | canonical 落点 | 规则 |
| --- | --- | --- |
| `ApiServiceInfo.ID` | `legacy_object_mapping` + `resource_asset.id` | 新主键重新生成 UUID，旧 ID 只进入映射证据 |
| `ApiServiceCatalog.ID` / `ApiGroup.ID` | `legacy_object_mapping` + `catalog_entry` / `catalog_item` | 分类、分组只作为目录展示与搜索结构，不等同 API 服务本体 |
| `NAME` / `DESCRIPTION` | `resource_asset.resource_name` / `summary` | 用户可见名称与说明保留，但文案按新产品口径重写 |
| `ORG_CODE` / `ORG_NAME` / `APP_ORGAN_CODE` | `owner_org_id` / `owner_org_snapshot` | 组织、角色和 IAM 绑定边界以 `dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准；服务能力只保存调用时快照 |
| `REGION_CODE` / `REGION_NAME` | `catalog_entry.region_code` / `tenant_org_projection` / 指标区划字段 | 区划用于发现、统计与审批路由，不成为权限权威 |
| `TYPE` / `SERVICE_TYPE` / `CALL_TYPE` | `resource_kind` / `resource_channel_binding.endpoint_ref` | 统一收敛为 API 通道类型与 endpoint 元数据 |
| `URL` / `VERSION` / `PROXY_URL` / `REST_METHOD` | `resource_channel_binding.endpoint_ref` | 保存路由与外部端点引用，不暴露为前台导航 |
| `INPUT` / `OUTPUT` / `API_RESULT` / `RESULT_TYPE` | `resource_channel_binding.schema_ref` | 转为输入输出 schema、样例、错误码引用 |
| `AUTH_TYPE` | `resource_channel_binding.auth_ref` | 只保存鉴权方式与密钥引用 |
| `SECRET` / `superior_app_secret` | 不入 canonical 明文字段 | 必须迁入密钥系统或外部引用，不得落库明文 |
| `FREQUENCY_TIME` / `FREQUENCY_NUM` / `EXTRA_CALL_FREQUENCY` | `gateway_policy_json` / `access_grant_snapshot` | 区分资源默认频控与某次授权覆盖策略 |
| `HYSTRIX_NUM` / `HYSTRIX_TIMEOUT` / `POOL_ID` | `gateway_policy_json` | 作为外部网关策略快照或策略引用 |
| `PRE_FILTER_ID` / `AFTER_FILTER_ID` | `gateway_policy_json` | 过滤链引用，不把 filter 代码迁入核心模型 |
| `SHARE_TYPE` / `OPEN_TYPE` / `PRIVACY_DATA` | `access_policy_json` | 映射共享、开放、敏感数据策略 |
| `CALL_TIMES` / `ApiServiceTimes.*` | `service_invocation_metric_projection` | 作为可重算运营投影，不作为资源事实源 |
| `FILE_NAME` / `FILE_PATH` | `blob_object` 或 `source_ref` | 仅用于旧附件/日志文件引用，文件本体进对象存储 |

### 3.7 结构数据证据补充

`old/12-datastructure` 补强的是旧库表级事实，不改变 Jobs/确定性自动化运营和运维 迁移方向。它证明旧 `dsp-dataservice` 的承重对象确实集中在服务本体、服务分类、代理通道、授权策略、调用统计、运行监控和上链日志：

| 结构来源 | 关键旧表/字段 | 对本方案的约束 |
| --- | --- | --- |
| `old/12-datastructure/dsp_service.xml` | `api_service_info` 的 `ID`、`NAME`、`ORG_CODE`、`REGION_CODE`、`STATUS` | API 服务本体进入 `resource_asset(resource_kind='api')`；组织和区划只保存快照或路由维度 |
| `old/12-datastructure/dsp_service.xml` | `api_service_catalog`、`api_group`、`api_group_lk` | 分类、分组和服务关联只进入目录/搜索投影，不等同 API 服务事实源 |
| `old/12-datastructure/dsp_service.xml` | `api_service_proxy` 的 `PROXY_URL`、`REST_METHOD`、`FREQUENCY_TIME`、`FREQUENCY_NUM`，`api_service_data` / `api_service_general` 的服务绑定字段 | 路由、代理、频控和具体通道信息进入 `resource_channel_binding` 与 `gateway_policy_json` |
| `old/12-datastructure/dsp_service.xml` | `api_service_app` 的 `APP_ID`、`AUTH_TYPE`、`FREQUENCY_*`、`SECRET`、`superior_app_secret` | 授权关系进入 `application_record` / `delivery_task.access_grant_snapshot`；密钥只进密钥系统或引用，不得明文落 canonical DB |
| `old/12-datastructure/dsp_service.xml` | `api_access_ip`、`api_service_filter`、`api_service_pool`、`api_service_errors` | 黑白名单、过滤器、线程池、错误码属于通道策略和契约证据，收敛到 `gateway_policy_json` / `schema_ref` |
| `old/12-datastructure/dsp_service.xml` | `api_service_times` 的提供方、调用方、区划、应用、调用次数与错误统计字段，`api_service_statistic` 的浏览/收藏/申请/评分字段 | 调用与错误统计进入 `service_invocation_metric_projection`；浏览、收藏、评分不作为核心事实源 |
| `old/12-datastructure/dsp_monitor.xml` | `cgservice_warning_rules`、`interface_result`、`product_call_result`、`service_warning_rule` 中的 `service_id`、`service_name`、`gateway_ip`、`error_type`、`call_time` | 运行监控和拨测只作为 B1.1 运营投影与外部诊断 Capability 输入，不成为服务生命周期事实源 |
| `old/12-datastructure/dsp_block.xml` | `block_apilog`、`block_err_log`、`block_success_log` | 上链仍按 `anchor_outbox` + `audit_receipt` 处理；外链结果不反向驱动业务状态 |

因此，`old/12-datastructure` 的作用是校验旧表字段覆盖面，而不是要求 zw-brain 复刻旧库 schema；凡属生命周期、审批、授权、审计的事实进入 canonical 聚合，凡属运行、统计、拨测、告警的内容进入可重算投影或外部 Capability。

### 3.8 状态映射规则

旧 `ServiceStatusEnum` 的具体编码不进入新模型；迁移 adapter 只输出语义状态：

| legacy 语义 | `resource_asset.status` | `approval_case.current_status` | 说明 |
| --- | --- | --- | --- |
| 草稿 / 审核驳回后待修改 | `draft` |  | 可继续编辑 |
| 注册提交 / 注册审核中 | `pending_review` | `pending_decision` | 对应 `resource.api.submit_review` |
| 审核通过待发布 | `suspended` 或 `pending_review` | `approved` | 取决于是否已对外可用；不得直接等同 active |
| 已发布 | `active` | `approved` | 可被发现、申请、调用 |
| 发布后变更待审 | `pending_review` | `pending_decision` | 保留当前线上版本，变更走版本快照 |
| 撤回 / 撤销审核中 | `pending_review` | `pending_decision` | 对应 `resource.api.withdraw` / `resource.api.revoke` |
| 已撤销 / 删除 | `revoked` 或 `retired` | `approved` | 受监管领域不物理删除 |
| 服务优化 / 策略调整 | 状态不变 | 可选 `pending_decision` | 只改 `gateway_policy_json`，高风险策略需审批 |

## 四、能力迁移分类

### 4.1 zw-brain 原生核心产品业务能力

核心能力只保留围绕 API 服务资源主旅程、跨项目高频、强责任、可审计、可回放的部分。新增工单素材只用于抽象故障模式和流程诉求，不把工单系统本身变成 zw-brain 事实源。

| 原生核心能力 | 承接对象 | 判定依据 |
| --- | --- | --- |
| API 服务资源化 | `ApiServiceInfo` → `resource_asset(resource_kind='api')` | API 服务必须能被发现、理解、申请、交付，是 P2/P3/P4 主旅程对象 |
| API 服务目录发现 | `ApiServiceCatalog` / `ApiGroup` → `catalog_entry` / `catalog_item` / 搜索投影 | 服务列表、详情、目录查询仍是用户发现入口，但不复刻旧服务市场后台 |
| API 通道绑定 | 代理、路由、参数、响应、鉴权引用 → `resource_channel_binding` | 调用通道是服务可交付的必要条件，必须可被审计和回放 |
| 服务申请、审批、授权、发布、撤回 | `application_record`、`approval_case`、`delivery_task` | 旧 controller 写动作责任强，必须进入统一状态机和审计链 |
| 通道策略治理 | 限流、熔断、黑白名单、过滤链、日志采集级别 → `gateway_policy_json` | 策略影响调用安全和稳定性，属于资源交付边界，不做独立网关后台 |
| 网关心跳与运行状态 | `/openapi/report` → `gateway_runtime_status_projection` | 旧最高频接口实际是网关心跳，进入 B1.1 只读运行状态投影 |
| 服务调用统计与错误归因 | `ApiServiceTimes`、网关日志 → `service_invocation_metric_projection` | 调用量、成功率、错误归因支撑运营排障，不作为业务事实源 |
| 调用失败与工单语义归因 | 工单主题类型、处置摘要、证据引用 → 审计与运营投影 | 工单反复暴露接口失败、流程改造、展示异常，需要可解释的证据链，不复制工单系统 |
| 日志上链证据 | `UploadApiLog2BlockchainJob` → `anchor_outbox` + `audit_receipt` | 上链是审计证据扩展，本地审计先落库，外链异步执行 |

### 4.2 可通过 ANP / 外部 Capability 外化的能力

外化能力应做成符合协议约束的 Capability 包、adapter 或执行器：声明输入/输出 contract、审计等级、租户策略、失败回写方式，不直接写 canonical 状态。

| 外化能力 | 外化形态 | 边界 |
| --- | --- | --- |
| 具体网关运行时 | 外部网关 adapter，如旧 Zuul 或后续选型的外部网关运行时 | zw-brain 管服务、策略和审计；网关管转发、限流、鉴权、熔断执行 |
| 网关缓存刷新与路由下发 | ANP 执行器 / runtime adapter | 只能按 canonical 策略执行，不反向成为策略事实源 |
| 环境与中间件诊断 | DB、ES、Nginx、JDK、Logstash、SQLServer 等诊断 Capability | 工单中的环境故障只触发诊断和证据采集，不直接改业务状态 |
| 外部系统联动 | 工单系统、监控、CMDB、Wiki、共享交换平台 adapter | 只同步引用、状态摘要和证据，不复制外部系统全量模型 |
| 特殊协议与项目化接口适配 | WSDL 解析、特殊代理协议导入、地区项目脚本 | 长尾能力通过注册包交付，不进入普通用户主导航 |
| 轻量编排 | 旧 orchestrator 的 HTTP / DATA_SERVICE 编排包 | 可作为 ANP/Capability runtime binding，不新建流程编排中心 |
| 门户展示异常修复 | 项目化页面修复脚本或外部前端适配 | 目录/搜索投影一致性归核心，具体页面修复执行外化 |
| 熔断监控细节 | 外部观测底座或网关监控 adapter | zw-brain 只消费摘要和告警，不迁入 Hystrix 原页面 |

### 4.3 工单素材对能力边界的启发

`old/工单导出-列缩减.xlsx` 只作为脱敏后的能力边界证据。文档不摘录工单原文、姓名、组织、内部地址或密钥。

| 工单主题类型 | 对 dsp-dataservice 重构的启发 | 归属 |
| --- | --- | --- |
| 流程改造 | 服务发布、审核、授权、撤回应进入核心状态机，避免散落在旧后台 controller | Core |
| 接口调用失败 | 调用证据、错误归因、排障摘要进入核心投影；具体环境诊断由执行器外化 | Core + External |
| 门户展示异常 | 目录、搜索、统计投影的一致性检查归核心；页面修复和项目化展示脚本外化 | Core + External |
| 环境/中间件故障 | 作为外部诊断 Capability，不进入 zw-brain 主业务模型 | External |

### 4.4 不可外化红线

- API 服务生命周期事实源不可外化。
- 申请、审批、授权、发布、撤回状态机不可外化。
- 审计总线、审计回执和上链 outbox 的本地事实不可外化。
- 租户、权限、策略裁决不可外化给执行器。
- 外化 Capability 不得绕过 Capability / policy / audit 写 canonical 状态。
- 明文密钥、内部地址、工单个人信息不得进入文档、日志或 canonical 明文字段。

### 4.5 Drop：不迁入

- 旧登录、退出、门户首页、菜单页面。
- Hystrix dashboard 原页面。
- 服务收藏、评论、评分作为主事实源。
- 旧网关节点管理页面的运维细节。

## 五、adapter 迁移规则

### 5.1 输入源

| adapter source | 读取对象 | 输出 |
| --- | --- | --- |
| `dsp_dataservice_mgmt` | `ApiServiceInfo`、`ApiServiceCatalog`、`ApiServiceProxy`、`ApiInputParam`、`ApiServiceApp`、策略类表 | `resource_asset`、`catalog_entry`、`catalog_item`、`resource_channel_binding`、`application_record`、`legacy_object_mapping` |
| `dsp_dataservice_metrics` | `ApiServiceTimes`、`ApiServiceStatistic`、ES 网关日志 | `service_invocation_metric_projection` |
| `dsp_dataservice_gateway_runtime` | Redis `GATEWAY_REPORT` 或网关心跳 API 快照 | `gateway_runtime_status_projection` |
| `dsp_dataservice_blockchain_log` | `apilog/arc`、`apilog/deposit`、旧上链返回 | `audit_receipt`、`anchor_outbox` |
| `dsp_dataservice_orchestrator` | `WorkflowDef`、`TaskDef` JSON 定义 | 外部 `capability_package` 草案 |

### 5.2 输出纪律

- adapter 只读旧系统，不回写旧表、Redis 或旧文件目录。
- adapter 输出 canonical draft 后，所有写入必须经 command/capability/audit。
- 每个旧对象必须写 `legacy_object_mapping`；冲突进入 `mapping_status='conflicted'`，不得自动覆盖。
- 密钥、secret、内部地址只输出引用或脱敏快照，不进入文档、日志或 canonical 明文字段。
- 统计投影允许重算；业务状态不允许由统计表反推。

## 六、落地波次

### Wave 0：网关状态、统计与审计读面先落地

目标：让旧系统最高频的网关心跳、服务调用统计在 zw-brain 中有权威读面。

- 建立 `gateway_runtime_status_projection`，承接 `/openapi/report` 语义。
- 建立 `service_invocation_metric_projection`，承接服务调用统计语义。
- 将旧网关日志、统计表、Redis 心跳快照只读接入为 adapter source。
- 由 `capability_call` / `audit_event` / adapter 日志生成 B1.1 指标。
- 暴露 `ops.gateway.heartbeat.ingest`、`ops.service.report.query` 与 `ops.service.invocation.query`。

### Wave 1：API 服务资源化

目标：API 服务进入资源发现、申请、审批、交付主旅程。

- `ApiServiceInfo` → `resource_asset(resource_kind='api')`。
- 路由、参数、认证、网关策略 → `resource_channel_binding`。
- 服务目录/分组 → `catalog_entry` 与搜索投影。
- 服务发布/撤回 → `approval_case` + 审计回执。

### Wave 2：治理动作收敛与外化能力注册

目标：把高价值服务管理动作变成 Capability，把长尾执行动作收敛为 ANP / 外部 Capability，而不是复刻后台。

- 服务注册、代理导入、策略更新、服务测试能力化。
- 黑白名单、限流、熔断进入 `gateway_policy_json` 或外部网关策略引用。
- 工单素材只作为脱敏后的故障类型、流程诉求和处置摘要输入，不成为 canonical 事实源。
- 外部工单、监控、CMDB、环境诊断执行器按 ANP / Capability contract 注册。
- 缓存刷新与日志上链进入 worker 与 outbox。

### Wave 3：编排外部化

目标：只保留有业务价值的编排语义。

- `WorkflowDef` / `TaskDef` 转为外部 Capability 包 manifest 与 runtime binding。
- 首批只支持 HTTP 与 DATA_SERVICE 类任务。
- 网关运行时、环境诊断、特殊协议导入等长尾能力通过 ANP / 外部 Capability 扩展。
- 不新建“流程编排中心”作为普通用户页面。

## 七、验收标准

1. 任一迁移对象必须能回指 `legacy_object_mapping`，否则不算迁移完成。
2. 任一写动作必须经过 Capability、policy、audit，不允许页面、adapter 或外化执行器直接改状态。
3. API 服务在 WebUI 中首先表现为可发现、可申请、可交付的资源，而不是旧后台菜单。
4. 统计查询必须能解释来源：来自审计事件、网关日志 adapter，还是旧统计表快照。
5. 网关策略不保存明文密钥，只保存策略快照或外部引用。
6. 旧 URL 不作为兼容契约；新契约以 Capability slug 与统一 contract 为准。
7. 任一 ANP / 外部 Capability 必须声明输入输出 contract、审计等级、租户策略和失败回写方式。
8. 外化能力不得绕过核心状态机、审计总线和策略裁决写 canonical 状态。
9. 工单素材只允许沉淀脱敏后的主题类型、故障模式、证据引用和处置摘要，不得写入姓名、组织、内部地址或密钥原文。

## 八、源码证据索引

| 结论 | 源码证据 |
| --- | --- |
| 旧仓库核验为 `3.16.15` | `git -C old/old_codes/dsp-dataservice describe --tags --always --dirty` 输出 `3.16.15` |
| 旧结构数据证明服务本体、分类、代理、授权、策略、统计、监控、上链日志是 dsp-dataservice 承重对象 | `old/12-datastructure/dsp_service.xml`、`old/12-datastructure/dsp_monitor.xml`、`old/12-datastructure/dsp_block.xml` |
| `/openapi/report` 是网关心跳，不是业务报表 | `dsp-service-gateway/src/main/java/com/inspur/dsp/gateway/config/Report2MgmtJob.java`、`dsp-service-gateway/src/main/java/com/inspur/dsp/gateway/execute/service/MgmtService.java`、`dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/api/rest/AdminApiController.java` |
| 调用方/系统维度统计来自 `ApiServiceTimesService` | `dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/api/rest/ApiLogController.java`、`dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/entity/ApiServiceTimes.java` |
| 服务统计维度覆盖提供方、调用方、地区、时间、成功/失败 | `dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/api/rest/StatisticsApiController.java`、`dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/entity/ApiServiceTimes.java` |
| 服务注册、审核、发布、撤回是强责任写动作 | `dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/controller/ServiceManageController.java`、`dsp-service-mgmt/src/main/java/com/inspur/dsp/service/mgmt/controller/ProxyOperateController.java` |
| 日志上链是异步文件 outbox 语义 | `dsp-service-work/src/main/java/com/inspur/dsp/service/work/job/UploadApiLog2BlockchainJob.java` |
| 编排支持 HTTP / DATA_SERVICE / DECISION / LOOP / PARALLEL，但不应升格为主旅程中心 | `dsp-service-orchestrator/src/main/java/com/inspur/dsp/orchestrator/model/WorkflowDef.java`、`dsp-service-orchestrator/src/main/java/com/inspur/dsp/orchestrator/model/TaskDef.java` |

