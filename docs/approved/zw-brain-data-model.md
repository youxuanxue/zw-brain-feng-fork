---
doc_id: design-zw-brain-data-model
status: approved
gate: approved
approved_by: xuejiao02
authors:
  - 薛娇（产品研发负责人）
  - Claude Code (claude-opus-4-7) — 设计协作
related_docs:
  - docs/approved/zw-brain-architecture.md
  - docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md
  - docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md
  - old/代码信息抽取/代码信息抽取-27newbranch/All-Project_数据库表结构文档.md
  - old/12-datastructure/dsp_catalog.xml
  - old/12-datastructure/dsp_connect.xml
  - old/12-datastructure/dsp_handling.xml
  - old/12-datastructure/dsp_bsp.xml
  - old/12-datastructure/dsp_block.xml
related_prs: []
related_commits: []
self_review_rounds: 3
phase_after_approval: Wave 0（先打通 Catalog → Application → Approval → Delivery → Audit；Objection 与最小注册治理进入后续波次）
---

# 政务数据大脑（zw-brain）数据模型与数据库设计

> 设计目标：把 `docs/approved/zw-brain-architecture.md` 的 Jobs / 确定性自动化运营和运维 / 合规内建 / 单一 Capability 契约，具体收敛为可落地的 canonical data model、Phase 1 物理库表边界，以及 legacy 适配映射规则。

---

## 一、约束来源与结论先行

### 1.1 本文直接服从的架构基线硬约束

本文不自创另一套数据库哲学，直接服从 `docs/approved/zw-brain-architecture.md` 的以下约束：

1. **模型围绕旅程与审计组织，不围绕 legacy 表名组织。**
2. **目录、申请、交付、异议都是强状态领域，必须保留显式状态机。**
3. **每次 Capability 调用都必须能回放到实体变化与审计事件。**
4. **legacy schema 只作为 adapter 输入面，不再成为新的业务写入口。**
5. **Phase 1 只收敛关键聚合边界，不把所有概念一次性膨胀成独立系统。**
6. **IAM / 组织 / 权限 / 区块链 / 推理平台 / 国家平台继续作为外部底座，不在 zw-brain 内复造。**其中 IAF IAM 与本地 Governance、租户 / 用户 / 组织 / 角色投影、旧 BSP / ucenter / manage 边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。
7. **控制面必须存在，但保持纤薄；Capability Registry 是治理事实源，不是普通用户产品首页。**

### 1.2 数据层总设计结论

本设计采用以下落地结论：

- **Canonical DB 选型：PostgreSQL**，承载强状态聚合、事务一致性、JSONB 快照、审计回放索引。
- **Phase 1 物理形态：单 PostgreSQL 集群 + 分 schema**，而不是一开始拆多库多服务；逻辑边界先清晰，物理拆分后移。
- **Schema 分层：**
  - `brain_core`：主旅程聚合与状态机
  - `brain_audit`：Capability 调用、审计事件、回执、上链 outbox
  - `brain_registry`：Capability 包注册、版本、暴露、adapter 映射
- **对象存储单独承载附件 / 回执原件 / 证据文件**，数据库只存元数据与引用。
- **legacy MySQL / XML / 外部接口全部只读接入**，通过 adapter 转译成 canonical 视图与映射证据。
- **不在新库里重建完整用户、角色、菜单、门户、监控、消息中心 schema**；仅保留业务执行和 Governance 所需的本地租户 / 组织 / 用户 / 角色投影、IAM 绑定、策略裁决和审计快照，具体治理边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。
- **Wave 0 只落首条黄金链路与 Registry 最小 schema**；异议闭环与更完整的注册治理按架构基线路线图后置到 Wave 2。
- **数据模型不仅服务存储，还必须支撑原生 WebUI、REST、CLI、MCP、A2A 五消费面的投影生成**；任何页面、接口、命令、工具、agent action 若无法回指同一 capability 与同一聚合事实源，都不符合架构基线。

### 1.3 为什么 Canonical DB 选 PostgreSQL

在架构基线约束下，PostgreSQL 比继续沿用 legacy 的多套 MySQL 更符合 Jobs / 确定性自动化运营和运维：

1. **强状态聚合需要严格事务与约束。** 申请、审批、交付、异议的状态推进需要在同一事务里同时写业务实体、审计事件、回执 outbox。
2. **CatalogModel / Capability contract / 审计快照天然需要 JSONB。** 这些是结构化但不适合被拆成过多稀碎列的内容，PostgreSQL 对 JSONB、GIN 索引、部分索引更友好。
3. **Phase 1 需要“少运维、强边界”。** 单集群分 schema 既能保持逻辑清晰，也符合确定性自动化运营和运维的最小运维面。
4. **后续分库演进自然。** 当 `brain_audit` 或 `brain_registry` 增长到独立边界时，可按 schema 平滑拆出，不影响领域模型本身。

### 1.4 本文额外回答的产品问题

本文不仅回答"表怎么建"，还必须回答以下架构基线下的产品问题：

1. **J1 / J2 / B1 各自由哪些聚合与 read model 支撑**。
2. **P1-P5 / P7 + B1.1 / B1.2 八个原生 WebUI 页面依赖哪些事实源与派生视图**。
3. **同一 capability 如何同时投影到 REST、CLI、MCP、A2A，而不复制业务逻辑**。
4. **哪些数据只允许作为投影存在，不能反向长成新的业务状态机**。
5. **哪些地方必须让 AI 只做减摩，不得吃掉结构化页面与责任边界**。

因此，本文的优化目标不是“数据库越完整越好”，而是：**让最少的持久化边界支撑最完整的核心旅程与五消费面投影**。

---

## 二、核心旅程、页面与五消费面覆盖矩阵

> 信息架构对齐：J1 找数→用数 / J2 挂数→维数 两条核心旅程 + B1 看全局→处异常 后台支撑面（B1.1 合规与运营 / B1.2 接入扩展中心）。详见 `docs/approved/zw-brain-architecture.md` §5.1。

### 2.1 旅程 / 后台面 → 聚合 → 页面覆盖

| 旅程 / 后台面 | WebUI 页面 | 主要聚合 / 表 | 说明 |
|--------------|-----------|--------------|------|
| **J1 找数→用数** | P1 工作台、P2 资源发现、P3 申请/审批/跟踪、P4 交付/交换、P7 共享专区 | `catalog_entry`, `catalog_item`, `resource_asset`, `application_record`, `application_attachment`, `approval_case`, `approval_step`, `approval_decision`, `delivery_task`, `delivery_receipt`, `delivery_notice_projection`, `audit_receipt`（Wave 0 必选）；`delivery_attempt`, `delivery_subscription`（Wave 1 补齐，见 §11.1-11.2） | 用户视角的"找 → 申请 → 拿"5 步骨干合并为一条核心旅程；含异议子流程 + 供需对接子流程；含有条件 / 无条件 / 不予共享 3 种 `share_type`（详见 architecture.md §3.3） |
| **J2 挂数→维数** | P1 工作台、P5 提供方管理、P7 共享专区 | `catalog_model`, `catalog_entry`, `catalog_entry_version`, `resource_asset`, `objection_*`（Wave 2） | 提供方编目 / 资源挂接 / 部门审 / 平台发布 / 异议处理 |
| **B1.1 合规与运营** | B1.1 合规与运营、P1 工作台 | `capability_call`, `audit_event`, `audit_receipt`, `anchor_outbox`, `service_invocation_metric_projection`, `gateway_runtime_status_projection` | 仅管理员/审计员；面向审计、统计、异常、追责，读的是审计事实和审计派生投影；不是消息通知；运行监控由集团统一运维监控平台承担（外部依赖） |
| **B1.2 接入扩展中心** | B1.2 接入扩展中心 | `capability_package`, `capability_version`, `capability_exposure`, `capability_review_record`, `tenant_capability_policy` | 仅管理员；后台支撑面；不进入普通用户主导航心智 |

> 网关与调用统计投影（`gateway_runtime_status_projection` / `service_invocation_metric_projection`）由 B1.1 合规与运营消费。

### 2.2 五消费面 → 同一 capability 的数据依赖

| 消费面 | 直接依赖 | 派生方式 | 不允许的做法 |
|--------|---------|---------|-------------|
| WebUI | `brain_core` + `brain_audit` + 必要 projection | capability 组装为页面动作、卡片、时间线、表单 | 页面绕过 command 直接写库 |
| REST | 同一 capability contract | 自动派生 OpenAPI / REST 路由 | 单独再写一套 REST 业务逻辑 |
| CLI | 同一 capability contract | 自动派生命令、参数、输出格式 | CLI 自己维护另一套状态推进 |
| MCP | 同一 capability contract | 自动投影为 tools / resources | MCP 专用实现偏离主状态机 |
| A2A | 同一 capability contract | 自动投影为 agent action / card | 为 A2A 复制一套能力模型 |

### 2.3 原生 WebUI 页面需要哪些数据形态

