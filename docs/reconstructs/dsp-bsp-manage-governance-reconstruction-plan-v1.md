# dsp-bsp / dsp-manage / dsp-ucenter 治理底座重构方案 v1

> 范围：旧平台 `old/old_codes/dsp-bsp`、`old/old_codes/dsp-manage`、`old/old_codes/dsp-ucenter`，`old/代码信息抽取/代码信息抽取-27newbranch/dsp-bsp_*`、`dsp-manage_*`、`dsp-ucenter_*`，旧结构数据 `old/12-datastructure/dsp_bsp.xml`，approved 中关于 Capability Registry、租户策略、五消费面和外部依赖的设计原则，以及 IAF IAM 已分配给 zw-brain 的统一认证接入信息。
> 结论：zw-brain 是全新项目，不迁入旧 `dsp-bsp` / `dsp-ucenter` 的自建 IAM、登录、密码、短信、CA、SSO、菜单、按钮权限、旧登录态和系统配置后台，也不把 `dsp-manage` 迁成新的综合管理控制台。但 zw-brain 必须交付自己的本地业务治理能力：租户、组织、区划、用户投影、角色映射、IAM 绑定状态、Capability policy、暴露面和审计策略都由 zw-brain Governance 管理。
> 交付目标：IAF IAM 负责“谁能登录”；zw-brain Governance 负责“登录后属于哪个租户 / 组织 / 角色、可调用哪些 Capability、如何审计和治理”；Capability Registry 负责能力包、版本、五消费面暴露和租户启停。旧 BSP 数据通过脚本 / adapter 一键导入 zw-brain 后，zw-brain 可脱离旧 BSP 独立运行、独立验收、独立交付客户。
> 单一事实源：本文是旧 BSP / manage / ucenter 治理语义导入、IAF IAM 接入、本地业务治理、身份 / 组织 / 角色投影、Capability 注册治理、租户策略和外化边界的专题单一事实源；其他 docs 触及 IAM、租户、用户、角色、组织、菜单权限或旧 BSP / ucenter / manage 去向时，应引用本文而不是重复定义边界。跨专题 greenfield 口径、统一 Capability 命名和全局决策基线以 `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` 为准。

## 一、设计原则

### 1.1 Jobs：从“基础支撑平台后台”改成“能力能否安全暴露”

旧 BSP 的表面形态是用户、角色、权限、菜单、组织、区域、应用、证书、字典、帮助、日志、登录和配置后台；旧 ucenter 是登录、OAuth、SAML、CAS、IAM、短信、扫码、CA/UKey 和门户入口；旧 manage 则混合了目录、资源申请、绩效、报表、统计、消息和配置。

zw-brain 不继承这些后台模块，但必须交付客户可用的本地业务治理层。治理层只保留六类承重价值：

1. 能识别调用者是谁、属于哪个组织和租户，以及当时的角色 / 岗位快照。
2. 能导入、同步、对账、人工修正、禁用和重新绑定租户、组织、区划、用户投影、角色映射与 IAM 绑定状态。
3. 能判断某租户是否启用某 Capability 包、某版本和某消费面。
4. 能审核 Capability 包是否允许暴露到 WebUI / REST / CLI / MCP / A2A。
5. 能为主旅程保存组织、区划、角色、权限裁决的可审计证据。
6. 能从 IAF IAM、组织源和旧 BSP 导入数据中生成本地治理投影，而不是自建完整身份认证系统。

调用者身份以 IAF IAM OIDC token 为权威输入；zw-brain 保存调用时 `actor_snapshot`、必要投影、策略裁决结果和审计证据。投影可以被本地治理台管理，但不得保存旧密码、旧 token、验证码、短信状态或旧会话，也不得取代 IAF IAM 成为认证权威源。

### 1.2 OPC：Registry 是能力治理的单一事实源

- Capability 包、版本、暴露面、审核记录、租户启停策略以 `brain_registry` 为唯一事实源。
- WebUI 动作、REST / OpenAPI、CLI、MCP、A2A 产物必须由 Registry 派生，不允许像旧 BSP 一样靠菜单 SQL 和按钮权限分散维护。
- 租户、组织、区划、用户、角色在 zw-brain 中作为本地治理投影管理；认证、密码、Token、短信、CA、SSO 由 IAF IAM 或外部认证因子承担。
- 本地治理台可管理投影同步、IAM 绑定、角色映射、租户能力启停、策略覆盖和审计查看；不得提供密码重置、认证因子配置、旧菜单维护或旧按钮权限树配置。
- 审计由 `capability_call` / `audit_event` 承载，不迁旧 `sys_log` 为新审计事实源。
- `dsp-manage` 中目录、申请、绩效、报表、消息等业务后台不纳入本专题；分别归属目录、申请交付、B1.1 projection 或外部 adapter。
- 旧 BSP 数据一键导入完成后，zw-brain 的运行时授权只查本地 Registry、投影和 policy，不再在线读取旧 BSP。

### 1.3 IAF IAM 是统一认证权威源

