# compliance ops adapters 合规运营与外部治理重构方案 v1

> 范围：旧平台 `datasecurity-service`、`indata-security-executor`、`standardservice-service`、`metricsmgr-service`、`data-operation-board-front`、`dsp-monitor`、`dsp-esupervision`，以及 approved 中关于 B1.1 合规与运营、外部数据治理中心、外部观测底座、Capability contract 和审计总线的设计原则。
> 结论：zw-brain 不把旧安全中心、标准服务平台、指标平台、监控告警、督导系统迁成新的综合运维 / 治理后台；只吸收风险事件、敏感识别摘要、标准资产候选、指标定义投影、接口健康、告警工单、超期督导和整改证据等承重语义，重建为 B1.1 合规与运营 projection + 外部 adapter + `audit_event` 证据链。安全风险闭环进入 zw-brain B1.1，自带最小 `compliance_case` 闭环；标准数据迁移参考 `old/08标准服务系统标准数据`。
> 单一事实源：本文是安全、标准、指标、监控、督导等 B1.1 合规与运营旧仓库的重构去向、Capability 边界、旧表 / 接口映射和不做清单的专题单一事实源；目录、资源、申请、交付、异议、专题包和能力注册的主事实仍以对应 reconstructs 与 approved 数据模型为准；跨专题 greenfield 口径和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 一、设计原则

### 1.1 Jobs：从“多套治理后台”改成“风险、质量、效率可解释”

旧平台把数据安全、标准服务、指标管理、监控告警、电子督导拆成多套后台。zw-brain 不继承后台形态，只保留五类用户可感知价值：

1. 监管方能看到目录、申请、交付、服务、异议是否超时、异常或不合规。
2. 平台方能解释风险来自哪个能力、对象、组织、调用、外部通道或策略。
3. 提供方能看到标准、质量、敏感数据、安全风险对其资源发布和交付的影响。
4. 运维方能看到外部通道、服务调用、级联 adapter、任务执行的健康和失败原因。
5. Agent 能基于审计、回执、指标和风险证据生成追责 / 改进建议，而不是维护一套独立监控事实。

### 1.2 OPC：B1.1 是 projection 与 case，不是反向事实源

- 安全风险、监控告警、标准质量、指标看板、督导预警只读消费 canonical 事件、回执、审计和外部 adapter 摘要。
- 目录、资源、申请、交付、异议、Capability 的状态不能由 B1.1 projection 直接覆盖。
- 需要人工处置的风险进入 `compliance_case` 候选；`risk_case` 只作为 `compliance_case` 的风险分类或读模型术语，不新增未获 approved 数据模型确认的核心事实表。zw-brain 自带最小确认、分派、整改、关闭闭环，不默认派发到外部工单系统。
- 分类分级、敏感识别、脱敏、加密、密钥、数据源扫描默认外部化，zw-brain 只保存摘要、结果引用和整改证据。
- B1.1 对**业务主旅程（J1/J2）的状态**只读：禁止 B1.1 投影或 case 闭环反向覆盖目录、资源、申请、审批、交付、异议、Capability 等核心状态。
- B1.1 的**写操作严格限定在合规 case 闭环 + 规则配置**：`compliance.case.*`、`compliance.rule.configure`、`risk.event.ingest` 是 B1.1 自身闭环所必需的 6 个写 Capability（详见 §四 Capability 清单），其作用域不越出"风险事件入站 → 升级 case → 分派 → 整改 → 关闭"链路。
- 主要执行角色：`ROLE_BUSIAUDIT`（业务运营员，case 受理与分派）/ `ROLE_SECURITY_AUDIT`（审计督查）/ `ROLE_SECURITY_ADMIN`（数据安全策略）；基线 §5.1 7 角色码集合。
- 本专题新增的 6 个辅助表（`compliance_signal` / `risk_event_projection` / `compliance_case` / `compliance_rule` / `health_signal_projection` / `metric_definition_projection`）**通过 SQLAlchemy `Base.metadata.drop_all + create_all` 管理**，不进入 alembic（基线 §9.6）。
- 默认租户：`tenant_id="sd-default"`（基线 §8.2 / 单租户单省）。