| 页面 | 主数据形态 | 是否允许写状态 | 备注 |
|------|-----------|--------------|------|
| P1 工作台 | 待办投影、最近上下文、告警摘要、回执摘要 | 否 | 工作台是聚合视图，不是新状态机 |
| P2 资源发现 | 检索 projection + `catalog_entry` / `resource_asset` 详情 | 否 | 搜索结果是投影，详情回到事实源 |
| P3 申请/审批/跟踪 | `application_record`、`approval_case`、`audit_receipt` | 是 | 所有提交、补件、审批都必须经 capability |
| P4 交付/交换/直达 | `delivery_task`、`delivery_receipt`、`delivery_subscription` | 是 | 状态解释可由 AI 辅助，但不能替代时间线与回执 |
| P5 提供方管理 | `catalog_model`、`catalog_entry`、`resource_asset`、`objection_*` | 是 | 编目、发布、下线、异议处理都属于强状态域 |
| P7 共享专区/专题包 | 专题 projection、目录/资源投影 | 否 | 主题化聚合，不长新状态机 |
| **B1.1 合规与运营** | `capability_call`、`audit_event`、`audit_receipt`、统计投影 | 否 | 仅管理员/审计员；以读为主，结论必须回指证据 |
| **B1.2 接入扩展中心** | `capability_package`、`capability_version`、`capability_exposure`、`tenant_capability_policy` | 是 | 仅管理员；后台治理面 |

### 2.4 什么进入 canonical model，什么不进入

#### 2.4.1 进入 canonical model 的领域

仅以下领域进入新平台核心一等持久化边界：

- 目录模型与目录发布
- 资源定义与交付绑定
- 申请单与审批轨迹
- 交付任务、订阅与回执
- 异议工单、调查过程与评价
- Capability 包注册治理
- 全量审计事件与上链 outbox
- 最小租户 / 组织投影

#### 2.4.2 不进入 canonical model 的 legacy 模块

以下 legacy 模块默认不重构为新平台核心业务表，只保留为外部底座、读侧投影或后续长尾扩展输入：

- `dsp-bsp` / `dsp-ucenter` 的完整用户、角色、权限、菜单、配置体系
- `message-center` 的完整消息中心模型
- `dsp-monitor` 的完整监控告警模型
- `app-center-server` / `app-center-web` 的应用中心模型
- `dsp-pdf` 的文档管理系统模型
- `dsp-example`、`dsp-perform`、大部分门户运营类模型
- 旧门户菜单、专题、资讯、帮助、公告、评分等前台岛模型

这些能力在架构基线中不是"消失"，而是：

- 作为外部系统继续存在，或
- 以 read model / adapter 的方式喂给 P1 / P7 / B1.1 页面，或
- 在确有高频价值时以外部 Capability 包注册进入。

### 2.5 Jobs / 确定性自动化运营和运维 数据模型验收清单

任何新增表、状态机或投影，在进入本文前都应回答以下问题：

1. **它服务的是哪条核心旅程或支撑面？** 若不能回指 J1 / J2 / B1，默认不进核心模型。
2. **它是事实源还是投影？** 若只是为了页面方便展示，应优先做 projection，而不是新增聚合根。
3. **它是否能同时支撑 WebUI、REST、CLI、MCP、A2A 的同一 capability 投影？** 若不能，说明边界切错了。
4. **它是否让普通用户产品心智变复杂？** 若新增的是后台岛、门户残留或长尾管理面，默认外部化。
5. **它是否降低确定性自动化运转效率？** 若新增后需要更多人工同步、更多双写、更多专用实现链，就违背确定性自动化运营和运维原则。
6. **它是否让 AI 夺主？** 若一个字段或表存在只是为了给聊天式入口兜底，而不是支撑结构化页面与责任边界，应判定为偏离基线。

## 三、领域概念、聚合边界与 legacy 语义映射

### 3.1 概念层 → 聚合层 → 物理表组

| 概念层 | Phase 1 聚合边界 | 主要新表 | legacy 来源类别 |
|------|----------------|---------|----------------|
| `CatalogModel` | `CatalogResourceAggregate` | `catalog_model`, `catalog_model_step`, `catalog_model_field` | 目录模板、字段配置与标准业务表；catalog3 / metadata3 专题细节以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准 |
| `Catalog` | `CatalogResourceAggregate` | `catalog_entry`, `catalog_entry_version`, `catalog_item` | 目录本体、目录版本、目录信息项与基本要素目录证据；专题细节以 reconstruction plan 为准 |
| `Resource` | `CatalogResourceAggregate` | `resource_asset`, `resource_channel_binding` | 数据资源、API 服务、库表/文件/链接资源与通道绑定证据；dataservice 与 catalog/metadata 专题细节分别以 reconstructs 文档为准 |
| `Application` | `ApplicationApprovalAggregate` | `application_record`, `application_attachment` | 资源申请、供需申请、附件与申请函证据；专题细节以 reconstructs 文档为准 |
| `ApprovalTask` | `ApplicationApprovalAggregate` | `approval_case`, `approval_step`, `approval_decision` | 目录、资源、服务、应用和通用审批流证据；专题细节以 reconstructs 文档为准 |
| `DeliveryTask` | `DeliveryAggregate` | `delivery_task`, `delivery_attempt`, `delivery_receipt`, `delivery_subscription` | 交换、订阅、级联、区块链与交付回执证据 |
| `ObjectionCase` | `ObjectionAggregate` | `objection_case`, `objection_evidence`, `objection_process`, `objection_evaluation` | 异议、互动反馈与纠错证据 |
| `AuditEvent` | `AuditAggregate` | `capability_call`, `audit_event`, `audit_receipt`, `anchor_outbox` | 操作日志、系统日志、级联日志、区块链日志证据 |
| `CapabilityPackage` | `CapabilityRegistryAggregate` | `capability_package`, `capability_version`, `capability_exposure`, `capability_review_record`, `tenant_capability_policy` | 外部 package manifest, hub-compatible package 元数据 |
| `TenantOrg` | `CapabilityRegistryAggregate` / shared substrate | `tenant_org_projection` | 组织、区划与租户投影证据 |

> 口径说明：`TenantOrg` 在概念上仍属于平台底座 / registry 相关治理上下文，而 `tenant_org_projection` 在物理上放入 `brain_core`，只是为了让主旅程查询、审批路由与历史回放获得稳定本地投影；它不是 IAM 权威源，也不改变 `TenantOrg` 的平台底座属性。

### 3.2 必须保留为显式状态机的 legacy 语义

旧库清楚证明以下语义不能被聊天式扁平化，必须在新模型中保留显式状态：

- **目录生命周期**：草稿、待审、发布、变更、撤销、驳回、归档
- **申请生命周期**：草稿、提交、补件、审批中、通过、驳回、撤回、交付中、生效、关闭
- **审批轨迹**：谁提单、谁审批、在哪一步、什么意见、何时通过/驳回/退回
- **交付生命周期**：排队、开通、执行、等待回执、成功、部分失败、失败、取消、过期
- **异议生命周期**：草稿、受理、平台核查、提供方核查、已解决、驳回、关闭、评价
- **审计回放链**：调用来源、目标实体、前后状态哈希、确认回执、审批回执、交付回执、上链回执

---

## 四、Phase 1 物理部署建议

### 4.1 推荐部署形态

**Phase 1 推荐形态：**

- 一个 PostgreSQL 集群
- 三个 schema：`brain_core`、`brain_audit`、`brain_registry`
- 一个 Redis（缓存 / 短期上下文 / 幂等键）
- 一个对象存储（附件、证据、回执原件）
- 只读 legacy adapter（MySQL / 文件 / 外部 API）

### 4.2 为什么先分 schema，不先分库

架构基线明确要求"概念层完整，物理层分波次"。因此 Phase 1 的最优解不是按概念拆很多库，而是：

- 在数据库里先把边界画对
- 在服务编排里先把 command / domain / audit 串对
- 在运维上保持最小面

待以下任一条件出现，再考虑拆物理库：

- `brain_audit` 容量或写入压过主库
- `brain_registry` 需要独立发布节奏
- 交付链路出现明显的吞吐隔离诉求

---

## 五、跨表通用设计约定

### 5.1 主键与时间

- 所有核心实体主键使用 `UUID`
- 所有业务时间使用 `TIMESTAMPTZ`
- 所有聚合根带 `row_version INT NOT NULL DEFAULT 0` 做乐观锁
- 受监管领域默认**不做物理删除**，通过状态终态 + `archived_at` 表达退出生命周期

### 5.2 租户与组织

除跨租户公共 registry 根表外，所有核心聚合根至少包含：

- `tenant_id VARCHAR(64) NOT NULL`
- `owner_org_id VARCHAR(64)` 或等价业务组织字段
- 必要时保留 `owner_org_snapshot JSONB`，防止 IAF IAM、组织主数据或 Governance 投影变更导致历史回放失真

这里的唯一例外是 `brain_registry` 中的**跨租户公共事实源**，例如 `capability_package`、`capability_version`、`legacy_adapter_source`：

- 它们描述的是平台级 capability 与 adapter 元信息，而不是某个租户的业务状态
- 真正的租户生效边界落在 `tenant_capability_policy`
- 因此它们可以不带 `tenant_id`，但任何进入租户执行面的启停、暴露、策略覆盖，都必须显式回到带 `tenant_id` 的租户策略表

### 5.3 外部底座引用策略

