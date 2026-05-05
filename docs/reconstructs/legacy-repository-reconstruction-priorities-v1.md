# 旧平台代码仓库重构优先级总览方案 v1

> 范围：`old/代码信息抽取/代码项目信息汇总.xlsx` 中列出的旧平台代码仓库、`docs/approved/*` 中已批准的 zw-brain 重构原则，以及 `docs/reconstructs/*` 已完成的专题方案。
> 结论：zw-brain 是全新 AI 原生项目，不兼容旧 URL、旧 API、旧菜单、旧页面、旧后台形态和旧库表兼容层。旧仓库重构不按代码规模排序，而按“是否承载强状态主旅程、是否补齐 approved 聚合缺口、是否必须通过统一 Capability 暴露、是否只能作为 adapter / projection / evidence”分流。本总览是旧仓库去向、统一重构原则、Capability 命名和跨专题决策基线的全局单一事实源；各专题文档只记录专题证据、映射和差异约束。

## 一、全局重构原则

### 1.1 进入 zw-brain 核心重构的条件

旧仓库只有满足以下多数条件，才进入 canonical 聚合或正式 Capability 设计：

1. 承载目录、资源、申请、审批、交付、订阅、异议、审计、注册治理等强状态链路。
2. 能被 WebUI / REST / CLI / MCP / A2A 共用同一套 Capability contract 表达。
3. 能强化 R1 / R3 / R5 黄金链路，或支撑 P5 供给侧治理、P6 合规运营、P7 共享专区 / 专题包。
4. 旧实现中存在跨仓承重业务语义，迁入后能消除旧平台模块孤岛。
5. 能通过 `legacy_adapter_source`、`legacy_object_mapping`、`external_object_mapping`、`adapter_run_record` 留下证据，而不是复刻旧表、旧 Controller、旧菜单和旧后台。

### 1.2 默认外化或不重构的条件

以下类型默认不进入 zw-brain 核心事实模型：

1. 前端壳、门户导航、菜单、样式、组件路径和旧交互页面。
2. IAM、消息、监控、调度、PDF、应用中心、证书、短信、OAuth、SSO 等平台底座。
3. 低频、项目化、招标补齐型模块。
4. approved 已明确定位为外部依赖的能力，例如国家平台、数据治理中心、外部观测底座、外部区块链、集团推理平台。
5. 只能作为运营投影、只读证据、迁移线索或执行器摘要的仓库。

### 1.3 旧平台业务逻辑继承原则

进入实施阶段时，旧平台代码实现是业务逻辑的默认依据：状态流转、字段含义、SLA、审核分支、上报 / 下发规则、统计口径和异常处理，原则上按旧平台真实实现迁移为新 Capability 行为。

只有当旧实现触碰以下原则性边界时，才拉出独立决策，不允许在方案或代码中静默继承：

1. 把门户、菜单、按钮权限、Dashboard、监控、消息、调度等投影 / 底座能力当成业务事实源。
2. 绕过 canonical 聚合，直接覆盖目录、资源、申请、交付、异议等主状态。
3. 复制国家平台、IAM、数据治理中心、监控中心、标准平台、指标平台等已批准外部依赖。
4. 无法通过统一 Capability contract 暴露到 WebUI / REST / CLI / MCP / A2A。
5. 不能满足写动作审计、外部 receipt 留痕、敏感信息不入库等硬约束。
6. 包含密码、Token、密钥、证书、内部 IP、连接串、扫描样例、日志明细等敏感配置或数据。

### 1.4 全新项目口径

- 不兼容旧 URL、旧 API、旧菜单、旧页面、旧后台形态和旧库表兼容层。
- 不为了迁移便利保留旧系统切分；旧仓库只是证据来源，不是新系统边界。
- 不把 projection 反向写成事实源；Dashboard、P6、P7 读模型均只能消费 canonical、adapter receipt 和 audit evidence。
- 不为历史兼容新增 shim、同步双写或旧权限树适配层；需要保留的业务语义必须转写为新 Capability、adapter 或 evidence。