### 1.3 为什么不能迁成安全 / 指标 / 监控大后台

1. approved 已明确数据治理中心、外部观测底座是外部依赖，zw-brain 不复造。
2. 旧 `datasecurity-service` 同时覆盖分类分级、识别、脱敏、加密、密钥、数据源、风险和看板，迁入会形成新平台底座。
3. 旧 `metricsmgr-service` 能直连数据源、建模型、建指标、发布 API 和调度任务，和 zw-brain 的目录 / 服务 / B1.1 边界冲突。
4. 旧 `dsp-monitor`、`dsp-esupervision` 的价值是告警、超期和合规证据，不应变成主业务状态机。
5. OPC 要求主旅程深而窄：B1.1 只提供可解释运营与处置入口，不成为所有系统的后台入口。

### 1.4 旧业务逻辑继承规则

风险识别、告警接收、督导超期、规则配置、标准数据元 / 字典、指标口径和处理过程，默认以旧 `datasecurity-service`、`indata-security-executor`、`standardservice-service`、`metricsmgr-service`、`dsp-monitor`、`dsp-esupervision` 代码实现和 `old/08标准服务系统标准数据` 为实施依据。只有当旧逻辑试图复造安全中心 / 标准平台 / 指标平台 / 监控后台、直接修改 canonical 主状态、迁入连接串 / 密钥 / 样例敏感数据，或让 B1.1 投影反向执行业务写操作时，才进入独立决策。

### 1.5 全新项目口径

本专题不提供旧安全中心、标准平台、指标平台、监控告警、电子督导写操作或旧 URL 兼容层。`compliance_case` 是 B1.1 最小闭环的逻辑对象；物理表和字段落地必须回到 approved 数据模型基线，不以本文新增未批准核心表。

## 二、证据清单

### 2.1 approved 与既有 reconstructs 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture.md` | 不做大屏 / 指挥中心 / 演示页面（§1.3）；数据治理中心、外部观测底座、集团推理平台保持外部依赖。 |
| `docs/approved/zw-brain-data-model.md` | `audit_event`、`capability_call`、receipt 和 canonical 聚合是合规解释的事实来源。 |
| `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` | 目录、元数据、资源、质量、血缘已收敛到 CatalogResourceAggregate，标准 / 安全只可作为 evidence。 |
| `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md` | 申请、审批、交付、订阅的超期和异常必须从主链路投影，不在督导系统内复制状态。 |
| `docs/reconstructs/dsp-objection-handling-reconstruction-plan-v1.md` | 异议超期、解决率、满意度进入 B1.1 指标，但异议状态仍归 ObjectionAggregate。 |
| `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md` | 外部通道健康、失败率、重放结果进入 B1.1 projection；外部状态不覆盖本地状态。 |
| `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` | IAF IAM、本地 Governance、租户 / 组织 / 用户 / 角色投影、Capability policy 和暴露面边界由该文档定义；B1.1 只能查看和建议，不绕过策略。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | 安全、标准、指标、监控、督导列为 P2 / B1.1 adapter 和 projection，不进入核心重构。 |

### 2.2 旧 datasecurity-service / indata-security-executor 证据

旧代码目录显示 `datasecurity-service` 包含 `security-manage`、`security-encryption`、`security-plugin-hive`、`security-sensitive-function` 等模块；Controller 命名和路径覆盖：