- 不复制 IAM 的完整用户 / 角色 / 权限表；只保存 Governance 所需投影、绑定和策略候选
- 业务表只保存**外部 ID + 当时快照**
- 组织树和用户 / 角色关系作为 Governance 本地投影管理，不成为认证权威源
- IAF IAM、本地 Governance、旧 BSP / ucenter / manage 投影和菜单权限迁移边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准
- 任何外部系统连接信息只保存引用，不保存明文密钥

### 5.4 JSONB 使用边界

适合放 JSONB：

- catalog/version 快照
- capability schema 与 manifest
- actor / org snapshot
- delivery request / response payload
- 审计证据与 receipt payload
- legacy 映射证据

不放 JSONB 的内容：

- 主状态字段
- 关键检索字段
- 租户、组织、资源、申请、审批主键及关联
- 高频筛选项

### 5.5 幂等与回放

- 每次写 Capability 调用都生成 `capability_call`
- 每次聚合状态变更都必须写 `audit_event`
- 需要对外确认或存证的动作再生成 `audit_receipt`
- 区块链 / 外部监管回执通过 `anchor_outbox` 异步推进，禁止因外链不可用阻塞本地审计落库

---

## 六、数据库 schema 设计

### 6.1 `brain_core`：主旅程与状态机

#### 6.1.1 `tenant_org_projection`

用途：保存 IAF IAM、组织主数据或旧 BSP 导入形成的 Governance 本地组织投影，用于业务读取、历史回放、策略裁决输入和导入对账；不作为 IAM 认证权威源。具体治理边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| org_id | VARCHAR(64) | NOT NULL | 外部组织 ID |
| parent_org_id | VARCHAR(64) |  | 父组织 ID |
| org_name | VARCHAR(200) | NOT NULL | 组织名称 |
| region_code | VARCHAR(32) |  | 区划编码 |
| region_name | VARCHAR(64) |  | 区划名称 |
| tree_code | VARCHAR(512) |  | 组织路径 |
| source_system | VARCHAR(32) | NOT NULL | 来源系统，默认 `iam` |
| snapshot_json | JSONB | NOT NULL | 原始组织快照 |
| synced_at | TIMESTAMPTZ | NOT NULL | 最近同步时间 |

约束与索引：

- `UNIQUE (tenant_id, org_id)`
- `INDEX (tenant_id, region_code)`

legacy 对应：`sys_department`, `sys_region`, `portal_organization`, `block_org`

#### 6.1.2 `blob_object`

用途：承载附件、申请函、证据文件、回执原件等对象存储元数据。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| storage_provider | VARCHAR(32) | NOT NULL | `minio/oss/s3/local` |
| bucket | VARCHAR(128) | NOT NULL | 桶名 |
| object_key | VARCHAR(512) | NOT NULL | 对象键 |
| file_name | VARCHAR(256) | NOT NULL | 原始文件名 |
| media_type | VARCHAR(128) |  | MIME 类型 |
| size_bytes | BIGINT | NOT NULL | 文件大小 |
| checksum_sha256 | CHAR(64) |  | 内容哈希 |
| source_kind | VARCHAR(32) | NOT NULL | `upload/generated/legacy-import` |
| created_by | JSONB | NOT NULL | 上传者快照 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

约束与索引：

- `UNIQUE (storage_provider, bucket, object_key)`
- `INDEX (tenant_id, created_at)`

legacy 对应：附件与对象存储类 legacy 证据；catalog / metadata / dataservice 专题字段映射以 `docs/reconstructs/*` 为准。

---

#### 6.1.3 `catalog_model`

用途：目录模型/模板定义，是 `CatalogModel` 的聚合根。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| model_code | VARCHAR(64) | NOT NULL | 稳定编码 |
| model_name | VARCHAR(200) | NOT NULL | 模型名称 |
| model_scope | VARCHAR(32) | NOT NULL | `gov_catalog/open_catalog/shared_zone/custom` |
| status | VARCHAR(32) | NOT NULL | `draft/active/retired` |
| source_mode | VARCHAR(32) | NOT NULL | `builtin/imported_from_legacy/external_standard` |
| current_version_no | INT | NOT NULL | 当前版本号 |
| description | TEXT |  | 说明 |
| legacy_source_ref | JSONB |  | legacy 来源引用 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (tenant_id, model_code)`
- `INDEX (tenant_id, status)`

legacy 对应：目录模型、目录分类与标准目录类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

#### 6.1.4 `catalog_model_step`

用途：维护目录编制步骤。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| model_id | UUID | FK | 关联 `catalog_model.id` |
| step_key | VARCHAR(64) | NOT NULL | 稳定键 |
| step_name | VARCHAR(128) | NOT NULL | 步骤名称 |
| sort_order | INT | NOT NULL | 排序 |
| is_required | BOOLEAN | NOT NULL | 是否必须 |
| config_json | JSONB |  | 步骤配置 |

约束与索引：

- `UNIQUE (model_id, step_key)`
- `INDEX (model_id, sort_order)`

legacy 对应：目录编制步骤类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

#### 6.1.5 `catalog_model_field`

用途：维护目录属性、信息项属性、字典/维度/UI 约束等。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| model_id | UUID | FK | 关联 `catalog_model.id` |
| step_id | UUID | FK | 可空，关联 `catalog_model_step.id` |
| field_scope | VARCHAR(16) | NOT NULL | `catalog/item` |
| field_code | VARCHAR(64) | NOT NULL | 字段编码 |
| field_name | VARCHAR(128) | NOT NULL | 字段名称 |
| data_type | VARCHAR(32) | NOT NULL | 数据类型 |
| dictionary_code | VARCHAR(64) |  | 字典编码 |
| ui_component | VARCHAR(64) |  | UI 组件 |
| is_required | BOOLEAN | NOT NULL | 是否必填 |
| is_readonly | BOOLEAN | NOT NULL | 是否只读 |
| is_portal_visible | BOOLEAN | NOT NULL | 是否展示 |
| is_exportable | BOOLEAN | NOT NULL | 是否导出 |
| is_importable | BOOLEAN | NOT NULL | 是否导入 |
| display_order | INT | NOT NULL | 排序 |
| validation_rule | JSONB |  | 校验规则 |
| extra_config | JSONB |  | 额外配置 |

约束与索引：

- `UNIQUE (model_id, field_scope, field_code)`
- `INDEX (model_id, step_id, display_order)`

legacy 对应：目录字段、维度和表单属性类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

---

#### 6.1.6 `catalog_entry`

用途：目录主实体，是 J1 / J2 的核心聚合根之一。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| catalog_code | VARCHAR(64) | NOT NULL | 目录编码 |
| model_id | UUID | FK | 关联 `catalog_model.id` |
| title | VARCHAR(256) | NOT NULL | 目录名称 |
| owner_org_id | VARCHAR(64) | NOT NULL | 提供方组织 ID |
| owner_org_snapshot | JSONB | NOT NULL | 提供方组织快照 |
| region_code | VARCHAR(32) |  | 区划编码 |
| region_name | VARCHAR(64) |  | 区划名称 |
| source_system_id | VARCHAR(64) |  | 来源系统编码 |
| share_type | VARCHAR(32) | NOT NULL | `unconditional/conditional/forbidden` |
| share_condition | TEXT |  | 共享条件 |
| open_type | VARCHAR(32) | NOT NULL | `public/application/closed` |
| open_condition | TEXT |  | 开放条件 |
| update_cycle_code | VARCHAR(32) |  | 更新周期 |
| subject_tags | JSONB |  | 主题/行业/领域标签 |
| summary | TEXT |  | 摘要 |
| lifecycle_status | VARCHAR(32) | NOT NULL | `draft/pending_review/published/changed/revoking/revoked/rejected/archived` |
| latest_version_no | INT | NOT NULL | 当前版本号 |
| published_at | TIMESTAMPTZ |  | 发布时间 |
| archived_at | TIMESTAMPTZ |  | 归档时间 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (tenant_id, catalog_code)`
- `INDEX (tenant_id, lifecycle_status, updated_at DESC)`
- `INDEX (tenant_id, owner_org_id, lifecycle_status)`
- `GIN (subject_tags)`

legacy 对应：目录本体类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

#### 6.1.7 `catalog_entry_version`

用途：保存目录版本快照，支持回放、对比、审计与回滚。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| catalog_id | UUID | FK | 关联 `catalog_entry.id` |
| version_no | INT | NOT NULL | 版本号 |
| change_type | VARCHAR(32) | NOT NULL | `create/modify/publish/revoke/sync` |
| snapshot_json | JSONB | NOT NULL | 目录完整快照 |
| change_reason | TEXT |  | 变更原因 |
| changed_by | JSONB | NOT NULL | 变更人快照 |
| approval_case_id | UUID |  | 关联审批单 |
| created_at | TIMESTAMPTZ | NOT NULL | 生成时间 |

约束与索引：

- `UNIQUE (catalog_id, version_no)`
- `INDEX (catalog_id, created_at DESC)`

legacy 对应：目录版本与信息项版本类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

#### 6.1.8 `catalog_item`

