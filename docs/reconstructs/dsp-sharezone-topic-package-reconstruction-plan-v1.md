# dsp-sharezone / dsp-example / dsp-basesubject 共享专区与专题包重构方案 v1

> 范围：旧平台 `old/12-datastructure/dsp_catalog.xml` 中 `sharezone` / `catalog_share_group` 相关结构、`old/old_codes/dsp-sharezone`、`old/old_codes/dsp-example`、`old/old_codes/dsp-basesubject`，`old/代码信息抽取/代码信息抽取-27newbranch/dsp-example_*`、`dsp-basesubject_*`，以及 approved 中关于 P7 共享专区、专题包、一表通 / 基层报表减负、Capability Registry、租户策略和外部依赖的设计原则。
> 结论：zw-brain 保留“共享专区”作为 P7 主题化复用入口，但不迁成旧共享专区后台、示范应用后台或基础主题库系统；只吸收专题组织、目录 / 资源引用、可见组织策略、发布审核、复用证据、应用案例和主题库素材等承重语义，重建为 `TopicPackage` 投影 + `tenant_capability_policy` 可见性策略 + canonical 聚合引用。**首批专题包以 sd-default 山东省真实政务案例为标杆**（具体清单由业务方按客户优先级 sign-off，可参考 `m0-site-migration.md` 已列举的"医疗救助信息 / 医保码信息 / 异地就医统筹区开通信息"等真实高频目录）；"一表通 / 基层报表减负"在基线 §3.4 C 已**降级为可选预填 adapter**，归 Wave 2 候选专题之一（详见 `docs/approved/research-yibiaotong.md`），不再作为首批标杆。
> 单一事实源：本文是共享专区、专题包、示范应用和基础主题库内容源的专题单一事实源；目录、资源、申请、交付、异议、标准资产和能力注册的核心事实仍以对应 reconstructs 与 approved 数据模型为准；跨专题 greenfield 口径、统一 Capability 命名和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 〇、专题口径速览

- **旅程归属**：P7 共享专区是 **J1 找数→用数**（用户按主题快速发现 + 申请）+ **J2 挂数→维数**（运营方组织专题包）的复用入口；基线 §5.2 P7。
- **首批标杆**：sd-default 山东省高频跨部门政务场景（具体清单由业务方 sign-off，可参考 `m0-site-migration.md` 真实高频目录）；一表通定位为 Wave 2 候选可选 adapter（基线 §3.4 C）。
- **物理实现**：`TopicPackage` 系列 6 张表作为 `CapabilityRegistryAggregate` 的物理实现（专题为能力包的主题视图），schema 通过 SQLAlchemy `Base.metadata.drop_all + create_all` 管理（基线 §9.6），**不进入 alembic**。
- **R15 桥接面**：§四 12 个 Capability slug 通过统一 contract 投影到 5 消费面（WebUI / API / CLI / MCP / A2A），MCP / A2A 投影由 AgentRuntime `AGENT.yaml` 声明（基线 §8.1 / R15）；前端 UI 文案禁用 `package` / `projection` 工程术语（基线 §11 R12）。
- **可见性策略边界**：本文 §四 `topic.package.policy.update` Phase 1 仅支持组织 + 角色 + 消费面三维（与 §3.2 T2 一致），分级授权延后至 R14 表单 schema 化引擎 Wave 2 后再评估（与基线 §5.6 #3"目录分级授权本期不做"一致）。
- **basesubject 边界**：`dsp_basesubject` 81 张独立表**完全不复造**（基线 §5.6 #13）；本文档 §3 目标模型中 basesubject 仅作为专题素材 / 标准资产 evidence 候选输入，**不生成新事实源**（与本文 §1.2 / §1.5 一致）。
- **默认租户**：`tenant_id="sd-default"`，不启用 multi-tenant（基线 §8.2）。
- **角色与方向**：执行者限定基线 §5.1 7 角色码集合；专题包运营 = `ROLE_BUSIAUDIT`；专题包内容贡献 = `ROLE_ORGAN_MANAGER` / `ROLE_ORGAN_OPERATER`。

## 一、设计原则

### 1.1 Jobs：从“专区后台”改成“主题化复用入口”