1. IAF IAM 已为 zw-brain 分配统一认证接入信息，zw-brain 作为业务应用 client 接入 IAF IAM。
2. 登录采用 OIDC 授权码流程；zw-brain 可提供品牌化登录入口，但用户名、密码、短信、CA/UKey、扫码和 SSO 认证过程均发生在 IAF IAM。
3. zw-brain 必须校验 `state`、`nonce`、issuer、audience / clientId、JWT 签名和 token 过期时间，不能只解码 JWT payload 后直接信任。
4. zw-brain 不实现项目轻量登录兜底，不实现密码找回、注册、验证码、短信、CA/UKey，也不存储 OAuth access token / refresh token。
5. `ACCOUNT_ADMIN` 只能作为 IAF 主用户 / 项目管理员类身份信号输入 policy，不能直接等价为 zw-brain 全局超级管理员。

### 1.4 不导入密码 / token 后如何正常使用

旧 BSP 的密码、OAuth token、refresh token、session、验证码和短信状态属于旧认证系统运行时秘密，不具备跨平台复用价值，导入它们会把 zw-brain 重新绑定到旧认证责任上。

zw-brain 的可用性来自两个闭环：

1. **IAF IAM 重新认证用户并签发新 token**：用户访问 zw-brain 后跳转到 IAF IAM 登录，IAM 回跳后由 zw-brain 校验 token 并生成本地安全上下文。
2. **旧 BSP 数据补齐业务身份和授权上下文**：一键导入脚本 / adapter 将旧 BSP 的组织、区划、用户关系、角色和旧权限映射导入为 `tenant_projection`、`org_projection`、`region_projection`、`actor_projection`、`role_projection`、`legacy_object_mapping` 和 `tenant_capability_policy`。

IAF 身份与旧 BSP 业务身份的绑定规则：

1. 已存在 IAF `sub` 映射时，以 `sub` 为权威绑定键。
2. `preferred_username` / 旧 BSP account 仅作为辅助匹配键。
3. `phone` / `email` 可作为受控辅助匹配键，必须按敏感字段策略脱敏、最小化存储和记录匹配证据。
4. 无法唯一匹配的旧用户标记为 `unmatched` / `disabled`，不得自动授权。
5. 旧 BSP 用户尚未存在于 IAF IAM 时，导入报告必须标记为 `iam_account_missing`；客户交付前需由 IAF IAM 侧完成账号开通或同步，zw-brain 不接管密码创建。

### 1.5 全新项目口径

本专题不提供旧 BSP、ucenter、manage 的 URL、菜单、按钮权限、登录态或后台页面兼容层；不设计 BSP 到 zw-brain 的运行时过渡期；不做旧 BSP 与 zw-brain 双读、双写或双登录态。

这不等于 zw-brain 没有管理面。交付态管理面应是新的 Governance 控制台：管理租户、组织、区划、用户投影、角色映射、IAM 绑定状态、Capability policy、暴露面和审计策略；它的事实源是 IAF IAM claims、组织主数据、导入投影、Registry 和审计事件，不是旧菜单、旧权限 SQL 或旧登录体系。

旧数据只支持通过脚本 / adapter 一键导入到新模型。导入成功后，zw-brain 按 Capability Registry、租户策略、本地投影和 IAF IAM 会话独立运行；旧 BSP 的菜单、按钮、权限 SQL、登录态和接口不再参与生产鉴权。

## 二、证据清单

### 2.1 approved 约束

| 约束来源 | 对本方案的约束 |
| --- | --- |
| `docs/approved/zw-brain-architecture.md` | 五消费面共享同一套 Skill / Capability 契约；新增能力默认外部生产、平台注册。 |
| `docs/approved/zw-brain-data-model.md` | `brain_registry` 派生 WebUI、REST、CLI、MCP、A2A；`tenant_capability_policy` 控制租户级启停与暴露面。 |
| `docs/approved/research-yibiaotong.md` | 基层报表减负需要按权限取数和全程留痕，但不要求复造身份平台。 |
| `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md` | `dsp-bsp` / `dsp-manage` / `dsp-ucenter` 被列为 P1；本文进一步明确它们收敛为本地业务治理层，而不是旧 IAM / 菜单 / 权限后台复刻。 |
| `old/integrated-bigdata-platform/README.md` | 旧基础支撑是自建统一用户、角色、权限、菜单、参数、日志体系，所有旧系统菜单和权限依赖它。 |

### 2.2 IAF IAM 分配信息

zw-brain 已获取 IAF IAM 统一认证 client 分配信息：

| 配置项 | 值 / 约束 |
| --- | --- |
| `realm` | `picp` |
| `auth-server-url` | `https://cnp-jn-rgzn-inlinux-test.inspur.com:9443/auth` |
| `ssl-required` | `none`；这是 IAF / Keycloak client 配置项，不代表 zw-brain 可以关闭 HTTPS、JWT 签名、issuer、audience、过期时间或 nonce 校验。 |
| `resource` / `client_id` | `zw-brain` |
| `credentials.secret` | 已分配但不在本文、代码、配置样例、导入报告或审计日志中记录；由部署 Secret / 环境变量注入。 |
| `confidential-port` | `0` |
| 当前网络状态 | 该地址为内网测试环境，当前不可访问；本文只记录分配信息和离线设计约束，不声明在线联调已通过。 |