用途：目录信息项定义，是目录内可治理的结构化字段集合。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| catalog_id | UUID | FK | 关联 `catalog_entry.id` |
| item_code | VARCHAR(64) | NOT NULL | 数据项编码 |
| item_name | VARCHAR(128) | NOT NULL | 数据项名称 |
| data_type | VARCHAR(32) | NOT NULL | 数据类型 |
| length | INT |  | 长度 |
| precision | INT |  | 精度 |
| is_primary_key | BOOLEAN | NOT NULL | 是否主键 |
| is_nullable | BOOLEAN | NOT NULL | 是否可空 |
| sensitive_level | VARCHAR(32) |  | 敏感级别 |
| share_condition_type | VARCHAR(32) |  | 共享条件类型 |
| description | TEXT |  | 字段说明 |
| source_column_ref | JSONB |  | 来源字段引用 |
| display_order | INT | NOT NULL | 排序 |

约束与索引：

- `UNIQUE (catalog_id, item_code)`
- `INDEX (catalog_id, display_order)`

legacy 对应：目录信息项、字段口径与标准字段类证据；catalog3 / metadata3 专题字段映射以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

---

#### 6.1.9 `resource_asset`

用途：定义可被发现、申请、交付的数据资源，是 J1 找数→用数 主旅程的核心实体。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| catalog_id | UUID | FK | 所属目录 |
| resource_code | VARCHAR(64) | NOT NULL | 资源编码 |
| resource_name | VARCHAR(256) | NOT NULL | 资源名称 |
| resource_kind | VARCHAR(32) | NOT NULL | `table/api/file/stream/dataset` |
| owner_org_id | VARCHAR(64) | NOT NULL | 提供方组织 |
| source_system_id | VARCHAR(64) |  | 来源系统编码 |
| publish_scope | VARCHAR(32) | NOT NULL | `tenant/cross-tenant-approved/public-approved` |
| access_policy_json | JSONB | NOT NULL | 访问控制策略快照 |
| qos_policy_json | JSONB |  | QoS / SLA / 配额策略 |
| status | VARCHAR(32) | NOT NULL | `draft/pending_review/active/suspended/revoked/retired` |
| validity_start | TIMESTAMPTZ |  | 生效时间 |
| validity_end | TIMESTAMPTZ |  | 失效时间 |
| latest_sync_at | TIMESTAMPTZ |  | 最近同步时间 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (tenant_id, resource_code)`
- `INDEX (tenant_id, catalog_id, status)`
- `INDEX (tenant_id, owner_org_id, resource_kind, status)`

legacy 对应：资源本体、库表/API/文件通道与服务资源类证据；dataservice 与 catalog3 / metadata3 专题字段映射分别以 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md`、`docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为准。

#### 6.1.10 `resource_channel_binding`

用途：定义资源的交付通道绑定，不存明文密钥，只存绑定元信息与引用。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| resource_id | UUID | FK | 关联 `resource_asset.id` |
| channel_type | VARCHAR(32) | NOT NULL | `api/db/file/national_push/subscription` |
| binding_status | VARCHAR(32) | NOT NULL | `inactive/ready/testing/deprecated` |
| endpoint_ref | JSONB | NOT NULL | 终端地址 / 路由 / 对象路径引用 |
| schema_ref | JSONB |  | 结构说明 |
| auth_ref | JSONB |  | 鉴权引用 |
| gateway_policy_json | JSONB |  | 网关策略快照或外部策略引用，包括限流、熔断、黑白名单、过滤与日志采集级别 |
| delivery_capability_slug | VARCHAR(128) |  | 交付 capability |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (resource_id, channel_type)`
- `INDEX (binding_status, updated_at DESC)`

legacy 对应：`ApiServiceNode`, `ApiInputParam`, `ApiServiceGeneral`, `base_system_info`, `MetaDatabase`

---

#### 6.1.11 `application_record`