旧共享专区的表面形态是专区创建、配置目录、部门授权、资源授权、上线审核、统计；旧示范应用是案例管理、发布、门户展示、评论反馈；旧基础主题库则混合了基础库、资源、档案、标准、统计、页面配置、流程和数据库配置。

zw-brain 不继承这些后台形态，只保留五类用户可感知价值：

1. 用户能围绕“一表通 / 基层报表减负”等场景快速看到一组可复用目录、资源、模板、说明和成功案例。
2. 运营方能把现有目录、资源、服务、模型、标准、案例组织成专题包，并配置适用组织、角色和消费面。
3. 使用方能从专题包直接发起订阅、申请、查看证据或提交异议，而不是在多套菜单中跳转。
4. 监管方能看到专题包的覆盖组织、使用量、申请转化、质量异议和复用成效。
5. Agent 能读取专题包结构、引用事实和证据，生成场景级复用建议，而不是维护另一套资源事实。

### 1.2 OPC：TopicPackage 是投影，不是第六个资源库

- 目录事实仍归属 `catalog_entry` / `catalog_item` / `catalog_model`。
- 资源事实仍归属 `resource_asset` / `resource_channel_binding`。
- 申请与订阅仍归属 `application_record` / `delivery_subscription` / `delivery_task` / `delivery_receipt`。
- 异议和质量反馈仍归属 `objection_case` / `objection_evidence`。
- 专题包只保存主题组织、引用、展示摘要、可见性策略、发布审核和运营指标投影，不复制目录 / 资源 / 申请 / 交付事实。
- `dsp-example` 的应用案例只作为可验证复用 evidence 或纵向上报素材，不恢复独立案例推广系统。
- `dsp-basesubject` 的基础主题、档案、标准和统计只作为专题素材或标准资产 adapter 输入，不复造主题库建库平台。

### 1.3 为什么共享专区必须保留但不能原样迁入

1. approved 已将共享专区从“可砍功能”修订为 P7 必保留产品形态，原因是旧平台问题在于入口埋深和无订阅闭环，而非需求不存在。
2. 基层报表减负需要把目录、资源、模板、案例和证据按场景打包，单纯搜索目录无法形成端到端复用体验。
3. 旧 `share_zone_*` 已证明专区需要目录绑定、组织可见、授权、上线审核和统计，但这些都应落到统一策略、申请、交付和审计链路。
4. 旧示范应用和基础主题库混入大量门户、报表、页面配置、数据库配置，原样迁入会把 zw-brain 拉回多后台拼接形态。

### 1.4 旧业务逻辑继承规则

专区创建、目录 / 资源绑定、组织可见、资源授权、上线审核、下线、统计和案例发布等业务逻辑，默认以旧 `share_zone_*`、`catalog_share_group`、`Example*` 与 `dsp-basesubject` 代码实现为实施依据。只有当旧逻辑试图让共享专区成为第二套目录 / 资源 / 授权事实源、迁入 `app_key` / 数据库连接 / 页面引擎配置，或绕过统一租户策略时，才进入独立决策。

### 1.5 全新项目口径

本专题不提供旧共享专区、示范应用门户、基础主题库页面引擎、评论社区、旧授权规则或旧 URL 兼容层。TopicPackage 只是 P7 投影和复用入口，不拥有目录、资源、申请、交付、异议或服务授权事实。

## 二、证据清单

### 2.1 approved 与既有 reconstructs 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture.md` | 共享专区作为 P7 产品形态保留，但不复刻旧平台菜单导航；五消费面共享 Capability 契约。 |
| `docs/approved/zw-brain-data-model.md` | `tenant_capability_policy` 控制租户级启停与暴露面；目录、资源、申请、交付、异议已有 canonical 聚合。 |
| `docs/approved/research-yibiaotong.md` | 一表通 / 基层报表减负需要将上级交换和基层填报链路组织成可复用场景。 |
| `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md` | 共享专区保留为 P7 主题 / 分组投影；权限裁决走统一租户策略。 |
| `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md` | 专题包内的订阅、申请和交付必须进入申请 / 交付主链路，不在专区内自建流程。 |
| `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md` | 案例 / 专题包如需上报国家平台，应通过 `adapter.national.topic.report`，不在专区内部实现外部协议。 |
| `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` | 专区可见性、组织授权和消费面暴露应收敛到 Registry 与租户策略，不迁旧菜单 / 按钮权限。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | `dsp-sharezone` + `dsp-example` + `dsp-basesubject` 定位为 P1 共享专区 / 专题包内容源专题。 |

