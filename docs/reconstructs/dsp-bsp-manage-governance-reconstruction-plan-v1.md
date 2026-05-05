# dsp-bsp / dsp-manage / dsp-ucenter 治理底座重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-bsp`、`old/old_codes/dsp-manage`、`old/old_codes/dsp-ucenter`，`old/代码信息抽取/代码信息抽取-27newbranch/dsp-bsp_*`、`dsp-manage_*`、`dsp-ucenter_*`，旧结构数据 `old/12-datastructure/dsp_bsp.xml`，以及 approved 中关于 Capability Registry、租户策略、五消费面和外部依赖的设计原则。
> 结论：zw-brain 不迁入旧 `dsp-bsp` / `dsp-ucenter` 的自建 IAM、登录、密码、短信、CA、SSO、菜单、按钮权限和系统配置后台，也不把 `dsp-manage` 迁成新的综合管理控制台；只吸收组织 / 区划投影、用户快照、角色语义、租户级 Capability 启停、暴露面策略和注册审核等承重治理语义，重建为 `brain_registry` + 最小组织投影 + 外部 IAM adapter。
> 单一事实源：本文是旧 BSP / manage / ucenter 的治理语义迁移、Capability 注册治理、租户策略和外化边界的专题单一事实源；跨专题 greenfield 口径、统一 Capability 命名和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 一、设计原则

### 1.1 Jobs：从“基础支撑平台后台”改成“能力能否安全暴露”

旧 BSP 的表面形态是用户、角色、权限、菜单、组织、区域、应用、证书、字典、帮助、日志、登录和配置后台；旧 ucenter 是登录、OAuth、SAML、CAS、IAM、短信、扫码、CA/UKey 和门户入口；旧 manage 则混合了目录、资源申请、绩效、报表、统计、消息和配置。

zw-brain 不继承这些后台模块，只保留五类治理价值：

1. 能识别调用者是谁、属于哪个组织和租户，以及当时的角色 / 岗位快照。
2. 能判断某租户是否启用某 Capability 包、某版本和某消费面。
3. 能审核 Capability 包是否允许暴露到 WebUI / REST / CLI / MCP / A2A。
4. 能为主旅程保存组织、区划、角色、权限裁决的可审计证据。
5. 能从外部 IAM / 组织源同步只读投影，而不是自建完整身份系统。

### 1.2 OPC：Registry 是能力治理的单一事实源

- Capability 包、版本、暴露面、审核记录、租户启停策略以 `brain_registry` 为唯一事实源。
- WebUI 动作、REST / OpenAPI、CLI、MCP、A2A 产物必须由 Registry 派生，不允许像旧 BSP 一样靠菜单 SQL 和按钮权限分散维护。
- 用户、组织、角色只保存快照和只读投影；认证、密码、Token、短信、CA、SSO 默认外部化。
- 审计由 `capability_call` / `audit_event` 承载，不迁旧 `sys_log` 为新审计事实源。
- `dsp-manage` 中目录、申请、绩效、报表、消息等业务后台不纳入本专题；分别归属目录、申请交付、P6 projection 或外部 adapter。

### 1.3 为什么不能迁成完整 IAM

1. approved 明确国家平台、集团平台、外部依赖不在大脑内复造；IAM 在架构图中是外部边界。
2. 旧 ucenter 覆盖 OAuth、SAML、IAM、CAS、CA/UKey、短信、扫码和多个地方化登录入口，迁入会把 zw-brain 拖回“大而全平台”。
3. zw-brain 真正需要的是“谁调用了哪个能力，是否有权，是否留痕”，而不是自建账号生命周期。
4. 不同客户现场的统一身份源可能不同，必须通过 adapter 和环境配置接入。

### 1.4 旧业务逻辑继承规则

组织、区划、用户、角色、权限、菜单与日志的字段含义、层级关系和历史映射，默认以旧 `dsp-bsp`、`dsp-ucenter`、`dsp-manage` 代码和 `dsp_bsp.xml` 为实施依据。但旧平台的登录、密码、Token、菜单、按钮权限和权限 SQL 不能直接成为新系统生产鉴权事实；只有经权威源确认和人工审核后，才能进入 `actor_projection`、`org_projection`、`role_projection` 或 `tenant_capability_policy`。

### 1.5 全新项目口径

本专题不提供旧 BSP、ucenter、manage 的 URL、菜单、按钮权限、登录态或后台页面兼容层。旧权限和菜单只能作为候选映射，经 Registry 与 `tenant_capability_policy` 审核后转写为新能力策略。