运行时配置由环境变量注入：`ZW_BRAIN_IAF_REALM`、`ZW_BRAIN_IAF_AUTH_SERVER_URL`、`ZW_BRAIN_IAF_SSL_REQUIRED`、`ZW_BRAIN_IAF_CLIENT_ID` / `ZW_BRAIN_IAF_RESOURCE`、`ZW_BRAIN_IAF_CLIENT_SECRET_ENV`。默认 secret 读取环境变量名为 `ZW_BRAIN_IAF_CLIENT_SECRET`，配置导出、日志、报告和审计只允许出现这个变量名，不允许出现变量值；当前内网地址不可达时，用离线 discovery / JWKS fixture 验证端点推导和 token 校验边界。

### 2.3 IAF OIDC 手册约束

IAF 对接手册给出的关键约束：

1. 业务应用需先在 IAM 注册，由 IAM 团队分配 `client_id` 和 `client_secret`。
2. 认证流程为 OIDC 授权码流程：未认证请求跳转统一认证中心，认证成功后回跳业务应用 callback。
3. 授权请求必须带 `state` 和 `nonce`；业务应用需要校验回传 `state` 防 CSRF，校验 token 中 `nonce` 防重放。
4. 授权码换 token 使用 `authorization_code` grant，`redirect_uri` 必须与发起授权时一致。
5. JWT claims 中可取得 `sub`、`preferred_username`、`phone`、`email`、`project`、`project_id`、`realm_access`、`resource_access` 等用户和角色信息。
6. `realm_access.roles` 中包含 `ACCOUNT_ADMIN` 表示主用户；否则为子用户；`project` / `project_id` 表示子用户所属主用户。
7. 如果业务应用有自己的用户体系，需要将 IAM 用户与本地用户建立映射，再构建本地安全上下文。

### 2.4 旧 BSP API 证据

| 旧接口簇 | 旧平台表现 | zw-brain 解释 |
| --- | --- | --- |
| `/bsp/user/*` | 用户增删改查、密码重置、修改密码 | 账号开通、停用、密码重置外部化到 IAF IAM；zw-brain 管理 actor 投影、IAM 绑定状态和 legacy mapping。 |
| `/bsp/role/*` | 角色管理、角色权限配置 | 角色导入为 `role_projection`、角色映射和 policy condition，不复刻旧角色后台。 |
| `/bsp/permission/*` | 权限管理 | 通过预批准 mapping manifest 转成 Capability policy；Governance 可管理策略覆盖，但不迁按钮 / 接口权限树。 |
| `/bsp/menu/*` | 菜单树和菜单配置 | WebUI 动作由 Registry 派生，不迁菜单表或菜单配置后台。 |
| `/bsp/organ/*`、`/bsp/region/*` | 组织、区域树 | 导入为组织 / 区划投影，可作为 tenant / org policy 输入。 |
| `/bsp/app/*` | 应用管理和审核 | 外部应用目录 / Capability package source，默认不进核心。 |
| `/bsp/certificate/*` | 证书管理 | 外部密钥 / 证书系统，不迁。 |
| `/bsp/dict/*` | 数据字典 | 只导入必要业务字典到对应领域，不建通用字典后台。 |
| `/bsp/log/*` | 操作日志 | 可作为历史 evidence；新审计由 `audit_event` / `capability_call` 生成。 |
| `/restapi/getAuthorities` | 用户权限查询 | 不作为运行时依赖；导入后由 `tenant.policy.evaluate` 裁决。 |

### 2.5 旧 BSP 表证据

| 旧表 | 承重语义 | 新系统解释 |
| --- | --- | --- |
| `sys_user` | 用户身份、状态、联系方式、登录信息 | 导入 actor 投影和 IAF 绑定辅助信息；密码、登录 IP、头像等不进核心。 |
| `sys_role` | 角色编码和名称 | 导入 `role_projection` / policy condition。 |
| `sys_permission` | 菜单、按钮、接口权限 | 经 mapping manifest 转换为 Capability / exposure / policy；不迁权限树。 |
| `sys_menu` | 路由、组件、图标、排序 | 不迁；WebUI 由产品设计和 Registry 派生。 |
| `sys_department` | 部门、层级、区划、联系方式 | 导入 `org_projection` / actor snapshot。 |
| `sys_region` | 区划树 | 导入 `region_projection`。 |
| `sys_user_role`、`sys_role_permission`、`sys_user_department` | 用户-角色-部门关系 | 导入 actor-org-role 关系和 policy manifest 输入，不直接成为授权事实源。 |
| `sys_dict`、`sys_dict_item` | 数据字典 | 按领域导入，禁止全局字典平台化。 |
| `sys_log` | 操作、登录、异常日志 | 可作为历史 evidence；新审计从 `capability_call` 生成。 |
| `sys_config` | 系统 / 业务配置 | 环境变量和 Registry 配置，不迁旧配置中心。 |
| `sys_file` | 文件路径和存储类型 | 对象存储引用，不迁内部路径。 |

### 2.6 旧 ucenter 证据

`dsp-ucenter` 覆盖登录、验证码、OAuth2、SAML2、IAM SSO、CAS、密码重置、扫码、OTP、CA/UKey、短信、第三方地方化登录、Token 和导航菜单。数据库仅包含 `user`、`authority`、`user_authority`、`oauth_access_token`、`oauth_refresh_token`。

新系统处理：