### 2.2 旧 sharezone 表证据

`old/12-datastructure/dsp_catalog.xml` 中 `sharezone` 模块显示旧共享专区至少包含以下承重语义：

| 旧表 | 承重语义 | zw-brain 解释 |
| --- | --- | --- |
| `share_zone` | 专区 ID、名称、所属部门、创建人、状态、简介、logo、下线状态 | `topic_package` 展示摘要、发布状态和运营归属。 |
| `share_zone_catalog_link` | 专区关联目录、提供方、共享范围、取消状态 | `topic_package_item` 引用 `catalog_entry`，不复制目录事实。 |
| `share_zone_org_link` | 专区关联部门 | `topic_package_visibility` 或 `tenant_capability_policy` 条件。 |
| `share_zone_resource_auth` | 专区资源授权规则、资源、目录、调用频次、服务时间和期限 | 专题包资源引用 + 申请 / 交付策略模板候选。 |
| `share_zone_org_auth` | 使用部门、资源、规则、申请 ID、授权状态 | `delivery_subscription` / `application_record` / receipt 的专题投影。 |
| `share_zone_approve` | 上线审核环节、意见、处理人、审核结果 | `topic_package_review_record` 或 `capability_review_record`。 |
| `share_zone_appkey` | 使用部门、应用系统、资源、服务调用密钥 | 只保留外部应用 / 授权映射；`app_key` 不迁入。 |
| `share_zone_statistics`、`share_zone_org_auth_statistic` | 关联部门数、目录数、资源数、调用 / 交换统计 | B1.1 / P7 运营 projection，不作为可写事实。 |
| `catalog_share_group` | 目录共享分组、归属部门、排序、状态 | 专题包分组候选或目录分组迁移 evidence。 |
| `share_group_permission` | 用户 / 部门对共享分组的权限 | `tenant_capability_policy` 候选，需人工审核后生效。 |

旧 `share_zone.status` 可映射为专题包发布状态：

| 旧状态 | 新解释 |
| --- | --- |
| `0 草稿` | `draft`。 |
| `1 待配置` | `configuring`。 |
| `2 已配置` | `configured`。 |
| `3 待审核` | `submitted`。 |
| `4 上线` | `published`。 |
| `6 已驳回` | `rejected`。 |
| `-1 下线` | `offline`。 |

### 2.3 旧 dsp-example 证据