## 二、证据清单

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture-v4-gpt55.md` | 五消费面共享同一套 Skill / Capability 契约；新增能力默认外部生产、平台注册。 |
| `docs/approved/zw-brain-data-model-v4-gpt55.md` | `brain_registry` 派生 WebUI、REST、CLI、MCP、A2A；`tenant_capability_policy` 控制租户级启停与暴露面。 |
| `docs/approved/research-yibiaotong-zw-brain-v4.md` | 基层报表减负需要按权限取数和全程留痕，但不要求复造身份平台。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | `dsp-bsp` / `dsp-manage` / `dsp-ucenter` 被列为 P1，只抽取最小租户策略、能力注册治理和组织投影。 |
| `old/integrated-bigdata-platform/README.md` | 旧基础支撑是自建统一用户、角色、权限、菜单、参数、日志体系，所有旧系统菜单和权限依赖它。 |

### 2.2 旧 BSP API 证据

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/bsp/user/*` | 用户增删改查、密码重置、修改密码 | 认证与账号生命周期外部化；只保留 actor snapshot 和用户投影。 |
| `/bsp/role/*` | 角色管理、角色权限配置 | 角色仅作为策略输入和审计快照，不复刻角色后台。 |
| `/bsp/permission/*` | 权限管理 | 映射为 Capability policy，不迁按钮 / 接口权限树。 |
| `/bsp/menu/*` | 菜单树和菜单配置 | WebUI 动作由 Registry 派生，不迁菜单表。 |
| `/bsp/organ/*`、`/bsp/region/*` | 组织、区域树 | 只读组织 / 区划投影，可作为 tenant / org policy 输入。 |
| `/bsp/app/*` | 应用管理和审核 | 外部应用目录 / Capability package source，默认不进核心。 |
| `/bsp/certificate/*` | 证书管理 | 外部密钥 / 证书系统，不迁。 |
| `/bsp/dict/*` | 数据字典 | 只迁必要业务字典到对应领域，不建通用字典后台。 |
| `/bsp/log/*` | 操作日志 | `audit_event` / `capability_call`，旧日志只作迁移 evidence。 |
| `/restapi/getAuthorities` | 用户权限查询 | `tenant.policy.evaluate` 或 auth adapter。 |

### 2.3 旧 BSP 表证据

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `sys_user` | 用户身份、状态、联系方式、登录信息 | 外部 IAM 用户投影；密码、登录 IP、头像等不进核心。 |
| `sys_role` | 角色编码和名称 | `role_snapshot` / policy condition。 |
| `sys_permission` | 菜单、按钮、接口权限 | 映射为 Capability / exposure / policy，不迁权限树。 |
| `sys_menu` | 路由、组件、图标、排序 | 不迁；WebUI 由产品设计和 Registry 派生。 |
| `sys_department` | 部门、层级、区划、联系方式 | `org_projection` / actor snapshot。 |
| `sys_region` | 区划树 | `region_projection`。 |
| `sys_user_role`、`sys_role_permission`、`sys_user_department` | 用户-角色-部门关系 | 只作为迁移参考和策略输入，不直接成为授权事实源。 |
| `sys_dict`、`sys_dict_item` | 数据字典 | 按领域迁移，禁止全局字典平台化。 |
| `sys_log` | 操作、登录、异常日志 | `audit_event` 或历史 evidence。 |
| `sys_config` | 系统 / 业务配置 | 环境变量和 Registry 配置，不迁旧配置中心。 |
| `sys_file` | 文件路径和存储类型 | 对象存储引用，不迁内部路径。 |

### 2.4 旧 ucenter 证据

`dsp-ucenter` 覆盖登录、验证码、OAuth2、SAML2、IAM SSO、CAS、密码重置、扫码、OTP、CA/UKey、短信、第三方地方化登录、Token 和导航菜单。数据库仅包含 `user`、`authority`、`user_authority`、`oauth_access_token`、`oauth_refresh_token`。

新系统处理：

| 旧能力 | 新边界 |
| --- | --- |
| 登录、登出、注册、密码、验证码 | 外部 IAM，不迁。 |
| OAuth / SAML / CAS / IAM SSO | IAM adapter，后续实现配置。 |
| CA / UKey / 短信 / 扫码 | 外部认证因子，不进核心模型。 |
| OAuth access / refresh token | 禁止迁入；运行时由外部身份源管理。 |
| `authority` / `user_authority` | 只作为角色快照或策略输入。 |
| `/getNavigation`、`/queryUserSystem` | WebUI 导航由 Registry / 产品页面生成，不迁旧门户导航。 |