| 旧能力 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| 分类分级 | `DataCategoryController`、`DataLevelController`、`DataStrategyController`，如 `/classification/v1/categories/*` | 外部数据治理 / 安全中心；只同步分类分级摘要和资源风险标签。 |
| 数据资产视角 | `DataCatalogPerspectiveController`、`DatabasePerspectiveController`、`DataAssetViewController` | B1.1 / P2 资产安全 projection，不成为目录事实源。 |
| 数据源管理 | `DatasourceController`、`DatasourceManageController` | 外部扫描配置；禁止迁入连接串和账号。 |
| 敏感识别 | `RuleController`、`RuleGroupController`、`TaskController`、`RecordController`、`ResultController`、`SensitiveDataController` | `security.scan.result.sync`，仅保存摘要、风险级别和对象引用。 |
| 动态 / 静态脱敏 | `DynamicDsRuleController`、`DynamicDtRuleController`、`StaticRuleController`、`StaticTaskController`、`StaticRecordController` | 外部执行器；zw-brain 保存任务 receipt，不执行脱敏引擎。 |
| 加密与密钥 | `KeyController`、`KeyPairController`、`EncryptRestApi`、`ServerController` | 外部 KMS / 加密服务；密钥材料不迁。 |
| 审计日志 | `AuditLogController`、`LogController` | 可导入 `audit_event` 摘要；不把旧安全日志当作新事实源。 |
| 风险识别 | `RiskIdentificationRulesController`、`RiskWarningEventController`、`AlarmConfigurationController` | `risk.event.ingest` 与 `compliance.case.open` 候选。 |
| 外部集成 | `Rest4BspController`、`Rest4XxljobController`、`SecurityOpenApi` | adapter 边界；不迁 BSP / XXL-Job 依赖。 |

`indata-security-executor` README 显示敏感识别任务支持精确、模糊、正则匹配，并处理 Oracle、Hive、静态脱敏任务执行问题。其 Controller 包含 `DiscoveryTaskController`、`MaskTaskController`、`RiskTaskController`、`IdentifyTaskController`、`StaticTaskController`、`MetricsController`、`MessageCenterController`。

新系统处理：安全执行器只作为外部扫描 / 脱敏 / 风险任务 adapter，核心保存任务摘要、对象引用、结果哈希、风险等级、整改状态和审计证据。

### 2.3 旧 standardservice-service 与标准数据证据

旧 `standardservice-service` 包含 `standard-manage` 与 `standard-report`。`old/08标准服务系统标准数据` 提供本轮标准资产迁移的权威样本输入，至少包含数据元导出文件和多个数据字典文件，例如 `数据元_2026-04-22 14_54_08.xlsx`、国别（地区）代码、机构性质代码、身份证件类型代码、行业门类代码等字典。处理原则是：这些文件可作为标准数据元、领域字典和模型字段 evidence 进入 `standard_asset_projection` / `CatalogModel` 候选；不得据此复造标准服务平台或全局字典后台。