`dsp-example_对外提供API清单.md` 显示旧示范应用有六类能力：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/dsp/example/new/manage/*` | 管理示范应用、关联目录资源、维护示范项 | `topic.package.evidence.attach`，案例作为专题包 evidence。 |
| `/dsp/example/publish/*` | 发布、取消发布、关联示范 | `topic.package.publish` 或案例素材发布审核。 |
| `/dsp/example/report/*` | 示范应用报表、添加、取消 | B1.1 / P7 运营 projection 或纵向案例上报素材。 |
| `/dsp/example/web/*` | 门户列表、资源、需求、评论、反馈 | P7 专题详情读模型，不迁旧门户页面。 |
| `/restapi/portal/*` | 统计数量、详情、示范项、列表 | `topic.package.query` / `topic.package.metric.query` 的 REST 投影。 |
| `/dsp/organization/*` | 组织树、全国组织 | 组织投影；权威组织源不在示范应用内。 |

表结构文档显示：

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `Example` | 示范名称、描述、类型、组织、状态 | `topic_package_evidence` 的 case evidence 或专题包描述素材。 |
| `ExampleItem` | 示范项键值和排序 | case evidence 结构化内容。 |
| `ExampleResource` | 示范关联资源 | `topic_package_item` 引用 `resource_asset`。 |
| `ExampleLink` | 示范关联对象 | legacy mapping / evidence link。 |
| `ExampleFile` | 附件文件 | 对象存储受控引用，不迁内部 `file_path` 为公开字段。 |
| `ExampleComment`、`ExampleFeedback` | 评论与反馈 | 可转运营反馈 evidence 或 `objection_case`，不建评论社区。 |
| `ExampleCollection` | 收藏 | 用户偏好 projection，默认不进核心。 |
| `ExampleContact` | 联系人、电话、邮箱 | 联系方式按敏感信息策略处理，只保存快照或脱敏摘要。 |

### 2.4 旧 dsp-basesubject 证据

`dsp-basesubject_对外提供API清单.md` 显示基础主题库覆盖范围远超“专题包”：

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/basesubject/info/*`、`/basesubject/schema/*` | 基础库与方案管理 | 专题素材候选或 `catalog_model` evidence，不成为主题库事实源。 |
| `/resource/*`、`/resource/approve/*`、`/resource/revoke/*` | 资源管理、审核、撤销 | 已归属目录 / 资源与申请 / 审核链路，不在专题包内复刻。 |
| `/archive/type/*`、`/archive/template/*`、`/archive/data/*`、`/archive/sync/*` | 档案类型、模板、数据、同步任务 | 外部档案 / 知识素材 adapter；同步日志进入 adapter run record。 |
| `/catalog/*` | 目录管理与统计 | 目录事实归属 `catalog_entry`；统计为 projection。 |
| `/standard/api/*`、`/standard/element/*` | 标准 API、数据元素 | 标准资产 adapter 或 `catalog_model` evidence。 |
| `/statistic/population/*`、`/statistic/corporation/*`、`/statistic/subject/*` | 人口、法人、主题统计 | B1.1 / P7 指标 projection，不作为事实源。 |
| `/page/template/*`、`/page/module/*`、`/page/column/*` | 页面模板、模块、字段配置 | WebUI 产品配置参考，不迁旧页面引擎。 |
| `/procedure/*` | 流程配置 | 不迁通用流程后台；专题包审核走 Registry / review record。 |
| `/database/*`、`/database/test` | 数据库配置和连通性测试 | 禁止迁入连接信息、账号和密钥。 |
| `/task/*` | 定时任务和日志 | 外部调度器 / adapter run record。 |

## 三、目标模型

### 3.1 TopicPackage 投影边界

建议新增逻辑投影，不新增独立主事实聚合：

- `topic_package`：专题包元信息、场景说明、归属租户 / 组织、发布状态、展示摘要。
- `topic_package_item`：专题内引用项，可引用目录、资源、目录模型、标准、申请模板、交付订阅、异议证据、案例 evidence。
- `topic_package_visibility`：适用组织、角色、岗位、租户范围、消费面；最终由 `tenant_capability_policy` 裁决。
- `topic_package_review_record`：发布、驳回、下线、配置变更审核轨迹。
- `topic_package_evidence`：应用案例、复用成效、附件、反馈、国家 / 上级上报 receipt、异议和质量证据。
- `topic_package_metric_projection`：浏览、订阅、申请、交付、调用、交换、异议、满意度等运营指标。

这些结构不拥有：

1. 目录 / 资源 / 申请 / 交付 / 异议的权威状态。
2. API 调用密钥、数据库连接、文件内部路径、页面模板引擎配置。
3. 独立评论社区、收藏系统、绩效系统或案例推广工作流。

### 3.2 TopicPackage 引用类型

| 引用类型 | 关联对象 | 旧来源 |
| --- | --- | --- |
| `catalog` | `catalog_entry` / `catalog_item` | `share_zone_catalog_link`、`ExampleResource`、`dsp-basesubject /catalog/*`。 |
| `resource` | `resource_asset` / `resource_channel_binding` | `share_zone_resource_auth`、`ExampleResource`、`/resource/*`。 |
| `model` | `catalog_model` / `catalog_model_field` | `basesubject schema`、标准元素、旧目录模型。 |
| `subscription` | `delivery_subscription` | 专区授权和复用订阅投影。 |
| `application_template` | `application_record.intent_snapshot` 模板 | 专题包复用申请入口。 |
| `case_evidence` | `topic_package_evidence` / object storage | `Example`、`ExampleItem`、`ExampleFile`。 |
| `objection` | `objection_case` / `objection_evidence` | 评论反馈、质量问题和复用争议。 |
| `external_receipt` | adapter receipt / external mapping | 国家 / 上级案例或专题上报回执。 |

### 3.3 发布状态机

| 新状态 | 旧状态 / 旧动作 | 说明 |
| --- | --- | --- |
| `draft` | `share_zone.status=0` | 运营方创建但未配置。 |
| `configuring` | `status=1` | 正在选择目录、资源、模型、案例和可见组织。 |
| `configured` | `status=2` | 配置完成，尚未提交审核。 |
| `submitted` | `status=3` | 等待发布审核。 |
| `published` | `status=4` / 示例发布 | 对允许的消费面和组织可见。 |
| `rejected` | `status=6` | 审核驳回，保留意见。 |
| `offline_pending` | `offline=1` | 下线待审核。 |
| `offline` | `status=-1` | 不再对消费面展示。 |

状态推进规则：

1. `published` 前必须至少绑定一个 canonical 引用项和一条可见性策略。
2. 发布、下线、策略变更必须写 `topic_package_review_record`、`audit_event` 和 `capability_call`。
3. 删除旧引用只能标记 retired / removed，不删除 canonical 对象。
4. `published` 后的目录、资源状态变化由读模型刷新反映，专题包不得反向覆盖源状态。

## 四、Capability 设计

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `topic.package.create` | 写 | `write-trace` | 创建专题包草稿。 |
| `topic.package.configure` | 写 | `write-trace` | 绑定目录、资源、模型、案例和场景说明。 |
| `topic.package.submit` | 写 | `approval-trace` | 提交专题包发布审核。 |
| `topic.package.review` | 写 | `approval-trace` | 审核、驳回、下线或恢复专题包。 |
| `topic.package.publish` | 写 | `approval-trace` | 发布到 WebUI / REST / MCP 等消费面。 |
| `topic.package.policy.update` | 写 | `approval-trace` | 配置可见组织、角色、租户和消费面策略。 |
| `topic.package.subscribe` | 写 | `approval-trace` | 从专题包发起资源订阅或复用申请。 |
| `topic.package.evidence.attach` | 写 | `write-trace` | 关联应用案例、复用成效、附件、反馈和外部回执。 |
| `topic.package.query` | 读 | `read-trace` | 查询专题包列表、详情和引用项。 |
| `topic.package.metric.query` | 读 | `read-trace` | 查询覆盖、订阅、交付、调用、异议等运营指标。 |
| `adapter.national.topic.report` | 写 | `write-trace` | 如需上报国家 / 上级平台，交由直达 adapter 执行。 |
| `legacy.sharezone.mapping.import` | 写 | `write-trace` | 导入旧专区、案例、基础主题库映射和待审核候选。 |

消费面：

- WebUI：P7 共享专区 / 专题包详情、P2 资源发现入口、P5 供给侧治理入口、B1.1 运营指标入口。
- REST：对外查询专题包、专题资源清单和复用成效。
- CLI：迁移导入、策略检查、指标导出。
- MCP：Agent 查询专题结构、资源证据和复用建议。
- A2A：外部 Agent / Skill 注册专题素材或上报复用结果，必须走审核。

## 五、旧表到新系统映射

| 旧字段 / 旧表 | 新落位 | 说明 |
| --- | --- | --- |
| `share_zone.zone_id` | `legacy_object_mapping.legacy_id` + `topic_package.id` | 新主键不沿用旧 ID。 |
| `share_zone.name/description/zone_logo` | `topic_package.display_snapshot` | logo 仅保存对象存储引用。 |
| `share_zone.org_code/org_name` | `topic_package.owner_org_snapshot` | 组织来源和 Governance 边界以 `dsp-bsp-manage-governance-reconstruction-plan-v1.md` 为准。 |
| `share_zone.creator_id/creator_name/contact_phone` | actor snapshot / owner snapshot | 联系方式按敏感信息策略处理。 |
| `share_zone.status/offline` | `topic_package.status` | 按本文状态机映射。 |
| `share_zone_catalog_link.cata_id` | `topic_package_item.ref_id` | 引用 `catalog_entry`；未解析进入 unresolved。 |
| `share_zone_catalog_link.share_range` | `topic_package_visibility` / policy condition | 公开 / 专区可见映射为策略。 |
| `share_zone_org_link.*` | `topic_package_visibility` | 组织可见范围。 |
| `share_zone_resource_auth.res_id/rule_id` | `topic_package_item` + policy template候选 | 不直接生成授权事实。 |
| `share_zone_org_auth.apply_id` | `application_record` / `delivery_subscription` projection | 只作为复用链路证据。 |
| `share_zone_appkey.app_key` | 不迁 | 服务调用密钥禁止迁入。 |
| `share_zone_approve.*` | `topic_package_review_record` + audit | 审核意见和处理人快照。 |
| `share_zone_statistics.*` | `topic_package_metric_projection` | 统计为只读投影。 |
| `catalog_share_group.*` | `topic_package` / group evidence | 共享分组可转专题包候选。 |
| `share_group_permission.*` | `tenant_capability_policy` 候选 | 人工审核后才可生效。 |
| `Example.*` | `topic_package_evidence` | 应用案例证据。 |
| `ExampleResource.resource_id` | `topic_package_item` | 关联资源引用。 |
| `ExampleFile.file_path` | object storage legacy ref | 不公开内部路径。 |
| `ExampleComment` / `ExampleFeedback` | feedback evidence / `objection_case` 候选 | 按问题类型归属。 |
| `ExampleContact.*` | evidence actor / org snapshot | 联系信息脱敏。 |
| `basesubject schema/resource/archive/standard` | 专题素材、标准资产或 catalog model evidence | 不生成独立主题库事实源。 |
| `basesubject database/task/page/procedure` | 不迁或 adapter run record | 禁止迁入连接配置和通用页面 / 流程后台。 |

## 六、策略与复用链路

### 6.1 可见性策略

专题包可见性必须统一进入租户策略，不允许旧 `share_group_permission` 或专区部门表直接控制 WebUI：

| 输入 | 说明 |
| --- | --- |
| `tenant_id` | 租户。 |
| `topic_package_id` | 专题包。 |
| `actor_snapshot` | 用户 / service / agent 快照。 |
| `org_snapshot` | 组织与区划快照。 |
| `role_codes` | IAF IAM、BSP 导入和 zw-brain Governance 映射后的角色。 |
| `surface` | `webui/api/cli/mcp/a2a`。 |
| `intent` | `view/subscribe/attach_evidence/review/admin`。 |

输出沿用 `tenant.policy.evaluate`：`allowed`、`decision_reason`、`human_confirmation_required`、`audit_class`、`policy_version`。

### 6.2 从专题包发起复用

专题包不直接授予资源使用权，黄金路径应为：

1. 用户在 P7 专题包看到目录、资源、模型、案例和适用说明。
2. 系统调用 `tenant.policy.evaluate` 判断是否可见和是否可发起复用。
3. 用户选择资源或模板，调用 `topic.package.subscribe`。
4. `topic.package.subscribe` 生成 `application_record` 或 `delivery_subscription`，写明来源专题包。
5. 审批、授权、交付、回执进入申请 / 交付主链路。
6. 指标投影回写专题包的申请转化、交付成功、调用量和异议率。

### 6.3 案例与成效证据

应用案例必须可追溯到事实证据：

- 复用了哪些目录、资源、模型或服务。
- 覆盖了哪些组织、岗位或报表场景。
- 产生了哪些申请、交付、订阅或调用回执。
- 是否发生异议、反馈或质量问题。
- 如上报国家 / 上级平台，应保存 external mapping 与 receipt。

## 七、迁移与验证策略

### 7.1 迁移步骤

1. 登记 `legacy_adapter_source`：`dsp-sharezone`、`dsp-example`、`dsp-basesubject`、`dsp_catalog.xml`。
2. 导入 `share_zone`、`catalog_share_group` 为专题包候选。
3. 解析 `share_zone_catalog_link`、`share_zone_resource_auth`、`ExampleResource` 到 canonical 目录 / 资源引用。
4. 解析 `share_zone_org_link`、`share_group_permission` 为可见性策略候选，默认 pending。
5. 导入 `share_zone_approve` 为审核历史 evidence。
6. 导入 `Example`、`ExampleItem`、`ExampleFile`、`ExampleLink` 为案例 evidence。
7. 将 `ExampleComment`、`ExampleFeedback` 按类型转运营反馈 evidence 或异议候选。
8. 对 `app_key`、内部文件路径、联系人、电话、邮箱、数据库连接、任务配置做排除或脱敏。
9. 旧基础主题库只抽取能关联到目录模型、标准资产或专题说明的素材，其他页面 / 流程 / 数据库配置不迁。
10. 对无法解析的目录、资源、组织、案例引用建立 unresolved 清单，禁止自动写入核心事实。

### 7.2 验证样本

最小样本必须覆盖：

1. 一个旧 `share_zone` 草稿迁移为 `topic_package=draft`。
2. 一个已上线专区迁移为 `published`，并能查询关联目录、资源和组织可见范围。
3. 一个专区目录引用能解析到 `catalog_entry`，无法解析的进入 unresolved。
4. 一个专区资源授权不直接生效，只生成策略候选。
5. 一个旧应用案例关联多个资源并成为专题包 evidence。
6. 一个案例反馈按问题类型进入运营反馈或异议候选。
7. 一个用户从专题包发起订阅后进入 `application_record` / `delivery_subscription` 主链路。
8. 一个组织不在可见范围内时，WebUI / REST / MCP 均不可见。
9. 一个专题包下线后不再出现在 P7 入口，但历史 evidence 和指标仍可审计。
10. 一个 `dsp-basesubject` 标准元素只进入标准 / 目录模型 evidence，不生成独立主题库。

## 八、不做清单

1. 不复刻旧共享专区后台、菜单、页面和旧 URL。
2. 不把共享专区建成目录、资源、申请、交付之外的第二事实源。
3. 不迁 `share_zone_appkey.app_key`、数据库连接、内部文件路径、联系人敏感信息和任务配置。
4. 不直接把旧专区部门 / 用户权限变成生产策略，必须人工审核后写入 `tenant_capability_policy`。
5. 不恢复 `dsp-example` 的独立示范应用门户、评论社区和案例推广后台。
6. 不把 `dsp-basesubject` 迁成新的基础库 / 档案库 / 页面配置 / 流程配置 / 数据库配置平台。
7. 不在专题包内实现国家平台 / 上级平台上报协议；统一交由 adapter。
8. 不在专题包内直接修改目录、资源、服务或源数据。
9. 不把统计 projection 作为可写事实源。

## 九、专题差异决策

全局专题包发布审核机制、租户策略和 greenfield 口径以总览方案第八节为准。本专题只保留共享专区 / 专题包的产品差异：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| T1 | 首批标杆场景 | **首批 P7 专题包以 sd-default 山东省高频跨部门政务场景为标杆**（具体清单由业务方按客户优先级 sign-off；可参考 `m0-site-migration.md` 已列举的"医疗救助信息 / 医保码信息 / 异地就医统筹区开通信息"等真实高频目录）；"一表通 / 基层报表减负"按基线 §3.4 C 降级为 Wave 2 候选可选 adapter（与 `docs/approved/research-yibiaotong.md` Wave 2 同步），不作为首批标杆；企业服务、人口、法人等主题作为后续扩展。 | 专题包必须引用 canonical 目录 / 资源 / 模型 / 申请模板 / evidence，不新建主题库事实。 |
| T2 | 可见性策略维度 | 首版支持组织 + 角色 + 区划 + 消费面；岗位、业务条线、专题准入条件后续扩展。 | 策略输入至少包含 `tenant_id`、`org_snapshot`、`role_codes`、`region_code`、`surface`、`intent`。 |
| T3 | 旧资源授权规则迁移等级 | 旧 `share_zone_resource_auth` 只作为策略模板候选，不自动生效。 | 经人工审核后可转为专题可见性策略、申请模板或交付订阅限制。 |
| T4 | 应用案例是否继续上报国家 / 上级平台 | 首版只保留上报能力，不默认全量上报；按专题包或案例显式触发。 | 上报必须走 `adapter.national.topic.report` 并保存 external mapping 与 receipt。 |
| T5 | 案例评论和反馈归属 | 默认进入低风险运营反馈 evidence；涉及质量、授权、交付争议时转异议候选。 | 不恢复评论社区；联系人信息必须脱敏或不迁。 |

## 十、证据来源

- `old/12-datastructure/dsp_catalog.xml`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-example_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-example_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-example_外部SDK和接口文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-basesubject_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-basesubject_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-basesubject_外部SDK和接口文档.md`
- `old/integrated-bigdata-platform/README.md`
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/zw-brain-data-model.md`
- `docs/approved/research-yibiaotong.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md`