| 旧能力 | 新边界 |
| --- | --- |
| 登录、登出、注册、密码、验证码 | IAF IAM，不迁。 |
| OAuth / SAML / CAS / IAM SSO | IAF IAM / Auth adapter，不迁旧实现。 |
| CA / UKey / 短信 / 扫码 | 外部认证因子，不进核心模型。 |
| OAuth access / refresh token | 禁止导入；运行时由 IAF IAM 管理。 |
| `authority` / `user_authority` | 导入为角色投影或 policy condition 输入。 |
| `/getNavigation`、`/queryUserSystem` | WebUI 导航由 Registry / 产品页面生成，不迁旧门户导航。 |

### 2.7 旧 manage 证据

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

旧 BSP 的菜单、权限、按钮、系统配置不能生成 Registry 事实；只有预批准 mapping manifest 覆盖到的新 Capability policy 可以在导入时写入 `tenant_capability_policy`。

### 3.2 本地治理投影

> **物理实现归属**：以下所有投影表作为 `CapabilityRegistryAggregate` + shared substrate 的物理实现，schema 通过 SQLAlchemy `Base.metadata.drop_all + create_all` 管理（基线 §9.3 / §9.6），不进入 alembic。
>
> **默认租户**：Phase 1 单租户单省，`tenant_projection.tenant_id` 取值固定为 `"sd-default"`（基线 §8.2）；`tenant_mode=multi` 不启用。

实现本地治理投影，不作为 IAM 认证权威源：

| 投影 | 用途 | 来源 |
| --- | --- | --- |
| `tenant_projection` | 租户标识、名称、状态、IAF project 绑定、租户治理状态 | 环境配置、IAF `project_id` / `project`、旧 BSP 导入。 |
| `org_projection` | 组织编码、名称、父子关系、区划、状态、组织治理状态 | 旧 BSP / manage 导入，或客户组织主数据。 |
| `region_projection` | 区划编码、名称、层级、父子关系、治理状态 | 旧 BSP region、国家 / 客户区划主数据。 |
| `actor_projection` | IAF 用户 ID、显示名、组织、角色摘要、状态、旧身份绑定、IAM 绑定状态 | IAF token claims + 旧 BSP 导入绑定。 |
| `role_projection` | 角色编码、名称、来源、适用租户、Capability policy 映射状态 | 旧 BSP role、IAF group / role claims、导入 manifest。 |

这些投影可在 Governance 控制台中被导入、同步、对账、人工修正、禁用和重新绑定，但用途限定为：

1. 构建 `actor_snapshot`。
2. 支持 `tenant.policy.evaluate`。
3. 支持 WebUI 可见性和 B1.1 审计筛选。
4. 做 legacy ID 映射和导入对账。
5. 支持客户交付态的组织、用户、角色和租户能力治理。

### 3.3 IAF OIDC 登录与本地安全上下文

IAF IAM 只解决认证，zw-brain 在认证成功后生成本地业务安全上下文。安全上下文必须可被审计和治理，但不能回写为 IAM 密码、token 或认证因子。

运行时链路：

1. 用户访问 zw-brain WebUI 或受保护 API。
2. 未登录时，zw-brain 跳转到 IAF IAM 授权端点，并生成 `state` 与 `nonce`。
3. IAF IAM 完成认证后回跳 zw-brain callback。
4. zw-brain 校验回传 `state`，用授权码换取 token。
5. zw-brain 校验 JWT 签名、issuer、audience / clientId、`exp`、`nonce` 和必要 claims。
6. zw-brain 以 IAF `sub` 为认证主键，查找或生成 `actor_projection`。
7. zw-brain 按导入的 IAF 绑定、组织、角色和租户策略构建 `actor_snapshot`、`org_snapshot`、`role_codes`。
8. 所有能力调用进入 `tenant.policy.evaluate`，裁决结果写入 `capability_call` / `audit_event`。
9. 登出时清理 zw-brain 本地会话，并跳转 IAF IAM logout 端点；zw-brain 不直接管理密码或认证因子。

### 3.4 IAF token claim 到 zw-brain 投影映射

| IAF claim | zw-brain 落位 | 规则 |
| --- | --- | --- |
| `sub` | `actor_projection.external_actor_id` / `actor_snapshot.subject` | 权威用户唯一标识，优先作为稳定绑定键。 |
| `preferred_username` | `actor_projection.profile_snapshot.username` / `legacy_object_mapping` 辅助键 | 可用于旧 BSP account 匹配，不得替代 `sub` 成为认证主键。 |
| `phone` | `actor_projection.profile_snapshot.phone_mask` 或受控匹配证据 | 敏感字段，按脱敏和最小化存储。 |
| `email` | `actor_projection.profile_snapshot.email_mask` 或受控匹配证据 | 敏感字段，按脱敏和最小化存储。 |
| `project_id` | `tenant_projection.external_project_id` / tenant 绑定键 | 用于识别 IAM 主账号 / 项目上下文。 |
| `project` | `tenant_projection.name` 或 project display name | 仅作显示、快照或辅助绑定。 |
| `realm_access.roles` 中 `ACCOUNT_ADMIN` | `actor_snapshot.account_flags` / policy condition | 表示主用户身份，不自动授予全部 Capability。 |
| `resource_access[zw-brain].roles` | `actor_snapshot.iam_role_codes` / policy condition | 作为策略输入，与导入角色共同裁决。 |