旧 `standardservice-service` Controller 显示：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/model/*` | 数据模型列表、校验、保存、发布、下线、版本比较、资源关联、向量同步 | 标准模型候选，映射为 `catalog_model` / `catalog_model_field` evidence。 |
| `/dict/*`、`/api/dict/*` | 字典列表、导入、发布、下线、版本比较、关联资源 / 模型 | 领域字典候选，不建全局字典平台。 |
| `/rule/*` | 规则列表、校验、保存、在线测试、关联模型 | 数据规则 evidence；规则执行外部化。 |
| `/docu/*` | 标准文档、发布、下线、关联模型 | 对象存储 / 知识检索 evidence。 |
| `/catalog/*`、`/api/catalog/*` | 标准分类目录 | 标准资产目录 projection，不替代业务目录。 |
| `/recommend/*`、`/tableRecommend/*`、`/fileRecommend/*` | 表 / 文件 / 资源推荐标准 | `standard.asset.recommend` adapter 结果。 |
| `/search/*` | 标准检索、热词、访问量、同步 ES | 统一搜索 / projection，不迁 ES 写入链路。 |
| `/overview/*`、`/analysisReport/*` | 标准覆盖率、发布趋势、关联趋势、PDF 导出 | B1.1 标准质量 projection，不作为事实源。 |

### 2.4 旧 metricsmgr-service / data-operation-board-front 证据

`metricsmgr-service` Controller 显示其不仅是看板，还能建数据源、模型、指标、API、调度：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/datasource/*` | 数据源创建、连接测试、表 / 字段 / 样例数据 | 外部 BI / 指标平台；禁止迁入连接信息。 |
| `/indicator/*` | 指标创建、发布、下线、版本、血缘、查询指标数据 | `metric.definition` 候选或 B1.1 指标 projection；不直接查询业务库。 |
| `/dimension/*`、`/dataModel/*` | 维度和数据模型管理 | B1.1 projection 元数据候选。 |
| `/api-service/*`、`/api/do/*` | 指标 API 发布、在线测试、授权应用、调用统计 | 不复造 API 网关；服务型 Capability 归 `dsp-dataservice` 方案。 |
| `/scheduler/*` | 指标调度任务、实例、重启、停止 | 外部调度器；只保存 adapter run record。 |
| `/app/*`、`/oauth/token` | 应用和 OAuth | 外部应用 / IAM，不迁。 |
| `/tag/*`、`/catalog/*`、`/statistic-period/*` | 标签、业务目录、统计周期 | B1.1 projection 配置候选。 |

`data-operation-board-front` 只作为 B1.1 视觉 / 指标展示诉求输入，不迁前端代码；B1.1 必须只读消费 projection。

### 2.5 旧 dsp-monitor 证据

抽取文档显示 `dsp-monitor` 是监控告警项目，API 覆盖：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/warningWorkOrder/ruleConfigure/*` | 告警工单规则配置 | `compliance.rule.configure` 候选，但规则执行可外部化。 |
| `/warningMessageInfo/overview/*` | 告警概览、分布、24 小时趋势 | B1.1 告警 projection。 |
| `/warningMessageInfo/manage/*` | 接收、清理、详情、生成工单、处理告警 | `risk.event.ingest` / `compliance.case.open` / `compliance.case.resolve`。 |
| `/warning/interface/pushWarningInfo` | 外部告警推送 | `risk.event.ingest`。 |
| `/logWarning/*` | 日志告警规则、ES 磁盘、日志使用 | 外部观测底座摘要；不迁 ES。 |
| `/servicedialing/warning/rule/*` | 服务拨测告警规则 | `adapter.health.probe` / service health projection。 |
| `/servicedialing/task/config/*` | 服务拨测任务配置 | 外部调度器 / adapter run record。 |
| `/login`、验证码 | 自建登录 | IAF IAM 承担认证；本地 Governance 边界以 `dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。 |

表结构文档显示 `WarningMessage`、`WarningMessageInfo`、`WarningWorkOrderRules`、`WarningHandleProcess`、`LogWarningRule`、`MonitorItem`、`MonitorRule`、`MonitorResult`、`MonitorPlan`、`MonitorHost`、`DatasourceInfo`、`DatasourceMonitor` 等。新系统只保留告警事件、处理过程、规则摘要、健康指标和外部对象引用。

### 2.6 旧 dsp-esupervision 证据

`dsp-esupervision` Controller 显示其核心是电子督导、合规和超期：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/home/getHomeStatic`、`/home/getAlertTrend`、`/home/getAlertDistribution` | 首页统计、预警趋势、分布 | B1.1 compliance projection。 |
| `/apply/getTimelimitStatic`、`/apply/getApplyData`、`/apply/timeLimitHandle` | 申请超期统计、列表、处理 | 从 `application_record` / `approval_case` 投影；处理进入合规 case。 |
| `/apply/getComplianceStatic`、`/apply/complianceHandle` | 申请合规统计和处理 | 合规规则命中与整改证据。 |
| `/handling/getTimeLimitStatic`、`/handling/getComplianceData` | 异议超期和合规 | 从 ObjectionAggregate 投影。 |
| `/require/getRequireData`、`/require/timeLimitHandle` | 需求超期督导 | 从申请 / 需求 intent 投影。 |
| `/catalog/getTimeLimitStatic`、`/catalog/getTimeLimitData` | 目录超期督导 | 从 CatalogResourceAggregate 发布 / 编制事件投影。 |
| `/rule/saveOrUpdateRule` | 规则配置 | `compliance.rule.configure`。 |
| `/common/getRegulations`、`/common/getFlowTypeNodes` | 条例和流程节点 | 规则解释和证据引用，不迁通用流程引擎。 |

## 三、目标模型

### 3.1 B1.1 逻辑边界

建议新增逻辑 projection / adapter，不新增大而全运维聚合；具体物理表落地必须以 approved v4 数据模型为准：

- `compliance_signal`：从审计、回执、外部安全、监控和督导规则生成的信号。
- `risk_event_projection`：安全风险、接口异常、通道失败、异常调用、敏感识别命中等只读风险事件。
- `compliance_case`：需要人工确认和整改的合规问题，可关联目录、资源、申请、交付、异议、adapter run。
- `compliance_rule`：超期、失败率、调用异常、标准覆盖、敏感数据等规则定义；规则来源可为配置或外部系统。
- `standard_asset_projection`：标准模型、字典、规则、文档和推荐结果的候选 / evidence。
- `metric_definition_projection`：B1.1 指标定义、维度、口径和来源。
- `health_signal_projection`：服务、adapter、外部通道、任务运行健康。
- `adapter_run_record`：外部安全扫描、标准推荐、指标同步、告警接收、督导计算等执行摘要。

### 3.2 事实来源原则

| B1.1 对象 | 来源 | 禁止行为 |
| --- | --- | --- |
| 超期信号 | canonical 状态时间、SLA、审计事件 | 不在督导系统内复制主状态。 |
| 风险事件 | 安全中心 / 监控 / 审计 / 能力调用 | 不保存密钥、明文样例和敏感扫描明细。 |
| 标准资产 | standard adapter / catalog model | 不建立独立标准平台。 |
| 指标 | projection 定义、canonical 查询、外部 BI | 不直连业务库写事实。 |
| 告警 | 外部监控推送、adapter run、服务健康 | 不替代观测底座。 |
| 整改 | `compliance_case` / `objection_case` / audit | 不直接修改目录、资源、申请、交付状态。 |

### 3.3 Compliance case 状态

| 状态 | 说明 |
| --- | --- |
| `detected` | 规则或外部事件命中，待确认。 |
| `acknowledged` | 责任方确认收到。 |
| `assigned` | 已分派到组织 / 人 / adapter。 |
| `remediating` | 正在整改或等待外部处理。 |
| `resolved` | 已提交整改结果和证据。 |
| `closed` | 平台 / 监管确认关闭。 |
| `dismissed` | 误报或无需处理，需说明理由。 |

每次状态推进必须写 `audit_event` 和 `capability_call`；如涉及外部系统，保存 receipt。

## 四、Capability 设计

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `compliance.signal.ingest` | 写 | `write-trace` | 接收安全、监控、督导、adapter 信号。 |
| `risk.event.ingest` | 写 | `write-trace` | 接收风险事件和告警摘要。 |
| `compliance.rule.configure` | 写 | `approval-trace` | 配置超期、失败率、敏感、标准覆盖等规则。 |
| `compliance.case.open` | 写 | `approval-trace` | 将信号升级为人工处置 case。 |
| `compliance.case.assign` | 写 | `approval-trace` | 分派责任组织或处理人。 |
| `compliance.case.resolve` | 写 | `approval-trace` | 提交整改结果和证据。 |
| `compliance.case.close` | 写 | `approval-trace` | 关闭或驳回整改。 |
| `compliance.metric.query` | 读 | `read-trace` | 查询 B1.1 指标、趋势、组织排行。 |
| `compliance.case.query` | 读 | `read-trace` | 查询风险 / 合规 case 列表和详情。 |
| `standard.asset.sync` | 写 | `write-trace` | 同步标准模型、字典、规则、文档候选。 |
| `standard.asset.recommend` | 写 | `write-trace` | 触发外部标准推荐并保存结果摘要。 |
| `security.scan.result.sync` | 写 | `write-trace` | 同步敏感识别、分类分级、脱敏任务摘要。 |
| `adapter.health.probe` | 写 | `write-trace` | 写入服务、通道、adapter 健康检测结果。 |

消费面：

- WebUI：B1.1 合规与运营、问题处置、规则配置、高风险确认。
- REST：外部安全 / 监控 / 标准系统推送摘要。
- CLI：迁移、规则校验、指标导出、adapter 健康排障。
- MCP：Agent 查询风险证据、生成整改建议和追责摘要。
- A2A：外部安全 Agent / 标准 Agent 推送结果，必须注册为 Capability。

## 五、旧仓库到新系统映射

| 旧仓库 / 旧对象 | 新落位 | 说明 |
| --- | --- | --- |
| `datasecurity-service` 分类分级 | `standard_asset_projection` / `risk_event_projection` | 只同步资源标签和风险摘要。 |
| `datasecurity-service` 敏感识别任务 / 结果 | `security.scan.result.sync` + `adapter_run_record` | 明细、样例和敏感值不迁。 |
| `datasecurity-service` 脱敏 / 加密 / 密钥 | 外部安全 adapter | 密钥、算法配置和执行引擎不进核心。 |
| `datasecurity-service` 风险告警 | `risk_event_projection` / `compliance_signal` | 可升级为 compliance case。 |
| `indata-security-executor` 识别 / 脱敏 / 风险任务 | `adapter_run_record` | 执行器只保存摘要、状态、receipt。 |
| `standardservice-service /model` | `catalog_model` evidence / `standard_asset_projection` | 正式模型归目录模型聚合。 |
| `standardservice-service /dict` | 领域字典 evidence | 不建全局字典中心。 |
| `standardservice-service /rule` | `standard_asset_projection` / `compliance_rule` 候选 | 规则执行外部化。 |
| `standardservice-service /docu` | 对象存储 / 知识 evidence | 文档原文不进主状态表。 |
| `standardservice-service /recommend` | `standard.asset.recommend` result | 推荐结果需人工确认。 |
| `metricsmgr-service /indicator` | `metric_definition_projection` | 指标口径候选。 |
| `metricsmgr-service /dimension` | `metric_definition_projection` | 维度定义候选。 |
| `metricsmgr-service /api-service` | dataservice capability / audit | 不复造指标 API 网关。 |
| `metricsmgr-service /datasource` | 不迁连接配置 | 禁止保存明文连接串。 |
| `metricsmgr-service /scheduler` | `adapter_run_record` | 调度外部化。 |
| `dsp-monitor WarningMessage*` | `risk_event_projection` | 告警消息摘要。 |
| `dsp-monitor WarningWorkOrderRules` | `compliance_rule` 候选 | 规则需审核。 |
| `dsp-monitor MonitorResult*` | `health_signal_projection` | 健康检测结果。 |
| `dsp-monitor DatasourceInfo` | 不迁连接配置 | 只保留脱敏 endpoint ref。 |
| `dsp-esupervision` 超期 / 合规接口 | `compliance_signal` / `compliance_case` | 从 canonical 重新投影。 |
| `data-operation-board-front`、`metricsmgr-front` | B1.1 视觉输入 | 不迁前端代码。 |

## 六、迁移与验证策略

### 6.1 迁移步骤

1. 登记 `legacy_adapter_source`：`datasecurity-service`、`indata-security-executor`、`standardservice-service`、`metricsmgr-service`、`dsp-monitor`、`dsp-esupervision`。
2. 导入旧告警、风险、督导、标准、指标对象 ID 到 `legacy_object_mapping`。
3. 将告警消息、风险事件、超期记录导入为 `compliance_signal` 候选。
4. 将已处理工单、督导处理、整改说明导入为 `compliance_case` / evidence 候选。
5. 将标准模型、字典、规则、文档映射到标准资产 projection 或 `catalog_model` evidence。
6. 将指标定义、维度、口径映射为 B1.1 指标 projection。
7. 将服务拨测、adapter 执行、外部通道健康导入 `health_signal_projection` / `adapter_run_record`。
8. 排除或脱敏数据库连接、IP、账号、密码、密钥、扫描样例、日志明细和文件内部路径。
9. 对所有规则候选设置 pending，人工审核后才能生效。

### 6.2 验证样本

最小样本必须覆盖：

1. 一个申请超期记录从 `approval_case` 状态时间重新投影为 `compliance_signal`。
2. 一个异议超期记录从 `objection_case` 重新投影为 B1.1 指标。
3. 一个直达 adapter 失败记录进入通道健康 projection。
4. 一个安全敏感识别结果只保存摘要，不保存样例值。
5. 一个标准模型候选能关联到 `catalog_model`，无法解析时进入 unresolved。
6. 一个监控告警被升级为 `compliance_case` 并完成整改闭环。
7. 一个旧告警规则导入后保持 pending，不自动生效。
8. 一个 B1.1 查询只读 projection，不能调用写能力。
9. 一个 metrics 数据源连接配置被排除或脱敏。
10. 一个 B1.1 Agent 查询风险证据并生成摘要，不能直接关闭 case。

## 七、不做清单

1. 不复刻旧数据安全中心、标准服务平台、指标平台、监控告警系统、电子督导后台。
2. 不迁入数据库连接串、账号、密码、密钥、证书、内部 IP、扫描样例和日志明细。
3. 不在 zw-brain 内实现分类分级、敏感识别、脱敏、加密、密钥管理引擎。
4. 不把旧监控 / 督导状态作为目录、申请、交付、异议的新事实源。
5. 不让 B1.1 projection 反向执行业务写操作。
6. 不复造指标 API 网关、OAuth、应用中心和调度中心。
7. 不把标准服务的全局字典平台迁入核心；字典必须归属具体领域。
8. 不把外部观测底座、ES、Prometheus、XXL-Job、Nacos 配置迁为产品模型。
9. 不让规则导入后自动生效；所有生产规则必须审核并可审计。

## 八、专题差异决策

全局高风险 case 关闭门槛、标准数据权威批次和 greenfield 口径以总览方案第八节为准。本专题只保留 B1.1 合规与运营与外部安全的差异决策：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| P1 | B1.1 逻辑对象与 approved 物理模型关系 | `compliance_case` 是 B1.1 最小闭环逻辑对象；物理表、字段和聚合归属必须以 approved v4 数据模型为准。 | `risk_case` 只能作为 `compliance_case` 分类、投影视图或候选术语，不新增未批准核心事实表。 |
| P2 | 外部安全中心 API 可用性 | 不阻塞 B1.1 最小闭环；API 可用时同步摘要，不可用时支持人工 / 文件导入风险事件。 | zw-brain 不实现扫描、脱敏、加密、密钥管理引擎。 |
| P3 | B1.1 指标口径来源 | zw-brain projection 统一定义 B1.1 指标口径；旧 metrics / esupervision 作为口径参考。 | B1.1 只读消费 projection，不允许写业务状态。 |
| P4 | 外部告警接入方式 | 统一接入 `risk.event.ingest`，安全、监控、级联 adapter 以 `source_type` 区分。 | 风险事件统一去重、升级为 compliance case 和审计。 |
| P5 | 安全扫描样例数据处理 | 默认不保存明文样例；只保存摘要、风险等级、对象引用、结果哈希和受控对象存储引用。 | 原始明细保留在外部安全中心或受控对象存储，读取需额外权限和审计。 |

## 九、证据来源

- `old/08标准服务系统标准数据`
- `old/代码信息抽取/代码项目信息汇总.xlsx`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-monitor_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-monitor_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-monitor_外部SDK和接口文档.md`
- `old/old_codes/datasecurity-service/README.md`
- `old/old_codes/datasecurity-service/security-manage/src/main/java/com/inspur/indata/**/controller/*.java`
- `old/old_codes/indata-security-executor/README.md`
- `old/old_codes/indata-security-executor/src/main/java/com/inspur/indata/security/**/controller/*.java`
- `old/old_codes/standardservice-service/standard-manage/src/main/java/com/inspur/standard/controller/*.java`
- `old/old_codes/standardservice-service/standard-report/src/main/java/com/inspur/standard/report/controller/*.java`
- `old/old_codes/metricsmgr-service/src/main/java/com/inspur/cloud/platform/metric/controller/*.java`
- `old/old_codes/dsp-esupervision/dsp-esupervision-console/src/main/java/com/inspur/dsp/console/**/*.java`
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/zw-brain-data-model.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-objection-handling-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md`