## 二、统一 Capability 与 adapter 命名基线

| 领域 | 统一命名 | 说明 |
| --- | --- | --- |
| Registry 包注册 | `capability.package.register` | 注册能力包草稿。 |
| Registry 版本提交 | `capability.version.submit` | 提交能力版本审核。 |
| Registry 版本审核 | `capability.version.review` | 审核、驳回、禁用、回滚能力版本。 |
| Registry 暴露配置 | `capability.exposure.configure` | 配置版本暴露到 WebUI / REST / CLI / MCP / A2A。 |
| 租户策略裁决 | `tenant.policy.evaluate` | 判断调用者、组织、角色、消费面和目标对象是否可调用能力。 |
| 级联重放 | `adapter.cascade.replay` | 按失败日志或旧对象映射重放级联处理。 |

禁止在方案和实现中继续使用旧的 exposure 注册 / 审核漂移命名，或带 legacy 前缀的 cascade replay 命名。

## 三、已覆盖仓库与典型重构模式

| 已有方案 | 覆盖旧仓库 | 典型模式 |
| --- | --- | --- |
| `dsp-catalog3-metadata3-reconstruction-plan-v1.md` | `dsp-catalog3`、`dsp-metadata3` | 目录、元数据、资源、发布、质量、血缘收敛为 `CatalogResourceAggregate` 与资源证据，不复造目录中心 / 元数据中心。 |
| `dsp-exchange-reconstruction-plan-v1.md` | `dsp-require`、`dsp-supply`、`dsp-exchange` | 需求、申请、审批、授权、交付、订阅收敛为 `ApplicationApprovalAggregate` 与 `DeliveryAggregate`，不兼容旧 URL。 |
| `dsp-dataservice-reconstruction-plan-v1.md` | `dsp-dataservice` | 接口服务、服务发布、调用证据、服务交付收敛为可注册、可审计的服务型 Capability。 |

统一方法：先识别用户旅程和承重语义，再决定聚合边界；强状态进入 canonical 聚合，统计、看板、门户显示进入 projection；外部副作用通过 adapter 或外部执行器执行；所有写动作必须审计，外部调用必须留下 receipt / evidence。

## 四、重点重构专题索引

| 优先级 | 专题方案 | 覆盖旧仓库 | 新系统落位 |
| --- | --- | --- | --- |
| P0 | `dsp-objection-handling-reconstruction-plan-v1.md` | `dsp-objection-handling` | `ObjectionAggregate` + `AuditAggregate`，补齐异议强状态闭环。 |
| P0 | `dsp-data-connect-cascade-reconstruction-plan-v1.md` | `dsp-data-connect`、`dsp-cascade-platform`、`dsp-cascade-down` | 国家 / 上级直达与级联 adapter、external mapping、receipt、replay。 |
| P1 | `dsp-bsp-manage-governance-reconstruction-plan-v1.md` | `dsp-bsp`、`dsp-manage`、`dsp-ucenter` | `brain_registry`、`tenant_capability_policy`、组织 / 用户 / 角色只读投影、外部 IAM adapter。 |
| P1 | `dsp-sharezone-topic-package-reconstruction-plan-v1.md` | `dsp-sharezone`、`dsp-example`、`dsp-basesubject` | P7 `TopicPackage` 投影、专题 evidence、可见性策略、复用入口。 |
| P2 | `compliance-ops-adapters-reconstruction-plan-v1.md` | `datasecurity-service`、`indata-security-executor`、`standardservice-service`、`metricsmgr-service`、`data-operation-board-front`、`dsp-monitor`、`dsp-esupervision` | P6 合规运营 projection、标准资产候选、风险事件、健康信号、最小 `compliance_case` 闭环。 |

## 五、Excel 全量仓库覆盖矩阵