如果旧 BSP 用户无法匹配 IAF `sub` 或稳定辅助键，导入不得自动启用该用户。旧 BSP 用户 ID 只能进入 `legacy_object_mapping`，不能作为新认证主键。

### 3.5 策略裁决输入

`tenant.policy.evaluate` 的最小输入：

| 输入 | 说明 |
| --- | --- |
| `tenant_id` | 租户（Phase 1 固定为 `sd-default`，基线 §8.2）。 |
| `actor_snapshot` | 用户 / service / agent 快照。 |
| `org_snapshot` | 组织和区划快照。 |
| `role_codes` | IAF roles / groups 与导入角色映射后的角色集合，**限定为基线 §5.1 7 角色码集合**（`ROLE_SYSTEM` / `ROLE_BUSIAUDIT` / `ROLE_ORGAN_MANAGER` / `ROLE_ORGAN_OPERATER` / `ROLE_SECURITY_ADMIN` / `ROLE_SECURITY_AUDIT`），r1-r8 字面值禁止写入（基线 §11 R10）。 |
| `tags` | 可选标签位 JSON；当前仅承载 `tag_lead_dept: bool`（牵头部门标签依附 `ROLE_ORGAN_MANAGER`，仅 2 项菜单覆盖，详见 `docs/approved/zw-brain-roles.md`）。 |
| `capability_slug` | 能力标识；前端 UI 不暴露此 slug（基线 §11 R12 工程术语黑名单），UI 文案改用业务语义。 |
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

> 以下 Capability slug 仅出现在契约 / 代码 / Registry 层；前端 UI 必须按基线 §11 R12 改用业务语义命名（如 `capability.package.register` → "能力包注册"；`tenant.capability.enable` → "启用能力"），禁止把 `package` / `projection` / `capability` / `policy_decision` 等工程术语暴露给最终用户。

| Capability | 写 / 读 | 审计级别 | 说明 |
| --- | --- | --- | --- |
| `capability.package.register` | 写 | `approval-trace` | 注册能力包草稿。 |
| `capability.version.submit` | 写 | `approval-trace` | 提交能力版本审核。 |
| `capability.version.review` | 写 | `approval-trace` | 审核、驳回、禁用、回滚能力版本。 |
| `capability.exposure.configure` | 写 | `approval-trace` | 配置版本暴露到哪些消费面。 |
| `tenant.capability.enable` | 写 | `approval-trace` | 启用租户能力包。 |
| `tenant.capability.disable` | 写 | `approval-trace` | 禁用租户能力包。 |
| `tenant.policy.evaluate` | 读 | `read-trace` | 判断调用者是否可调用某能力。 |
| `tenant.governance.view` | 读 | `read-trace` | 查看租户、组织、角色、IAM 绑定、能力策略和导入对账状态。 |
| `tenant.governance.update` | 写 | `approval-trace` | 调整本地治理状态、角色映射、绑定修正、禁用 / 重新启用和策略覆盖。 |
| `org.projection.sync` | 写 | `write-trace` | 从组织主数据或一键导入结果同步本地组织投影。 |
| `actor.projection.sync` | 写 | `write-trace` | 从 IAF claims / IAM 同步和旧 BSP 导入结果同步用户 / 角色投影。 |
| `role.mapping.configure` | 写 | `approval-trace` | 配置 IAF role / group、旧 BSP role 与 zw-brain Capability policy 的映射。 |
| `iam.binding.reconcile` | 写 | `write-trace` | 对账 IAF 身份与本地 actor 投影绑定，标记 missing / unmatched / disabled。 |
| `registry.artifact.export` | 读 | `read-trace` | 导出 WebUI / OpenAPI / CLI / MCP / A2A 产物。 |
| `legacy.bsp.mapping.import` | 写 | `write-trace` | 一键导入旧 BSP 用户、组织、角色、IAM 绑定和预批准 Capability policy manifest。 |

登录本身不是 zw-brain 业务 Capability；它属于 IAF IAM 外部认证能力。zw-brain 只在 token 校验后把身份声明解析为本地安全上下文，并通过 Governance Capability 管理登录后的业务授权与审计。

## 五、旧表到新系统映射

| 旧字段 / 旧表 | 新落位 | 说明 |
| --- | --- | --- |
| `sys_user.id/username`、`ucenter.user.username` | `legacy_object_mapping` / `actor_projection.profile_snapshot` 辅助字段 | 新认证主键优先来自 IAF `sub`；不迁密码和 token。 |
| `sys_user.real_name/email/phone/status` | `actor_projection.profile_snapshot` / IAF 绑定证据 | IAF claims 优先；旧字段只作导入补充或待核验字段，联系方式按敏感信息策略处理。 |
| `sys_role.role_code/name`、`authority.name` | `role_projection` / `actor_snapshot.role_codes` | 角色只是策略输入，最终授权由 `tenant_capability_policy` 决定。 |
| `sys_department.dept_code/name/parent_id/region_code` | `org_projection` | 导入后作为本地组织投影，不依赖旧 BSP 在线服务。 |
| `sys_region.region_code/name/parent_code` | `region_projection` | 区划投影。 |
| `sys_permission.permission_code/type/path` | Capability mapping manifest 输入 | 不迁旧权限树；仅 manifest 覆盖项可转换为新 policy。 |
| `sys_menu.menu_code/path/component/icon` | 不迁 | 新 WebUI 不继承菜单和组件路径。 |
| `sys_role_permission` | `tenant_capability_policy.auth_override_json` | 按预批准 mapping manifest 一键转换；未覆盖项不生效并进入报告。 |
| `sys_user_department` | actor-org relation projection | 作为导入后的组织关系来源。 |
| `sys_dict` / `sys_dict_item` | 领域字典输入 | 必须按领域拆分，不建通用字典中心。 |
| `sys_log` | `audit_event` 历史 evidence | 新审计从 `capability_call` 生成。 |
| `sys_config` | 环境变量 / Registry setting | 禁止迁硬编码配置和旧配置中心。 |
| `oauth_access_token` / `oauth_refresh_token` | 不迁 | token 属于运行时身份源，由 IAF IAM 管理。 |
| `dsp-manage InterfaceCall*` | `service_invocation_metric_projection` | 只读指标投影。 |
| `dsp-manage FeedbackInfo` | `objection_case` 或运营反馈 evidence | 按问题类型归属。 |