用途：申请单主实体，是 J1 找数→用数 主旅程的中心聚合根。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| catalog_id | UUID | FK | 申请目录 |
| resource_id | UUID | FK | 申请资源 |
| requested_channel_type | VARCHAR(32) | NOT NULL | 期望交付方式 |
| applicant_org_id | VARCHAR(64) | NOT NULL | 申请方组织 |
| applicant_org_snapshot | JSONB | NOT NULL | 申请方组织快照 |
| requester_snapshot | JSONB | NOT NULL | 申请人快照 |
| contact_snapshot | JSONB | NOT NULL | 联系方式快照 |
| use_purpose | TEXT | NOT NULL | 使用目的 |
| use_scope_json | JSONB | NOT NULL | 使用范围、地区、场景、字段选择 |
| requested_items | JSONB |  | 申请数据项列表 |
| requested_until | DATE |  | 申请有效期 |
| status | VARCHAR(32) | NOT NULL | `draft/submitted/supplement_required/in_review/approved/rejected/withdrawn/delivering/active/expired/closed` |
| approval_case_id | UUID |  | 当前审批单 |
| latest_decision_summary | TEXT |  | 最近结论摘要 |
| submitted_at | TIMESTAMPTZ |  | 提交时间 |
| approved_at | TIMESTAMPTZ |  | 审批通过时间 |
| closed_at | TIMESTAMPTZ |  | 关闭时间 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (tenant_id, status, submitted_at DESC)`
- `INDEX (tenant_id, applicant_org_id, status)`
- `INDEX (resource_id, status)`
- `GIN (requested_items)`

legacy 对应：申请、资源申请和交换申请类证据；catalog3 / metadata3 与 dataservice 专题字段映射分别以对应 `docs/reconstructs/*` 文档为准。

#### 6.1.12 `application_attachment`

用途：申请附件、补件、证明材料关联表。**不承载任何回执事实**；凡属于审批回执、交付回执、人工确认回执或外链存证回执，统一落到 `brain_audit.audit_receipt` 或 `brain_core.delivery_receipt`。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| application_id | UUID | FK | 关联 `application_record.id` |
| blob_id | UUID | FK | 关联 `blob_object.id` |
| attachment_type | VARCHAR(32) | NOT NULL | `official_letter/supplement/evidence` |
| uploaded_by | JSONB | NOT NULL | 上传人快照 |
| created_at | TIMESTAMPTZ | NOT NULL | 上传时间 |

约束与索引：

- `INDEX (application_id, attachment_type)`

legacy 对应：`attachment_info`, `official_file`, `supply_document`

---

#### 6.1.13 `approval_case`

用途：统一的审批包络，不只服务申请审批，也服务目录发布、资源发布、能力注册等强责任动作。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| business_type | VARCHAR(32) | NOT NULL | `catalog_publish/resource_publish/application_apply/application_renew/application_revoke/capability_register/objection_close` |
| target_type | VARCHAR(32) | NOT NULL | 目标实体类型 |
| target_id | UUID | NOT NULL | 目标实体主键 |
| requester_snapshot | JSONB | NOT NULL | 提交人快照 |
| policy_snapshot | JSONB | NOT NULL | 审批策略快照 |
| current_status | VARCHAR(32) | NOT NULL | `pending_assignment/pending_decision/returned_for_supplement/approved/rejected/cancelled` |
| current_step_no | INT | NOT NULL | 当前步骤 |
| sla_due_at | TIMESTAMPTZ |  | SLA 截止时间 |
| submitted_at | TIMESTAMPTZ | NOT NULL | 提交时间 |
| finished_at | TIMESTAMPTZ |  | 完成时间 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (tenant_id, current_status, submitted_at DESC)`
- `INDEX (target_type, target_id)`

legacy 对应：审批流程、审批节点、审批意见与待办流转类证据；catalog3 / metadata3 与 dataservice 专题字段映射分别以对应 `docs/reconstructs/*` 文档为准。

#### 6.1.14 `approval_step`

用途：审批步骤定义与执行状态。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| approval_case_id | UUID | FK | 关联 `approval_case.id` |
| step_no | INT | NOT NULL | 步骤序号 |
| step_name | VARCHAR(128) | NOT NULL | 步骤名称 |
| approver_scope_json | JSONB | NOT NULL | 审批人范围 |
| decision_mode | VARCHAR(32) | NOT NULL | `single/any/all` |
| status | VARCHAR(32) | NOT NULL | `pending/in_progress/approved/rejected/returned/skipped/cancelled` |
| due_at | TIMESTAMPTZ |  | 截止时间 |
| started_at | TIMESTAMPTZ |  | 开始时间 |
| completed_at | TIMESTAMPTZ |  | 完成时间 |

约束与索引：

- `UNIQUE (approval_case_id, step_no)`
- `INDEX (status, due_at)`

legacy 对应：legacy 多套审批节点/流程明细表

#### 6.1.15 `approval_decision`

用途：保存每一次审批动作与意见，不覆盖历史。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| step_id | UUID | FK | 关联 `approval_step.id` |
| actor_snapshot | JSONB | NOT NULL | 审批人快照 |
| decision | VARCHAR(32) | NOT NULL | `approve/reject/return/transfer/escalate` |
| decision_reason | TEXT |  | 审批意见 |
| evidence_json | JSONB |  | 证据引用 |
| created_at | TIMESTAMPTZ | NOT NULL | 决策时间 |

约束与索引：

- `INDEX (step_id, created_at DESC)`

legacy 对应：`approve_opinion`, `audit_opinion`, 各类审核意见字段与节点轨迹表

---

#### 6.1.16 `delivery_task`

用途：交付任务主实体，表达批准后的真实交付链路。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| application_id | UUID | FK | 来源申请单 |
| resource_id | UUID | FK | 来源资源 |
| channel_type | VARCHAR(32) | NOT NULL | `api/db/file/national_push/subscription` |
| target_binding_id | UUID | FK | 资源通道绑定 |
| executor_mode | VARCHAR(32) | NOT NULL | `builtin/adapter/registered-package` |
| state | VARCHAR(32) | NOT NULL | `pending/provisioning/running/waiting_receipt/succeeded/partial_failed/failed/cancelled/expired` |
| current_attempt_no | INT | NOT NULL | 当前尝试次数 |
| access_grant_snapshot | JSONB | NOT NULL | 授权结果快照 |
| requested_at | TIMESTAMPTZ | NOT NULL | 请求时间 |
| scheduled_at | TIMESTAMPTZ |  | 调度时间 |
| started_at | TIMESTAMPTZ |  | 开始时间 |
| finished_at | TIMESTAMPTZ |  | 完成时间 |
| expires_at | TIMESTAMPTZ |  | 过期时间 |
| last_error_code | VARCHAR(64) |  | 最近错误码 |
| last_error_message | TEXT |  | 最近错误信息 |
| row_version | INT | NOT NULL | 乐观锁 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (tenant_id, state, created_at DESC)`
- `INDEX (application_id, state)`
- `INDEX (resource_id, channel_type, state)`

legacy 对应：`dc_resource_apply_info`, `dc_subscribe`, `Pipelines`, `PipelinesSubscribe`, `ResourceApplied`

#### 6.1.17 `delivery_attempt`

用途：记录每次交付执行尝试，支持失败诊断与重试回放。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| delivery_id | UUID | FK | 关联 `delivery_task.id` |
| attempt_no | INT | NOT NULL | 尝试序号 |
| external_job_ref | VARCHAR(128) |  | 外部作业号 |
| state | VARCHAR(32) | NOT NULL | `queued/running/succeeded/failed/timeout/cancelled` |
| request_payload | JSONB | NOT NULL | 执行请求快照 |
| response_payload | JSONB |  | 响应快照 |
| started_at | TIMESTAMPTZ |  | 开始时间 |
| ended_at | TIMESTAMPTZ |  | 结束时间 |

约束与索引：

- `UNIQUE (delivery_id, attempt_no)`
- `INDEX (state, started_at DESC)`

legacy 对应：`SubscribeJob`, `batch_job_execution*`, `batch_step_execution*`, `XxlJobInfo`

#### 6.1.18 `delivery_receipt`

用途：保存交付回执、交换回执、国家通道回执、下载回执等**业务交付事实**。它表达的是“交付这件事有没有产生业务可消费的回执/确认”，而不是消息中心中的通知投递记录。与 `audit_receipt` 的分工如下：

- `delivery_receipt`：描述 J1 找数→用数 主旅程末段交付任务的业务结果与外部回执
- `audit_receipt`：描述责任动作的确认、审批、调查、存证等审计事实

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| delivery_id | UUID | FK | 关联 `delivery_task.id` |
| receipt_type | VARCHAR(32) | NOT NULL | `provision/exchange/download/national_ack/subscription_ack` |
| receipt_no | VARCHAR(128) |  | 回执编号 |
| receipt_status | VARCHAR(32) | NOT NULL | `issued/acknowledged/rejected/expired` |
| payload_json | JSONB | NOT NULL | 回执正文 |
| raw_blob_id | UUID |  | 原始回执文件 |
| issued_at | TIMESTAMPTZ | NOT NULL | 签发时间 |
| acknowledged_at | TIMESTAMPTZ |  | 确认时间 |

约束与索引：

- `INDEX (delivery_id, receipt_type)`
- `INDEX (receipt_status, issued_at DESC)`

legacy 对应：国家平台 / 级联接口回执类字段、交换执行结果、订阅确认结果；**不把** `base_message_info` / `data_message_info` 视为 delivery receipt 的权威事实源。

#### 6.1.19 `delivery_notice_projection`

用途：承接交付链路面向人的消息通知投影，例如“交付已完成”“回执已到达”“下载即将过期”。它是通知投影，不是业务事实源。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| delivery_id | UUID | FK | 关联 `delivery_task.id` |
| notice_type | VARCHAR(32) | NOT NULL | `delivery_status/receipt_arrived/expiration_reminder` |
| receiver_snapshot | JSONB | NOT NULL | 接收人快照 |
| title | VARCHAR(255) | NOT NULL | 标题 |
| content | TEXT | NOT NULL | 内容 |
| read_at | TIMESTAMPTZ |  | 已读时间 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

约束与索引：

- `INDEX (tenant_id, created_at DESC)`
- `INDEX (delivery_id, notice_type)`

legacy 对应：`base_message_info`, `data_message_info`

#### 6.1.20 `delivery_subscription`

用途：长周期交付、订阅、直达类任务的持续状态。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| application_id | UUID | FK | 来源申请单 |
| delivery_id | UUID | FK | 最近交付任务 |
| resource_id | UUID | FK | 资源 |
| pipeline_ref | JSONB | NOT NULL | 管道 / 订阅配置引用 |
| sync_mode | VARCHAR(32) | NOT NULL | `full/incremental/event-driven` |
| cron_expr | VARCHAR(64) |  | 周期表达式 |
| cursor_state | JSONB |  | 增量游标 |
| status | VARCHAR(32) | NOT NULL | `active/paused/failed/closed` |
| next_run_at | TIMESTAMPTZ |  | 下次执行时间 |
| last_run_at | TIMESTAMPTZ |  | 上次执行时间 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (status, next_run_at)`
- `INDEX (resource_id, status)`

legacy 对应：`dc_subscribe`, `PipelinesSubscribe`, `SubscribeDetail`, `SubscribeJob`

---

#### 6.1.21 `objection_case`

用途：异议工单主实体，是 J1 / J2 异议子流程的强状态链路。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| objection_kind | VARCHAR(32) | NOT NULL | `catalog/resource/authorization/usage/quality` |
| target_type | VARCHAR(32) | NOT NULL | 异议目标类型 |
| target_id | UUID | NOT NULL | 异议目标主键 |
| related_application_id | UUID |  | 关联申请单 |
| title | VARCHAR(255) | NOT NULL | 异议标题 |
| complainant_org_id | VARCHAR(64) | NOT NULL | 提出方组织 |
| complainant_org_snapshot | JSONB | NOT NULL | 提出方快照 |
| provider_org_id | VARCHAR(64) | NOT NULL | 提供方组织 |
| provider_org_snapshot | JSONB | NOT NULL | 提供方快照 |
| basis_text | TEXT |  | 异议依据 |
| expected_result | TEXT |  | 期望结果 |
| status | VARCHAR(32) | NOT NULL | `draft/submitted/accepted/platform_investigating/provider_investigating/resolved/rejected/closed` |
| resolved_summary | TEXT |  | 解决摘要 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |
| closed_at | TIMESTAMPTZ |  | 关闭时间 |
| row_version | INT | NOT NULL | 乐观锁 |

约束与索引：

- `INDEX (tenant_id, status, created_at DESC)`
- `INDEX (target_type, target_id)`
- `INDEX (related_application_id)`

legacy 对应：`data_objection`, `data_interact_feedback`, `CorrectionFeedBack`

#### 6.1.22 `objection_evidence`

用途：保存异议文本、附件、字段差异、日志节选等证据。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| objection_id | UUID | FK | 关联 `objection_case.id` |
| evidence_type | VARCHAR(32) | NOT NULL | `text/file/screenshot/field_diff/api_contract/log_excerpt` |
| blob_id | UUID |  | 文件证据 |
| content_json | JSONB |  | 结构化内容 |
| submitted_by | JSONB | NOT NULL | 提交人快照 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

约束与索引：

- `INDEX (objection_id, evidence_type)`

legacy 对应：`data_objection_catalog`, `data_objection_resource`, `data_objection_use`, `data_objection_content`

#### 6.1.23 `objection_process`

用途：保存异议受理、核查、转办、回复、结案的过程轨迹。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| objection_id | UUID | FK | 关联 `objection_case.id` |
| node_name | VARCHAR(128) | NOT NULL | 环节名称 |
| handler_org_id | VARCHAR(64) |  | 处理组织 |
| handler_snapshot | JSONB | NOT NULL | 处理人/组织快照 |
| action_type | VARCHAR(32) | NOT NULL | `accept/reject/investigate/transfer/reply/resolve` |
| action_result | VARCHAR(32) | NOT NULL | `pass/fail/returned/closed` |
| opinion | TEXT |  | 处理意见 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

约束与索引：

- `INDEX (objection_id, created_at)`

legacy 对应：`data_objection_process`

#### 6.1.24 `objection_evaluation`

用途：保存异议结束后的评价与是否解决判断。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| objection_id | UUID | FK | 关联 `objection_case.id` |
| evaluator_snapshot | JSONB | NOT NULL | 评价人快照 |
| solved_flag | BOOLEAN | NOT NULL | 是否解决 |
| overall_score | INT |  | 总评分 |
| timeliness_score | INT |  | 时效评分 |
| result_score | INT |  | 结果评分 |
| comment | TEXT |  | 评价内容 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |

约束与索引：

- `UNIQUE (objection_id)`

legacy 对应：`data_objection_evaluate`

---

### 6.2 `brain_audit`：审计、回执、上链 outbox

#### 6.2.1 `capability_call`

用途：记录每次 Capability 调用，是"谁通过哪个消费面触发了什么能力"的统一入口日志。严格服从基线五消费面定义（WebUI / API / CLI / MCP / A2A）。B1.1 合规与运营消费 `capability_call` / `audit_event` 等统计投影。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| capability_slug | VARCHAR(128) | NOT NULL | 能力标识 |
| capability_version | VARCHAR(32) | NOT NULL | 能力版本 |
| exposure_surface | VARCHAR(32) | NOT NULL | `webui/api/cli/mcp/a2a` |
| actor_type | VARCHAR(32) | NOT NULL | `user/service/agent` |
| actor_snapshot | JSONB | NOT NULL | 调用方快照 |
| target_aggregate_type | VARCHAR(32) |  | 目标聚合 |
| target_aggregate_id | UUID |  | 目标实体 |
| confirmation_required | BOOLEAN | NOT NULL | 是否要求人工确认 |
| confirmation_receipt_id | UUID |  | 确认回执 |
| status | VARCHAR(32) | NOT NULL | `accepted/running/succeeded/failed/rejected` |
| input_hash | CHAR(64) | NOT NULL | 输入摘要 |
| output_hash | CHAR(64) |  | 输出摘要 |
| started_at | TIMESTAMPTZ | NOT NULL | 开始时间 |
| ended_at | TIMESTAMPTZ |  | 结束时间 |

约束与索引：

- `INDEX (tenant_id, capability_slug, started_at DESC)`
- `INDEX (status, started_at DESC)`
- `INDEX (target_aggregate_type, target_aggregate_id)`

#### 6.2.2 `audit_event`

用途：保存对实体状态变化负责任的全量审计事件，是 audit store 的核心事实表。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| aggregate_type | VARCHAR(32) | NOT NULL | 聚合类型 |
| aggregate_id | UUID | NOT NULL | 聚合主键 |
| event_type | VARCHAR(64) | NOT NULL | 事件类型 |
| audit_class | VARCHAR(32) | NOT NULL | `read-trace/write-normal/write-critical/security` |
| source_call_id | UUID |  | 来源 capability 调用 |
| actor_snapshot | JSONB | NOT NULL | 行为人快照 |
| before_state_hash | CHAR(64) |  | 变更前状态哈希 |
| after_state_hash | CHAR(64) |  | 变更后状态哈希 |
| payload_json | JSONB | NOT NULL | 审计载荷 |
| occurred_at | TIMESTAMPTZ | NOT NULL | 发生时间 |

约束与索引：

- `INDEX (aggregate_type, aggregate_id, occurred_at)`
- `INDEX (tenant_id, audit_class, occurred_at DESC)`
- `GIN (payload_json)`

legacy 对应：`user_operation_log`, `sys_log`, `data_cascade_record_log`, `data_cascade_interface_log`

#### 6.2.3 `audit_receipt`

用途：保存人工确认、审批回执、系统确认、调查结论、存证回执等结构化凭证。这里的 receipt 是**审计与责任事实**，不是通知消息；消息中心类表如果被保留，只能作为 notice projection 或发送记录的 legacy 输入。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| source_event_id | UUID |  | 来源审计事件 |
| source_call_id | UUID |  | 来源能力调用 |
| receipt_kind | VARCHAR(32) | NOT NULL | `human_confirmation/approval/system_ack/investigation/anchor` |
| receipt_code | VARCHAR(128) |  | 回执编号 |
| receipt_payload | JSONB | NOT NULL | 回执正文 |
| raw_blob_id | UUID |  | 原始文件 |
| issued_at | TIMESTAMPTZ | NOT NULL | 生成时间 |

约束与索引：

- `INDEX (source_event_id)`
- `INDEX (receipt_kind, issued_at DESC)`

legacy 对应：审批结果、人工确认记录、调查结论、`block_success_log`；**不把** `base_message_info` / `data_message_info` 视为 audit receipt 的权威事实源

#### 6.2.4 `anchor_outbox`

用途：对接区块链/监管外链的异步 outbox。遵循基线 §3.4 / §9.5：**本地审计同步落库，外部上链异步执行**。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| source_receipt_id | UUID | NOT NULL | 来源回执 |
| adapter_code | VARCHAR(64) | NOT NULL | `blockchain` 等 |
| status | VARCHAR(32) | NOT NULL | `pending/sending/succeeded/failed/retry_wait/abandoned` |
| payload_hash | CHAR(64) | NOT NULL | 上链摘要 |
| tx_hash | VARCHAR(128) |  | 外部交易哈希 |
| retry_count | INT | NOT NULL | 重试次数 |
| next_retry_at | TIMESTAMPTZ |  | 下次重试时间 |
| last_error | TEXT |  | 最近错误 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `INDEX (status, next_retry_at)`
- `INDEX (source_receipt_id)`

legacy 对应：`block_apilog`, `block_err_log`, `block_success_log`

#### 6.2.5 `gateway_runtime_status_projection`

用途：支撑 B1.1 合规与运营对外部网关运行状态的只读观察。它不是网关管理事实源，不承载路由、认证、限流等策略状态；这些策略仍回到 `resource_channel_binding.gateway_policy_json` 或外部网关策略系统。

`dsp-dataservice` 的 `/openapi/report` 网关心跳迁移语义、字段建议、来源证据与验收规则，以 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` §3.3 为单一事实源。

#### 6.2.6 `service_invocation_metric_projection`

用途：支撑 B1.1 合规与运营、REST / CLI 统计查询的服务调用指标读侧投影。它不是业务事实源，来源必须回指 `capability_call`、`audit_event` 或只读网关日志 adapter。

`dsp-dataservice` 的服务调用统计迁移语义、字段建议、来源证据与验收规则，以 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` §3.4 为单一事实源。

---

### 6.3 `brain_registry`：Capability Registry 与 adapter 映射

> 派生产物约束：`brain_registry` 不只是保存注册记录，还必须成为以下产物的唯一派生源：
> - WebUI 动作元数据与表单 schema
> - REST / OpenAPI 描述
> - CLI command spec
> - MCP tool / resource manifest
> - A2A action / agent card 元数据
> 
> 若某消费面需要额外手写一份能力描述而无法从 registry / contract 派生，说明该数据模型仍不符合基线的单一事实源要求。

#### 6.3.1 `capability_package`

用途：Capability 包的包级元信息，是 Registry 的聚合根。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| package_slug | VARCHAR(128) | NOT NULL | 稳定标识 |
| package_kind | VARCHAR(32) | NOT NULL | `skill/agent/tool/bundle` |
| source_type | VARCHAR(32) | NOT NULL | `builtin/imported/external-register` |
| owner_org_id | VARCHAR(64) |  | 归属组织 |
| review_status | VARCHAR(32) | NOT NULL | `draft/pending_review/approved/disabled/archived` |
| default_audit_class | VARCHAR(32) | NOT NULL | 默认审计等级 |
| default_tenant_scope | VARCHAR(32) | NOT NULL | 默认租户范围 |
| latest_version_id | UUID |  | 最新版本 |
| summary | TEXT |  | 包说明 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (package_slug)`
- `INDEX (review_status, updated_at DESC)`

legacy 对应：外部 package manifest 元信息

#### 6.3.2 `capability_version`

用途：Capability 版本级 contract、schema、binding、兼容面定义。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| package_id | UUID | FK | 关联 `capability_package.id` |
| version | VARCHAR(32) | NOT NULL | 版本号 |
| manifest_json | JSONB | NOT NULL | manifest |
| input_schema_json | JSONB | NOT NULL | 输入 schema |
| output_schema_json | JSONB | NOT NULL | 输出 schema |
| auth_policy | VARCHAR(32) | NOT NULL | `user/service/agent` |
| tenant_scope | VARCHAR(32) | NOT NULL | `tenant/cross-tenant-approved` |
| human_confirmation_required | BOOLEAN | NOT NULL | 是否人工确认 |
| audit_class | VARCHAR(32) | NOT NULL | 审计等级 |
| runtime_binding_type | VARCHAR(32) | NOT NULL | `builtin/registered-package/adapter-call` |
| runtime_binding_ref | JSONB | NOT NULL | 运行时绑定引用 |
| compatibility_json | JSONB | NOT NULL | 支持的消费面 |
| rollback_target_version | VARCHAR(32) |  | 回滚版本 |
| status | VARCHAR(32) | NOT NULL | `draft/approved/active/rolled_back/archived` |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| approved_at | TIMESTAMPTZ |  | 审批时间 |

约束与索引：

- `UNIQUE (package_id, version)`
- `INDEX (status, created_at DESC)`

#### 6.3.3 `capability_exposure`

用途：定义某版本 Capability 暴露到哪些消费面，以及路由/生成产物信息。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| version_id | UUID | FK | 关联 `capability_version.id` |
| surface | VARCHAR(32) | NOT NULL | `webui/api/cli/mcp/a2a` |
| route_key | VARCHAR(128) |  | 路由或命令键 |
| enabled | BOOLEAN | NOT NULL | 是否启用 |
| tenant_override_scope | VARCHAR(32) |  | 可选租户覆盖 |
| generated_artifact_ref | JSONB |  | 自动生成产物引用 |
| created_at | TIMESTAMPTZ | NOT NULL | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (version_id, surface)`
- `INDEX (surface, enabled)`

#### 6.3.4 `capability_review_record`

用途：记录包版本的审核、禁用、回滚、归档决策。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| version_id | UUID | FK | 关联 `capability_version.id` |
| reviewer_snapshot | JSONB | NOT NULL | 审核人快照 |
| decision | VARCHAR(32) | NOT NULL | `approve/reject/disable/archive/rollback` |
| comment | TEXT |  | 审核意见 |
| decision_at | TIMESTAMPTZ | NOT NULL | 决策时间 |

约束与索引：

- `INDEX (version_id, decision_at DESC)`

#### 6.3.5 `tenant_capability_policy`

用途：控制某租户对某 Capability 包的启停、暴露面和策略覆盖。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| tenant_id | VARCHAR(64) | NOT NULL | 租户标识 |
| package_id | UUID | FK | 能力包 |
| version_id | UUID | FK | 生效版本 |
| enabled | BOOLEAN | NOT NULL | 是否启用 |
| exposed_surfaces | JSONB | NOT NULL | 暴露消费面 |
| auth_override_json | JSONB |  | 权限覆盖 |
| updated_by | JSONB | NOT NULL | 更新人快照 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新时间 |

约束与索引：

- `UNIQUE (tenant_id, package_id)`
- `INDEX (tenant_id, enabled)`

#### 6.3.6 `legacy_adapter_source`

用途：登记 legacy 输入源，只允许 `readonly` 访问。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| source_code | VARCHAR(64) | NOT NULL | 输入源编码 |
| source_kind | VARCHAR(32) | NOT NULL | `mysql/api/file` |
| source_name | VARCHAR(128) | NOT NULL | 输入源名称 |
| access_mode | VARCHAR(16) | NOT NULL | 固定 `readonly` |
| connection_ref | JSONB | NOT NULL | 连接引用 |
| owned_domain | VARCHAR(64) | NOT NULL | 所属领域 |
| sync_strategy | VARCHAR(32) | NOT NULL | `snapshot/incremental/event-poll` |
| status | VARCHAR(32) | NOT NULL | `active/paused/retired` |
| last_sync_at | TIMESTAMPTZ |  | 最近同步时间 |

约束与索引：

- `UNIQUE (source_code)`

#### 6.3.7 `legacy_object_mapping`

用途：保存 legacy 主键到 canonical 主键的映射和证据，支撑迁移回放与排障。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 主键 |
| adapter_id | UUID | FK | 关联 `legacy_adapter_source.id` |
| legacy_system | VARCHAR(64) | NOT NULL | 旧系统名 |
| legacy_table | VARCHAR(128) | NOT NULL | 旧表名 |
| legacy_pk | VARCHAR(256) | NOT NULL | 旧主键 |
| canonical_type | VARCHAR(32) | NOT NULL | 新实体类型 |
| canonical_id | UUID | NOT NULL | 新实体主键 |
| mapping_status | VARCHAR(32) | NOT NULL | `discovered/mapped/conflicted/retired` |
| evidence_json | JSONB | NOT NULL | 映射证据 |
| last_seen_at | TIMESTAMPTZ | NOT NULL | 最近观测时间 |

约束与索引：

- `UNIQUE (legacy_system, legacy_table, legacy_pk)`
- `INDEX (canonical_type, canonical_id)`

---

## 七、状态机定义

### 7.1 目录状态机 `catalog_entry.lifecycle_status`

```text
draft
  → pending_review
  → published
  → changed
  → pending_review
  → published
  → revoking
  → revoked

pending_review → rejected
published      → archived
rejected       → draft
```

说明：

- `changed` 不是终态，而是“发布后变更待重新审”的临时态
- `revoked` 表示业务撤销后仍保留历史可回放性
- `archived` 只用于退出主工作流后的长期留痕

### 7.2 申请状态机 `application_record.status`

```text
draft
  → submitted
  → in_review
  → approved
  → delivering
  → active
  → expired
  → closed

submitted  → supplement_required → submitted
in_review  → rejected
submitted  → withdrawn
approved   → closed
```

说明：

- `approved` 与 `active` 不是同义；前者表示审批通过，后者表示交付已真正生效
- `delivering` 必须显式存在，避免把审批完成误认为已交付完成

### 7.3 审批状态机 `approval_case.current_status`

```text
pending_assignment
  → pending_decision
  → approved

pending_decision
  → returned_for_supplement
  → pending_decision

pending_decision → rejected
pending_decision → cancelled
```

### 7.4 交付状态机 `delivery_task.state`

```text
pending
  → provisioning
  → running
  → waiting_receipt
  → succeeded

running         → partial_failed
running         → failed
pending/running → cancelled
succeeded       → expired
```

说明：

- `partial_failed` 需要保留，旧平台大量交付链路并不是简单二元成功/失败
- `waiting_receipt` 允许国家平台 / 区块链 / 外部交换平台有独立确认时延

### 7.5 异议状态机 `objection_case.status`

```text
draft
  → submitted
  → accepted
  → platform_investigating
  → provider_investigating
  → resolved
  → closed

submitted → rejected
resolved  → closed
```

说明：

- `platform_investigating` 与 `provider_investigating` 分开保留，符合旧平台的多方核查责任链
- `resolved` 与 `closed` 分开，便于“已给出处理结果但尚未完成评价/归档”的场景

---

## 八、关键索引与约束策略

### 8.1 必须有的唯一约束

- `catalog_entry (tenant_id, catalog_code)`
- `resource_asset (tenant_id, resource_code)`
- `catalog_entry_version (catalog_id, version_no)`
- `catalog_item (catalog_id, item_code)`
- `approval_step (approval_case_id, step_no)`
- `delivery_attempt (delivery_id, attempt_no)`
- `capability_package (package_slug)`
- `capability_version (package_id, version)`
- `capability_exposure (version_id, surface)`
- `tenant_capability_policy (tenant_id, package_id)`
- `legacy_object_mapping (legacy_system, legacy_table, legacy_pk)`

### 8.2 必须有的查询索引

- 待办/工作台：
  - `approval_case (tenant_id, current_status, submitted_at desc)`
  - `application_record (tenant_id, status, submitted_at desc)`
  - `delivery_task (tenant_id, state, created_at desc)`
  - `objection_case (tenant_id, status, created_at desc)`
- 目录发现：
  - `catalog_entry (tenant_id, lifecycle_status, owner_org_id)`
  - `resource_asset (tenant_id, catalog_id, resource_kind, status)`
- 审计与运营回放：
  - `audit_event (aggregate_type, aggregate_id, occurred_at)`
  - `capability_call (tenant_id, capability_slug, started_at desc)`
  - `gateway_runtime_status_projection` 与 `service_invocation_metric_projection` 的 dsp-dataservice 专属查询索引见 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` §3.3–§3.4。
- 注册治理：
  - `capability_package (review_status, updated_at desc)`
  - `capability_exposure (surface, enabled)`
- 异步对接：
  - `anchor_outbox (status, next_retry_at)`

### 8.3 建议的 JSONB / GIN 索引

- `catalog_entry.subject_tags`
- `application_record.requested_items`
- `audit_event.payload_json`
- `capability_version.manifest_json`
- `legacy_object_mapping.evidence_json`

---

## 九、legacy → canonical 迁移与适配规则

### 9.1 总规则

1. **只读读取 legacy。** 不允许新业务再向旧表写入状态。
2. **先映射语义，再映射字段。** 不做表名一比一搬运。
3. **任何迁移都要产出 `legacy_object_mapping`。** 没有映射证据的同步不视为完成。
4. **状态机优先。** 凡旧表承载状态迁移语义，必须先映射到新状态机，再决定字段落点。
5. **前台低频岛不进入 core。** 只在确有高频价值时进 read model 或外部 capability。

### 9.2 dsp-catalog3 / dsp-metadata3 目录资源治理补充映射

`dsp-catalog3` 与 `dsp-metadata3` 的专题迁移映射、旧结构数据证据、字段级规则、真实工单模式、原生能力边界和 ANP 外化边界，以 `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` 为单一事实源。

本基线只保留 canonical 约束：专题事实必须落入 `CatalogResourceAggregate`、`ApplicationApprovalAggregate`、`DeliveryAggregate`、`AuditAggregate` 以及受控 evidence / projection；不得把旧 catalog / metadata 后台、旧 URL、旧表结构或外部执行器升级为并列事实源。

### 9.3 交付/交换域映射

| legacy 表/模块 | 新表 | 说明 |
|---------------|------|------|
| `dc_resource_apply_info` | `delivery_task` | 从“申请执行信息”归并为交付任务 |
| `dc_subscribe` / `PipelinesSubscribe` | `delivery_subscription` | 持续交付单独建模 |
| `SubscribeJob` / `batch_job_execution*` | `delivery_attempt` | 尝试与调度细节收口 |
| 国家平台 / 级联接口回执字段 | `delivery_receipt` | 交付回执单独建模 |
| `base_message_info` / `data_message_info` | `delivery_notice_projection` | 仅作为通知投影 legacy 来源，不作为交付事实源 |

### 9.4 异议域映射

| legacy 表/模块 | 新表 | 说明 |
|---------------|------|------|
| `data_objection` | `objection_case` | 异议主表保留为一等实体 |
| `data_objection_catalog/resource/use/content` | `objection_evidence` | 细分内容收敛为证据 |
| `data_objection_process` | `objection_process` | 流程轨迹保留 |
| `data_objection_evaluate` | `objection_evaluation` | 评价独立建模 |

### 9.5 审计/区块链映射

| legacy 表/模块 | 新表 | 说明 |
|---------------|------|------|
| `user_operation_log` / `sys_log` | `audit_event` | 保留为结构化事件流 |
| `data_cascade_record_log` / `data_cascade_interface_log` | `audit_event` | 级联与接口证据纳入统一审计 |
| `block_success_log` / `block_err_log` / `block_apilog` | `audit_receipt` + `anchor_outbox` | 外链结果不再散落到业务表 |
| `block_catalog` / `block_apply` / `block_resource` | `audit_receipt` 的 payload 来源 | 作为外链确认，不作为主业务状态机 |

### 9.6 dsp-dataservice 服务治理补充映射

`dsp-dataservice` 的服务治理迁移映射、旧结构数据证据、字段级规则和能力边界，以 `docs/reconstructs/dsp-dataservice-reconstruction-plan-v1.md` 为单一事实源。本基线只约束它必须落入以下 canonical 聚合与投影边界：

- API 服务本体进入 `resource_asset(resource_kind='api')`。
- API 调用通道、路由、契约、鉴权引用和网关策略进入 `resource_channel_binding`。
- 申请、审批、授权、发布、撤回进入 `application_record`、`approval_case`、`delivery_task` 与审计链。
- 网关心跳与服务调用统计只作为 B1.1 读侧投影，不成为业务事实源。
- 日志上链按 `anchor_outbox` + `audit_receipt` 处理，外链结果不反向驱动业务状态。
- 密钥、内部地址、工单个人信息不得明文进入 canonical DB、文档或日志。

### 9.7 租户/组织/权限映射

| legacy 表/模块 | 新表 | 说明 |
|---------------|------|------|
| `sys_department` / `sys_region` / `portal_organization` | `tenant_org_projection` | 作为 Governance 本地组织 / 区划投影，具体权威源和治理边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准 |
| `sys_user` / `sys_role` / `sys_permission` / `oauth_*` | Governance 投影 / 策略候选；认证秘密不入 core | **IAF IAM 是唯一认证权威源**，zw-brain 不复造认证 schema；用户 / 角色投影、绑定和权限映射边界以 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准 |

---

## 十、Capability 与数据层的一致性要求

### 10.1 每个写 Capability 必须声明的数据行为

任何 `human_confirmation_required = true` 或 `audit_class = write-*` 的 Capability，必须同时声明：

- 命中的聚合类型
- 可能变更的主状态字段
- 会写入的 `audit_event.event_type`
- 是否生成 `audit_receipt`
- 是否投递 `anchor_outbox`

示例：

| Capability | 目标聚合 | 主状态变化 | 审计事件 | 回执 |
|-----------|---------|-----------|---------|------|
| `catalog.entry.publish` | `catalog_entry` | `approved_pending_publish → active` | `catalog.entry.publish` | 审批回执 |
| `resource.apply` | `application_record` | `draft → submitted` | `application.submitted` | 人工确认回执 |
| `approval.decide` | `approval_case` + 目标实体 | `pending_decision → approved/rejected/returned_for_supplement` | `approval.decided` | 审批决策回执 |
| `delivery.provision` | `delivery_task` | `pending → provisioning/running` | `delivery.provision.started` | 交付回执 |
| `objection.accept` | `objection_case` | `submitted → accepted` | `objection.accepted` | 调查受理回执 |
| `registry.enable` | `tenant_capability_policy` | `enabled = false → true` | `capability.enabled` | 管理回执 |

### 10.2 禁止的做法

- 页面直接写 `brain_core`，绕过 command / audit / policy
- 注册包直接读写 `brain_core` 聚合根
- 通过 adapter 改写 legacy 表状态，反向充当新系统写入口
- 以消息中心或区块链成功日志代替正式审计事件

---

## 十一、分波次落地建议

### 11.1 Wave 0：首条黄金链路最小表集

优先创建：

- `tenant_org_projection`
- `blob_object`
- `catalog_model`
- `catalog_model_field`
- `catalog_entry`
- `catalog_item`
- `resource_asset`
- `resource_channel_binding`
- `application_record`
- `application_attachment`
- `approval_case`
- `approval_step`
- `approval_decision`
- `delivery_task`
- `delivery_receipt`
- `delivery_notice_projection`
- `capability_call`
- `audit_event`
- `audit_receipt`
- `gateway_runtime_status_projection`
- `service_invocation_metric_projection`
- `capability_package`
- `capability_version`
- `legacy_adapter_source`
- `legacy_object_mapping`

意义：已经足以打通 `发现 → 申请 → 审批 → 交付 → 审计` 首条黄金链路，并满足基线对"Registry 最小 schema"的要求，但**不提前展开完整租户级注册治理**。

### 11.2 Wave 1：交付深化与目录版本完善

继续补齐：

- `catalog_entry_version`
- `delivery_attempt`
- `delivery_subscription`
- `anchor_outbox`

说明：这一波服务 J1 找数→用数 主旅程闭环，不把 J2 挂数→维数 完整注册治理提前到 Wave 1。

### 11.3 Wave 2：异议闭环与最小注册治理

视真实需求再补：

- `objection_case`
- `objection_evidence`
- `objection_process`
- `objection_evaluation`
- `capability_exposure`
- `capability_review_record`
- `tenant_capability_policy`
- 更细的 projection / search 文档表
- B1.1 指标投影表
- 批量导入/导出任务表
- 更细粒度的 capability review / rollout 辅助表

---

## 十二、为什么这份设计符合架构基线，而不是又回到旧平台

### 12.1 它保留了复杂领域，但没有继承 legacy 系统切分

这份设计没有把 `dsp-catalog-platform`、`dsp-data-connect`、`dsp-objection-handling`、`dsp-blockchain` 原样迁入，而是把其**承重语义**重新收敛到：

- CatalogResourceAggregate
- ApplicationApprovalAggregate
- DeliveryAggregate
- ObjectionAggregate
- AuditAggregate
- CapabilityRegistryAggregate

这正是基线要求的"围绕旅程，不围绕模块名"。

### 12.2 它保留了合规与追责，但没有长成另一个大平台

- 审计、回执、上链 outbox 都存在
- 但没有重建消息中心、监控中心、门户中心、应用中心的大而全 schema
- 普通用户面对的是主旅程，后台治理面对的是最小 Registry 与 Audit

### 12.3 它符合确定性自动化运营和运维的最小运转面

- Phase 1 单 PostgreSQL 集群即可承载关键领域
- 通过 schema 保持清晰边界
- 通过 JSONB 承载可变结构，但不把主状态藏进 JSON
- 通过 `legacy_object_mapping` 把迁移与回放证据机械化，而不是靠口头同步

---

## 十三、待后续实现阶段确认的非阻塞问题

以下问题不影响本文作为详细数据设计基线，但在实现前需要落具体值：

1. `tenant_id` 的权威来源与编码规则
2. 组织投影同步频率与失效策略
3. 国家平台 / 区块链接口的正式 receipt schema
4. `resource_channel_binding.endpoint_ref` 的密钥引用规范
5. 哪些交付链路在 Wave 0 就需要 `delivery_subscription`
6. Search / Cache 是否首波用 PostgreSQL FTS，还是直接接入独立检索引擎

这些都属于 **实现参数**，不改变本文的聚合边界与表设计。

---

## 附录 A — legacy 长尾模块去向建议

| legacy 模块 | 建议去向 | 原因 |
|------------|---------|------|
| `message-center` | 外部通知适配器 | 通知不是主状态事实源 |
| `dsp-monitor` | 外部观测底座 | 监控是平台底座，不是主旅程聚合 |
| `app-center-server` | 外部应用目录/注册输入 | 不属于政务数据主旅程 |
| `dsp-pdf` | 对象存储 + 文档服务 | 文件管理不应反向成为主数据模型 |
| `portal-vue` / `catalog-front` | 前端实现输入，不入核心库表 | 前端状态不是权威数据模型 |
| `dsp-example` | 共享专区/专题包的外部内容源 | 不是首波核心聚合 |
| `dsp-basesubject` | **不复造**（基线 §5.6 #13） | 81 张独立表的并行编制系统；归外部数据治理中心或客户线下编制；本平台不重建 |

## 附录 B — 本文使用的主要旧库证据

- `old/代码信息抽取/代码信息抽取-27newbranch/All-Project_数据库表结构文档.md`
- `old/12-datastructure/dsp_catalog.xml`
- `old/12-datastructure/dsp_connect.xml`
- `old/12-datastructure/dsp_handling.xml`
- `old/12-datastructure/dsp_bsp.xml`
- `old/12-datastructure/dsp_block.xml`

## 文档维护说明

- 若架构基线的聚合边界、Capability 最小契约、物理存储分层发生变化，本文必须同步修订。
- 若后续实现决定拆分物理库，只允许调整部署层，不允许反向破坏本文的领域边界。
- 若新增 legacy 迁移来源，必须补充到 `legacy_adapter_source` / `legacy_object_mapping` 规则，而不是直接扩散旧表命名进 domain。