### 2.5 旧 manage 证据

`dsp-manage` 并不是纯治理底座，而是目录管理、绩效系统、报表、统计、反馈、消息、系统配置和接口调用统计的混合后台。对本专题只保留三类输入：

1. 组织编码、用户编码、统计中的 org_code / user 信息，作为投影和审计快照线索。
2. 接口调用统计，可映射到 `service_invocation_metric_projection` 或 `audit_event`。
3. 反馈管理可映射到异议 / 运营反馈 evidence。

不纳入本专题：目录、目录组、目录审批、资源申请、汇聚、绩效、报表、消息中心和系统配置；这些已有或应另归属对应专题。

## 三、目标模型

### 3.1 Registry 聚合

沿用 approved `brain_registry`：

- `capability_package`：能力包元信息。
- `capability_version`：版本、schema、auth policy、tenant scope、audit class、runtime binding。
- `capability_exposure`：WebUI / REST / CLI / MCP / A2A 暴露面。
- `capability_review_record`：审核、禁用、回滚、归档决策。
- `tenant_capability_policy`：租户级启停、版本、生效消费面和权限覆盖。
- `legacy_adapter_source` / `legacy_object_mapping`：旧源和旧对象映射。

旧 BSP 的菜单、权限、按钮、系统配置只允许作为迁移参考，不生成 Registry 的事实。

### 3.2 最小组织与身份投影

建议实现只读投影，不作为 IAM：

| 投影 | 用途 | 来源 |
| --- | --- | --- |
| `tenant_projection` | 租户标识、名称、状态、来源 | 环境配置 / 外部租户源 / BSP 迁移。 |
| `org_projection` | 组织编码、名称、父子关系、区划、状态 | BSP / ucenter / 外部组织源。 |
| `region_projection` | 区划编码、名称、层级、父子关系 | BSP region / 国家区划源。 |
| `actor_projection` | 用户外部 ID、姓名、组织、角色摘要、状态 | 外部 IAM adapter。 |
| `role_projection` | 角色编码、名称、来源、适用租户 | BSP role / IAM group。 |

这些投影只用于：

1. 构建 `actor_snapshot`。
2. 支持 `tenant.policy.evaluate`。
3. 支持 WebUI 可见性和 P6 审计筛选。
4. 做 legacy ID 映射。

### 3.3 策略裁决输入

`tenant.policy.evaluate` 的最小输入：

| 输入 | 说明 |
| --- | --- |
| `tenant_id` | 租户。 |
| `actor_snapshot` | 用户 / service / agent 快照。 |
| `org_snapshot` | 组织和区划快照。 |
| `role_codes` | 外部 IAM / BSP 映射后的角色。 |
| `capability_slug` | 能力标识。 |
| `surface` | `webui/api/cli/mcp/a2a`。 |
| `target_ref` | 可选目标对象，如 catalog/resource/application。 |
| `risk_context` | 是否跨租户、是否写操作、是否需人工确认。 |

输出：

| 输出 | 说明 |
| --- | --- |
| `allowed` | 是否允许。 |
| `decision_reason` | 命中策略说明。 |
| `human_confirmation_required` | 是否需要人工确认。 |
| `audit_class` | 审计等级。 |
| `policy_version` | 策略版本。 |

## 四、Capability 设计

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `capability.package.register` | 写 | `approval-trace` | 注册能力包草稿。 |
| `capability.version.submit` | 写 | `approval-trace` | 提交能力版本审核。 |
| `capability.version.review` | 写 | `approval-trace` | 审核、驳回、禁用、回滚能力版本。 |
| `capability.exposure.configure` | 写 | `approval-trace` | 配置版本暴露到哪些消费面。 |
| `tenant.capability.enable` | 写 | `approval-trace` | 启用租户能力包。 |
| `tenant.capability.disable` | 写 | `approval-trace` | 禁用租户能力包。 |
| `tenant.policy.evaluate` | 读 | `read-trace` | 判断调用者是否可调用某能力。 |
| `org.projection.sync` | 写 | `write-trace` | 从外部组织源同步只读组织投影。 |
| `actor.projection.sync` | 写 | `write-trace` | 从外部 IAM 同步用户 / 角色投影。 |
| `registry.artifact.export` | 读 | `read-trace` | 导出 WebUI / OpenAPI / CLI / MCP / A2A 产物。 |
| `legacy.bsp.mapping.import` | 写 | `write-trace` | 导入旧 BSP 用户、组织、角色、菜单权限映射。 |