| 旧仓库 | 类型 / API | 重构去向 | 优先级 | 说明 |
| --- | ---: | --- | --- | --- |
| `app-center-server` | 后端 / 63 | 外部应用目录 / Capability 来源参考 | P3 | 应用管理不是政务数据主旅程；最多为外部应用注册提供 adapter 线索。 |
| `app-center-web` | 前端 / - | 不重构 | P3 | 前端壳不进入核心库表。 |
| `catalog-front` | 前端 / - | WebUI 体验参考，不迁代码 | P3 | 新 WebUI 应按客户级体验重做，不继承 Angular 页面层级。 |
| `data-operation-board-front` | 前端 / - | Dashboard 视觉输入 | P2 | 只服务运营看板 projection，不成为主事实源。 |
| `dataresource` | 后端 / 25 | 默认不重构，必要时作为专题包内容源 | P3 | 旧数据资源库是招标补齐型建库向导，approved 已倾向不默认恢复。 |
| `datasecurity-front` | 前端 / - | 不重构 | P3 | 安全前端不进入主产品核心。 |
| `datasecurity-service` | 后端 / 225 | P6 风险监测 / 外部安全 adapter | P2 | 去重分类分级 / 脱敏 / 加密引擎，只保留风险摘要、处置证据和审计联动。 |
| `dsp-basesubject` | 后端 / 388 | 共享专区 / 专题包内容源候选 | P1 | 专题库、档案、标准和统计只作为专题素材或标准资产 evidence。 |
| `dsp-blockchain` | 后端 / 27 | 区块链锚定 adapter | P3 | v4 已决定 `anchor_outbox` 异步锚定，不复刻区块链系统。 |
| `dsp-bsp` | 后端 / 628 | 最小租户策略与注册治理 | P1 | 只抽取组织、角色、策略裁决语义，不复刻完整基础支撑后台。 |
| `dsp-cascade-down` | 后端 / 2 | 上下级直达 / 级联 adapter | P0 | 与 `dsp-data-connect`、`dsp-cascade-platform` 合并分析。 |
| `dsp-cascade-platform` | 后端 / 227 | 上下级直达 / 级联 adapter | P0 | 承接国家 / 上级双向通道、回执与督办证据。 |
| `dsp-catalog3` | 后端 / 1067 | 已覆盖：目录 / 元数据重构方案 | 已完成 | 见 `dsp-catalog3-metadata3-reconstruction-plan-v1.md`。 |
| `dsp-catalog-platform` | 后端 / 47 | 已纳入目录语义，不单独重构 | P2 | approved 明确不原样迁入；承重语义已收敛到 CatalogResourceAggregate。 |
| `dsp-data-connect` | 后端 / 562 | 上下级直达 / 级联 adapter | P0 | `dsp_connect.xml` 多次被数据模型和 exchange 方案引用，需形成独立 adapter 边界。 |
| `dsp-dataservice` | 后端 / 357 | 已覆盖：服务型 Capability 重构方案 | 已完成 | 见 `dsp-dataservice-reconstruction-plan-v1.md`。 |
| `dsp-esupervision` | 后端 / 47 | 合规督导 projection / adapter | P2 | 合规预警规则可收敛为 P6 能力，不复刻督导后台。 |
| `dsp-example` | 后端 / 125 | 共享专区 / 专题包内容源 | P1 | 应用案例只保留可验证的复用 / 上报证据。 |
| `dsp-exchange` | 后端 / 299 | 已覆盖：申请 / 交付重构方案 | 已完成 | 见 `dsp-exchange-reconstruction-plan-v1.md`。 |
| `dsp-manage` | 后端 / 403 | 最小租户策略与注册治理 | P1 | 与 `dsp-bsp` / `dsp-ucenter` 合并抽取治理语义。 |
| `dsp-metadata3` | 后端 / 416 | 已覆盖：目录 / 元数据重构方案 | 已完成 | 见 `dsp-catalog3-metadata3-reconstruction-plan-v1.md`。 |
| `dsp-monitor` | 后端 / 587 | 外部观测底座 / P6 投影 | P2 | 监控告警不是主旅程聚合，不能反向驱动业务状态。 |
| `dsp-objection-handling` | 后端 / 104 | 异议闭环专题 | P0 | 补齐 `ObjectionAggregate` 强状态链路。 |
| `dsp-pdf` | 后端 / 19 | 对象存储 + 文档服务 adapter | P3 | 文件生成 / 预览不是核心业务模型。 |
| `dsp-portal-backend` | 后端 / 38 | 门户投影输入，不重构 | P3 | 门户后台不能成为新事实源。 |
| `dsp-require` | 后端 / 223 | 已覆盖：申请 / 交付重构方案 | 已完成 | 见 `dsp-exchange-reconstruction-plan-v1.md`。 |
| `dsp-sharezone` | 后端 / 22 | 共享专区 / 专题包投影 | P1 | P7 必保留，但只做主题化聚合和策略投影。 |
| `dsp-supply` | 后端 / 174 | 已覆盖：申请 / 交付重构方案 | 已完成 | 见 `dsp-exchange-reconstruction-plan-v1.md`。 |
| `dsp-ucenter` | 后端 / 108 | 组织 / 用户投影与策略 adapter | P1 | 不自建完整 IAM，抽取权威组织源映射和策略裁决。 |
| `indata-security-executor` | 后端 / 9 | 安全风险执行器 adapter | P2 | 与 `datasecurity-service` 合并处理，只保留任务摘要、状态和 receipt。 |
| `message-center` | 后端 / 52 | 外部通知 adapter | P3 | 通知不是业务主状态；由异议、审批、督办调用。 |
| `metricsmgr-front` | 前端 / - | Dashboard 视觉输入 | P2 | 不迁前端代码，只参考指标展示诉求。 |
| `metricsmgr-service` | 后端 / 99 | 指标 projection / P6 adapter | P2 | 未封版，不能把直连业务库的指标平台迁成事实源。 |
| `portal-vue` | 前端 / - | 不重构 | P3 | 前端壳与菜单结构不继承。 |
| `staging` | 前端 / - | 不重构 | P3 | 前端 staging 不进入核心设计。 |
| `standardservice-front` | 前端 / - | 不重构 | P3 | 标准前端不进入核心。 |
| `standardservice-service` | 后端 / 86 | 标准资产只读 adapter | P2 | 数据元、标准规则进入 `CatalogModel` / `standard_asset_projection` 候选，不复造标准平台。 |
| `xxl-job` | 后端 / 34 | 外部调度器 / 执行器线索 | P3 | 调度只保存引用和回执，不进入用户主旅程。 |