## 六、策略与导入方法

### 6.1 菜单权限到 Capability 的转换原则

旧菜单和按钮权限不能机械迁移为运行时授权。转换必须通过预批准 Capability mapping manifest：

1. 识别旧菜单 / 按钮 / URL 权限所属业务域。
2. 找到对应新 Capability。
3. 判断该 Capability 是否已在 Registry 中存在。
4. 在 manifest 中声明旧角色、旧权限、新 Capability、消费面、风险等级和默认启停策略。
5. 一键导入时按 manifest 生成 `tenant_capability_policy`。
6. manifest 未覆盖的旧权限不生效，进入未映射报告，不得静默放大授权。

示例：

| 旧权限 | 新 Capability | 处理 |
| --- | --- | --- |
| 目录新增 / 编辑 | `catalog.entry.create` / `catalog.entry.update` | 归属目录专题，按 manifest 写入 policy。 |
| 资源申请审批 | `approval.case.decide` | 归属申请交付专题，按 manifest 写入 policy。 |
| 异议受理 | `objection.case.accept` | 归属异议专题，按 manifest 写入 policy。 |
| 数据直达刷新授权 | `adapter.national.application.reconcile` | 归属直达 adapter，高风险调用需保留确认与审计。 |
| 用户管理 / 重置密码 | 不迁 | IAF IAM。 |
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

### 6.3 旧 BSP 数据一键导入原则

导入性质：冷启动一次性 / 可重复执行的数据导入，不是运行时过渡期。导入完成并验收通过后，zw-brain 不再依赖旧 BSP 在线服务。

导入对象：

1. tenant / IAF project 映射。
2. `org_projection`、`region_projection`。
3. `actor_projection`、`role_projection`。
4. actor-org-role 关系。
5. IAF identity binding。
6. `legacy_object_mapping`。
7. 按预批准 manifest 转换出的 `tenant_capability_policy`。
8. 历史日志、接口统计、反馈记录等 evidence / projection。

不导入对象：

1. 密码、密码盐、密码策略。
2. OAuth access token / refresh token。
3. 验证码、短信状态、CA/UKey 会话、扫码状态。
4. 旧登录态、旧 session、旧 cookie。
5. 旧菜单页面、旧 URL、旧前端路由组件。
6. 旧按钮权限树、旧权限 SQL 运行时逻辑。
7. 旧系统配置中心、旧证书和密钥配置。

导入规则：

1. 幂等：同一份输入重复 apply 不产生重复组织、用户、角色或策略。
2. 可对账：输出源表数量、新表数量、跳过数量、失败数量和差异原因。
3. fail-closed：用户未匹配 IAF 身份、权限未命中 manifest、组织关系不完整时不得自动授权。
4. 敏感字段剔除：密码、token、密钥、证书、未脱敏手机号和邮箱不得进入导入报告、审计和日志。
5. 独立交付：apply 成功 + IAF 账号绑定完成后，zw-brain 的 WebUI / REST / CLI / MCP / A2A 权限全部由本地 Registry / policy 裁决。

## 七、外化边界

| 旧能力 | 新边界 |
| --- | --- |
| 用户登录、注册、密码、验证码、短信、CA/UKey、扫码、OAuth、SAML、CAS | IAF IAM / Auth adapter。 |
| Token 存储 | IAF IAM 和 zw-brain 本地会话边界；旧 token 禁止导入。 |
| 菜单管理、按钮权限、路由组件 | Registry 派生 + WebUI 产品设计。 |
| 应用中心 | 外部应用目录 / Capability package 来源。 |
| 证书管理 | 外部密钥和证书管理系统。 |
| 帮助中心 | 文档 / 知识库，不进入核心模型。 |
| 消息中心 | notification adapter。 |
| 绩效、报表、指标 | B1.1 projection 或后续 compliance ops adapter。 |
| 系统配置 | 环境变量、settings、Registry manifest，不迁旧配置表。 |

client secret 不进入代码仓库、文档正文、配置样例、导入报告、运行日志或审计事件；仅通过部署 Secret / 环境变量注入。

## 八、导入与验证策略

### 8.1 旧 BSP 数据冷启动导入步骤