## 五、旧表到新系统映射

| 旧字段 / 旧表 | 新落位 | 说明 |
| --- | --- | --- |
| `sys_user.id/username`、`ucenter.user.username` | `actor_projection.external_user_id` / `legacy_object_mapping` | 不迁密码和 token。 |
| `sys_user.real_name/email/phone/status` | `actor_projection.profile_snapshot` | 联系方式按敏感信息策略处理。 |
| `sys_role.role_code/name`、`authority.name` | `role_projection` / `actor_snapshot.role_codes` | 角色只是策略输入。 |
| `sys_department.dept_code/name/parent_id/region_code` | `org_projection` | 组织权威源待实现确认。 |
| `sys_region.region_code/name/parent_code` | `region_projection` | 区划投影。 |
| `sys_permission.permission_code/type/path` | Capability slug / exposure 迁移参考 | 不迁旧权限树。 |
| `sys_menu.menu_code/path/component/icon` | 不迁 | 新 WebUI 不继承菜单和组件路径。 |
| `sys_role_permission` | `tenant_capability_policy.auth_override_json` 候选 | 需人工校验后才可成为策略。 |
| `sys_user_department` | actor-org relation projection | 仅作为快照来源。 |
| `sys_dict` / `sys_dict_item` | 领域字典候选 | 必须按领域拆分，不建通用字典中心。 |
| `sys_log` | `audit_event` 历史 evidence | 新审计从 `capability_call` 生成。 |
| `sys_config` | 环境变量 / Registry setting | 禁止迁硬编码配置。 |
| `oauth_access_token` / `oauth_refresh_token` | 不迁 | token 属于运行时身份源。 |
| `dsp-manage InterfaceCall*` | `service_invocation_metric_projection` | 只读指标投影。 |
| `dsp-manage FeedbackInfo` | `objection_case` 或运营反馈 evidence | 按问题类型归属。 |

## 六、策略迁移方法

### 6.1 菜单权限到 Capability 的迁移原则

旧菜单和按钮权限不能机械迁移。迁移只能作为候选映射：

1. 识别旧菜单所属业务域。
2. 找到对应新 Capability。
3. 判断该 Capability 是否已在 Registry 中存在。
4. 将旧角色与新 Capability 的关系写入候选策略。
5. 人工审核后才可写入 `tenant_capability_policy`。

示例：

| 旧权限 | 新 Capability | 处理 |
| --- | --- | --- |
| 目录新增 / 编辑 | `catalog.entry.create` / `catalog.entry.update` | 归属目录专题。 |
| 资源申请审批 | `approval.case.decide` | 归属申请交付专题。 |
| 异议受理 | `objection.case.accept` | 归属异议专题。 |
| 数据直达刷新授权 | `adapter.national.application.reconcile` | 归属直达 adapter。 |
| 用户管理 / 重置密码 | 不迁 | 外部 IAM。 |
| 菜单配置 | 不迁 | Registry / WebUI 派生。 |

### 6.2 多消费面策略

旧 BSP 只面向 Web 菜单和接口权限，zw-brain 需要五消费面统一策略：

| 消费面 | 策略来源 |
| --- | --- |
| WebUI | `capability_exposure(surface=webui)` + tenant policy。 |
| REST | `capability_exposure(surface=api)` + auth policy。 |
| CLI | `capability_exposure(surface=cli)` + operator role。 |
| MCP | `capability_exposure(surface=mcp)` + agent/service actor。 |
| A2A | `capability_exposure(surface=a2a)` + external agent registration。 |

## 七、外化边界

| 旧能力 | 新边界 |
| --- | --- |
| 用户登录、注册、密码、验证码、短信、CA/UKey、扫码、OAuth、SAML、CAS | 外部 IAM / Auth adapter。 |
| Token 存储 | 外部身份源，禁止迁入。 |
| 菜单管理、按钮权限、路由组件 | Registry 派生 + WebUI 产品设计。 |
| 应用中心 | 外部应用目录 / Capability package 来源。 |
| 证书管理 | 外部密钥和证书管理系统。 |
| 帮助中心 | 文档 / 知识库，不进入核心模型。 |
| 消息中心 | notification adapter。 |
| 绩效、报表、指标 | P6 projection 或后续 compliance ops adapter。 |
| 系统配置 | 环境变量、settings、Registry manifest，不迁旧配置表。 |