## 六、默认外部化或不重构仓库

| 仓库 | 建议去向 | 原因 |
| --- | --- | --- |
| `app-center-server` / `app-center-web` | 外部应用目录 / 注册输入 | 不属于政务数据主旅程；最多为 Capability 来源提供参考。 |
| `dsp-portal-backend` / `portal-vue` / `catalog-front` / `staging` / 各类 front | 前端实现输入 | 前端状态不是权威事实源；WebUI 应按 zw-brain 客户级体验重做。 |
| `message-center` | 外部通知 adapter | 通知不是业务主状态；异议督办、审批提醒只引用通知能力。 |
| `dsp-pdf` | 对象存储 + 文档服务 adapter | 文件生成 / 预览不应成为核心业务模型。 |
| `dsp-blockchain` | `anchor_outbox` 的外部 adapter | v4 已决定区块链异步锚定、可插拔，不阻塞主业务。 |
| `xxl-job` | 外部调度器 / 执行器线索 | 调度不进入用户主旅程，核心只保存任务引用和回执。 |
| `dataresource` | 默认不重构，必要时作为专题包内容源 | 旧数据资源库被列为低价值 / 招标补齐型能力，不默认恢复。 |
| `app-center-*` | 不进入核心重构 | 应用管理不是 zw-brain 的主产品边界。 |