1. 配置 IAF IAM client 信息；`credentials.secret` 由部署 Secret / 环境变量注入。
2. 准备旧 BSP 数据源、旧对象映射规则、IAF 绑定规则和 Capability mapping manifest。
3. 执行 dry-run：不写入数据库，只输出数量对账、字段映射、敏感字段排除、IAM 未绑定用户、未映射权限和阻断项报告。
4. 修复 dry-run 阻断项：补齐 IAF 账号、修正唯一匹配关系、完善 manifest 或明确 disabled 策略。
5. 执行 apply：一次性写入 `tenant_projection`、`org_projection`、`region_projection`、`actor_projection`、`role_projection`、actor-org-role、`legacy_object_mapping` 和 `tenant_capability_policy`。
6. 重跑 apply 验证幂等。
7. 使用 mock IAF token 验证 actor binding、`actor_snapshot` 和 `tenant.policy.evaluate`。
8. 内网可访问后执行真实 IAF OIDC 联调。
9. 验证 WebUI / REST / CLI / MCP / A2A 从 Registry 派生且受同一 policy 控制。
10. 旧 BSP 停止在线依赖后，验证 zw-brain 仍可登录、授权、审计和调用能力。

### 8.2 验证样本

最小样本必须覆盖：

1. IAF token 包含 `sub`、`preferred_username`、`project_id` 后可生成正确 `actor_snapshot`。
2. 一个旧 BSP 用户已绑定 IAF `sub`，通过 IAF 登录后能进入 zw-brain。
3. 该用户的 `actor_snapshot` 包含正确 tenant / project / org / role。
4. 该用户能调用 manifest 授权的 Capability，不能调用未授权 Capability。
5. `ACCOUNT_ADMIN` 用户拥有主用户相关能力，但仍受 Capability policy 限制，不能绕过高风险审核。
6. 未绑定 IAF 身份的旧 BSP 用户不能登录或只能处于 disabled / unmatched 状态。
7. 旧 BSP 权限未命中 mapping manifest 时不生效，并出现在未映射报告中。
8. 同一份旧 BSP 数据重复导入不会产生重复组织、用户、角色或策略。
9. 禁用某租户 capability 后，WebUI / REST / CLI / MCP / A2A 全部一致不可用。
10. 审计事件中记录 actor_snapshot、policy_version、decision_reason，但不记录 client secret、旧 token 或密码。

### 8.3 一键导入验收标准

1. 旧 BSP 输入数据完整读取，源表与目标投影数量可对账。
2. 每个用户要么绑定到 IAF 身份，要么被明确标记为 `disabled` / `unmatched` / `iam_account_missing`。
3. 每个组织、区划、角色关系通过主外键完整性校验。
4. 每个旧权限要么命中 Capability mapping manifest，要么出现在未映射报告中。
5. 旧 BSP 密码、token、验证码、登录态、旧菜单、旧 URL 未进入 zw-brain 运行时模型。
6. 导入后用户可通过 IAF 登录，并按导入后的组织、角色和策略正常使用 zw-brain。
7. 旧 BSP 服务下线或不可访问时，不影响 zw-brain 的登录回调后授权、审计和能力调用。
8. 导入报告、日志和审计不泄露密钥、密码、token、证书或未脱敏敏感字段。

### 8.4 内网不可访问时的验证边界

当前 IAF IAM 内网测试地址不可访问，离线阶段只能验证：

1. 配置项完整性和 Secret 注入边界。
2. OIDC discovery URL / 授权 / token / logout 端点推导规则。
3. `state` / `nonce` 校验设计。
4. token claim 到 `actor_snapshot` 的映射规则。
5. mock token / fixture 下的身份绑定和策略裁决。
6. 旧 BSP 数据导入 dry-run / apply / 幂等验证。

在线联调阶段再验证：

1. 授权码登录与回调。
2. token 换取与刷新。
3. JWKS 签名校验。
4. issuer / audience 校验。
5. 真实 claims 解析。
6. IAF logout 与 zw-brain 本地会话清理。

本文不声明 IAF 在线联调已通过。

### 8.5 一键导入报告样例（脱敏）

```json
{
  "skill_id": "legacy.bsp.mapping.import",
  "result": {
    "mode": "dry-run",
    "tenant_id": "default",
    "summary": {
      "source_count": 3,
      "projection_count": 1,
      "mapping_count": 1,
      "skip_count": 1,
      "failure_count": 1,
      "blockers": {
        "iam_account_missing": 1,
        "unmatched": 0,
        "unmapped_permission": 1
      }
    },
    "items": [
      {
        "legacy_permission_ref": "dsp-bsp:sharezone:publish",
        "legacy_role_ref": "ROLE_TOPIC_ADMIN",
        "capability_id": "topic.package.publish",
        "surface": "webui",
        "source_ref": "dsp-bsp:permission:sharezone:publish",
        "result": "planned",
        "reason": null
      },
      {
        "legacy_permission_ref": "dsp-bsp:unknown",
        "legacy_role_ref": "ROLE_UNKNOWN",
        "capability_id": "unknown.capability",
        "surface": "webui",
        "source_ref": "legacy:bsp:dsp-bsp:unknown",
        "result": "skipped",
        "reason": "unmapped_permission"
      },
      {
        "legacy_permission_ref": "dsp-bsp:iam-missing",
        "legacy_role_ref": "ROLE_X",
        "capability_id": "topic.package.publish",
        "surface": "webui",
        "source_ref": "legacy:bsp:dsp-bsp:iam-missing",
        "result": "skipped",
        "reason": "iam_account_missing"
      }
    ]
  }
}
```