## 八、迁移与验证策略

### 8.1 迁移步骤

1. 登记 `legacy_adapter_source`：`dsp-bsp`、`dsp-ucenter`、`dsp-manage`。
2. 导入组织、区划、角色、用户-组织-角色关系为只读投影候选。
3. 对用户、电话、邮箱、登录 IP、密码、Token 等敏感字段做排除或脱敏。
4. 从旧菜单和权限 SQL 中生成 Capability 候选映射，不直接生效。
5. 对候选策略做人工审核，写入 `tenant_capability_policy`。
6. 使用 Registry 派生 WebUI / REST / CLI / MCP / A2A 产物，验证没有手写第二份能力描述。
7. 对每次策略变更写 `capability_review_record`、`audit_event` 和 `capability_call`。

### 8.2 验证样本

最小样本必须覆盖：

1. 一个租户启用目录发现能力，但不启用外部 A2A 暴露。
2. 一个提供方角色能创建目录、处理异议，但不能修改租户策略。
3. 一个审核角色能审批申请，但不能调用高风险 adapter 重放。
4. 一个 Agent 只能通过 MCP 查询证据，不能执行写能力。
5. 一个外部应用注册为 Capability package，审核通过后只暴露 REST。
6. 旧 BSP 菜单权限导入后保持 pending，不自动生效。
7. 用户从外部 IAM 登录后，`actor_snapshot` 能写入 `capability_call`。
8. 禁用某租户 capability 后，五消费面都不再暴露该能力。

## 九、不做清单

1. 不复刻旧 `dsp-bsp`、`dsp-ucenter` 的用户 / 角色 / 权限 / 菜单后台。
2. 不迁密码、OAuth token、验证码、短信、CA、UKey、SSO 会话。
3. 不兼容旧 `/bsp/*`、`/login`、`/oauth2Login`、`/SAML2/*`、`/cas/*` URL。
4. 不把旧菜单 SQL 变成新 WebUI 导航事实源。
5. 不把 `dsp-manage` 迁成新的综合管理控制台。
6. 不建全局通用字典中心；字典必须归属具体领域。
7. 不把旧 `sys_log` 当作新审计事实源。
8. 不在代码或文档中固化客户现场身份协议和密钥配置。

## 十、专题差异决策

全局身份 / 租户权威源、greenfield 口径和统一 Capability 命名以总览方案第八节为准。本专题只保留治理底座的落地差异：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| G1 | 权威 IAM 优先级 | 外部 IAM 为权威源；优先客户政务统一身份，其次集团统一身份，项目轻量登录只作临时兜底。 | 不迁密码、OAuth token、验证码、短信、CA、UKey、SSO 会话；`actor_projection` 从外部 IAM 同步。 |
| G2 | 组织 / 区划权威源 | 区划以国家 / 客户区划主数据为基线；组织以客户组织库或旧平台团队确认后的 BSP 组织表为准。 | 旧 `sys_department` / `sys_region` 默认只作候选投影和 legacy mapping。 |
| G3 | 用户 / 角色投影同步方式 | 登录时生成 `actor_snapshot`，后台定时同步 `actor_projection`、`role_projection`、`org_projection`。 | 策略裁决以调用时 snapshot + 当前 policy version 为准。 |
| G4 | 旧 BSP 权限迁移等级 | 旧 BSP 权限只作为 `tenant_capability_policy` 候选，不自动生效。 | 旧菜单 / 按钮 / URL 权限需映射到 Capability 并经人工审核后才能启用。 |

## 十一、证据来源

- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-bsp_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-bsp_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-bsp_外部SDK和接口文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-ucenter_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-ucenter_数据库表结构文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-ucenter_外部SDK和接口文档.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-manage_对外提供API清单.md`
- `old/代码信息抽取/代码信息抽取-27newbranch/dsp-manage_数据库表结构文档.md`
- `old/12-datastructure/dsp_bsp.xml`
- `old/integrated-bigdata-platform/README.md`
- `docs/approved/zw-brain-architecture-v4-gpt55.md`
- `docs/approved/zw-brain-data-model-v4-gpt55.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-objection-handling-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md`