## 七、专题方案产出状态

1. `dsp-objection-handling-reconstruction-plan-v1.md`：已产出，补齐 J4 异议强状态闭环。
2. `dsp-data-connect-cascade-reconstruction-plan-v1.md`：已产出，明确国家平台 / 上下级级联 adapter 与回执边界。
3. `dsp-bsp-manage-governance-reconstruction-plan-v1.md`：已产出，抽取最小租户策略、能力注册治理和组织投影。
4. `dsp-sharezone-topic-package-reconstruction-plan-v1.md`：已产出，把共享专区、专题包、应用案例、专题库收敛为 P7 投影与可见性策略。
5. `compliance-ops-adapters-reconstruction-plan-v1.md`：已产出，处理安全、标准、指标、监控、督导等 P6 外部 adapter。

本轮复查结论：`old/代码信息抽取/代码项目信息汇总.xlsx` 中 P0 / P1 / P2 重点仓库均已有总览去向和对应专题方案；剩余 P3 仓库按本文第六节默认外部化或不重构，不再新增重点重构专题。

## 八、实施前决策基线

以下事项已形成全局实施基线。专题文档只补充本专题差异，不重复定义跨专题规则。

| 编号 | 决策项 | 已定基线 | 实施约束 |
| --- | --- | --- | --- |
| D1 | 身份 / 租户权威源 | 外部 IAM 为权威源；旧 BSP / ucenter 只作投影和候选策略；`tenant_id` 由 zw-brain 租户投影 / 环境注册统一管理。 | 不自建完整 IAM，不迁密码 / Token；旧权限必须人工审核后才能进入 `tenant_capability_policy`。 |
| D2 | 国家直达 adapter 部署边界 | 国家直达 / 级联 adapter 独立部署在政务外网逻辑隔离可达区，zw-brain 主服务通过受控内部接口调用。 | 主服务不直接持有国家平台地址、证书、API key；敏感配置只在 adapter 环境中以密钥引用注入。 |
| D3 | 外部下发对象生效方式 | 外部申请、目录、资源默认先进入候选池 / receipt / mapping，不自动成为 canonical 事实。 | 经规则校验或人工确认后，才生成 `application_record`、目录 / 资源候选发布或其他主链路对象。 |
| D4 | P6 高风险 case 关闭门槛 | 高风险 `compliance_case` 双人复核；普通 case 平台单人关闭；监管 / 敏感场景需监管或指定角色确认。 | 每次关闭必须写 `audit_event` 和 `capability_call`，外部处置需保存 receipt。 |
| D5 | 专题包发布审核机制 | 专题包发布、下线、可见性策略变更统一走 capability review；高影响专题包双人审核。 | 专题包不得绕过 `tenant_capability_policy` 直接授权资源使用。 |
| D6 | 标准数据权威批次 | `old/08标准服务系统标准数据` 全量先导入候选，人工确认后标记 authoritative 才生效。 | 未确认数据元 / 字典只能作为 `standard_asset_projection` 候选，不得直接进入生产 `CatalogModel` 事实。 |

## 九、证据来源

- `old/代码信息抽取/代码项目信息汇总.xlsx`
- `old/integrated-bigdata-platform/README.md`
- `old/12-datastructure/dsp_connect.xml`
- `old/12-datastructure/dsp_handling.xml`
- `old/12-datastructure/dsp_bsp.xml`
- `old/2024-06-28全国一体化政务数据共享数据直达接口规范v0.55.docx`
- `old/08标准服务系统标准数据`
- `docs/approved/zw-brain-architecture-v4-gpt55.md`
- `docs/approved/zw-brain-data-model-v4-gpt55.md`
- `docs/approved/zw-brain-golden-path-r1-r3-r5-v1.md`
- `docs/approved/research-yibiaotong-zw-brain-v4.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md`