报告约束：样例与真实导入日志都必须经过 `safe_json`，禁止输出 `secret` / `password` / `token` / `client_secret` 等敏感字段。

## 九、不做清单

1. 不复刻旧 `dsp-bsp`、`dsp-ucenter` 的 IAM、登录、密码、token、认证因子、菜单、按钮权限和旧后台。
2. 不迁密码、OAuth token、验证码、短信、CA、UKey、SSO 会话。
3. 不兼容旧 `/bsp/*`、`/login`、`/oauth2Login`、`/SAML2/*`、`/cas/*` URL。
4. 不做旧 BSP 到 zw-brain 的运行时过渡期。
5. 不做旧 BSP 和 zw-brain 双读 / 双写 / 双登录态。
6. 不提供项目轻量登录兜底。
7. 不把旧菜单 SQL 变成新 WebUI 导航事实源。
8. 不把旧按钮、旧 URL、旧权限 SQL 作为新运行时授权事实源。
9. 不把 `dsp-manage` 迁成新的综合管理控制台。
10. 不建全局通用字典中心；字典必须归属具体领域。
11. 不把旧 `sys_log` 当作新审计事实源。
12. 不在代码、文档、配置样例、导入报告、日志或审计中写 client secret 明文。
13. 不把 `ACCOUNT_ADMIN` 直接映射为 zw-brain 全局超级管理员。
14. 不把 `ssl-required=none` 解读为关闭 HTTPS、JWT 签名、issuer、audience、过期时间或 nonce 校验。
15. 不因当前内网不可访问而跳过 OIDC 安全校验设计。

## 十、专题差异决策

全局 greenfield 口径和统一 Capability 命名以总览方案第八节为准。本专题只保留治理底座、IAF IAM 接入和旧 BSP 数据导入的落地差异：

| 编号 | 决策项 | 专题基线 | 实施约束 |
| --- | --- | --- | --- |
| G1 | 统一认证权威源 | IAF IAM 是当前 zw-brain 已分配的统一认证源。 | 使用 OIDC 授权码流程；必须校验 `state`、`nonce`、issuer、audience / clientId、JWT 签名和 `exp`；不迁密码、OAuth token、验证码、短信、CA、UKey、SSO 会话；不提供项目轻量登录兜底。 |
| G2 | 组织 / 区划权威源 | 区划以国家 / 客户区划主数据为基线；组织可由旧 BSP 数据一键导入后形成本地治理投影。 | 旧 `sys_department` / `sys_region` 导入后只作为 `org_projection` / `region_projection` 和 legacy mapping，可在 Governance 中对账和修正，但不依赖旧 BSP 在线服务。 |
| G3 | 用户 / 角色投影同步方式 | 登录时根据 IAF token 生成 `actor_snapshot`；一键导入生成 `actor_projection`、`role_projection`、IAM 绑定、组织关系和角色映射。 | 策略裁决以调用时 snapshot + 当前 policy version 为准；旧 BSP 用户 ID 不能作为新认证主键，Governance 只管理登录后的业务授权关系。 |
| G4 | 旧 BSP 权限转换等级 | 旧 BSP 权限只可按预批准 Capability mapping manifest 转换为 `tenant_capability_policy`。 | 旧菜单 / 按钮 / URL 权限不得自动生效；manifest 未覆盖项 fail-closed 并进入未映射报告。 |
| G5 | 旧 BSP 数据导入方式 | 仅支持脚本 / adapter 冷启动一键导入，不设计运行时过渡期。 | 不提供旧 URL、旧菜单、旧登录态兼容；导入必须幂等、可对账、敏感字段剔除、失败阻断。 |
| G6 | IAF claim 到本地安全上下文 | `sub` 是用户权威标识；`project_id` / `project` 绑定租户 / 项目上下文；`ACCOUNT_ADMIN` 是主用户标识。 | `ACCOUNT_ADMIN` 只作为 policy condition，不直接绕过 Capability policy；`preferred_username`、`phone`、`email` 仅作辅助匹配或展示。 |
| G7 | 独立交付目标 | 旧 BSP 数据一键导入并完成 IAF 账号绑定后，zw-brain 可脱离旧 BSP 独立运行、验收和交付客户。 | 运行时只依赖 IAF IAM、zw-brain Governance、Registry / policy / 投影和审计；旧 BSP 在线服务不可作为生产依赖。 |

## 十一、证据来源

- `old/人工智能能力中心iam统一对接方案/IAF-统一认证对接指导手册-from黄启庆.doc`
- `old/人工智能能力中心iam统一对接方案/IAF环境下IAM系统认证鉴权方案详细设计.md`
- `old/人工智能能力中心iam统一对接方案/IAF平台与BSP平台中IAF对接的异同_v2.md`
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
- `docs/approved/zw-brain-architecture.md`
- `docs/approved/zw-brain-data-model.md`
- `docs/reconstructs/legacy-repository-reconstruction-priorities-v1.md`
- `docs/reconstructs/dsp-catalog3-metadata3-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-exchange-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-objection-handling-reconstruction-plan-v1.md`
- `docs/reconstructs/dsp-data-connect-cascade-reconstruction-plan-v1.md`
