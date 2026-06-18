# 身份治理（Identity Governance）深挖审计 — 乔布斯视角的缺口与目标任务

> 范围：zw-brain「身份治理」域（B12IamGovernance 页 + governance/iam 能力 + D51 身份认领 + D55 角色模型 + actor 数据）
> 方法：12-agent workflow（7 facet 实证测绘 → 4 乔布斯透镜批判 → 综合），关键 critical 项已人工复核源码
> 日期：2026-06-18 ｜ 分支：chore/identity-governance-audit（独立 worktree）

---

## 一句话结论

**身份治理是一个穿着治理外衣的「查看器」，而且查看的对象在任何可发布环境里都是空的。** 两端工程做得很扎实（登录端真连 Keycloak OIDC + RS256 验签；导入端 D51 单行认领、歧义 fail-closed、生产空态 R-007 诚实兜底都很有手艺），但**中间整段——"管身份"本身——产品不拥有**。唯一的页面只有一个动词：审核「旧权限映射候选」；而身份治理管理员真正要干的 7 件事（开通、派角色、停用、修复 710 个搁浅账号、看谁能访问什么、审计身份变更、带证据地审一条授权），产品上**一件都做不了**——6 件要落到开发者 shell 脚本，1 件（派角色）产品里根本没有。

---

## 现状：身份治理今天到底是什么

| 维度 | 实证 | 评价 |
|---|---|---|
| **入口** | 独立左导航 `iam-governance`，路由 `/integration-admin/iam-governance`，仅 `ROLE_SYSTEM`（平台运维员）可见；前端 shell nav / 后端 snapshot redaction / policy 三层口径一致（`productShellNav.ts:111-120`、`policy.py:64`） | ✅ D52.b「独立导航」已兑现；角色门一致 |
| **页面** | `B12IamGovernance.vue`（222 行），只消费 `governance.policy_candidate.list/review`；6 列表格 + 批量 驳回/批准/批准并写策略 | ⚠️ 名为「身份治理」，实为「旧权限映射审核」一张表 |
| **诚实度** | line 67「样例数据」提示只在 dev 构建出现；生产构建走 `panelFallback`→空数据 + `source='error'`，**绝不渲染 mock**；写操作 `:disabled=!canReview`（`panelFallback.ts:35-47`，R-007/D11） | ✅ 兜底是诚实的，不是假数据骗人 |
| **登录端** | 真 Keycloak OIDC + RS256 验签（`iaf_oidc.py`、`auth_session.py`） | ✅ 工程扎实 |
| **认领端** | D51 `claim_legacy_actor_by_iaf`：sub 优先 → 辅助字段命中可认领状态就地 rekey（同 PK 保 profile、同事务搬 binding+mapping）；多命中 fail-closed `ActorMatchError`→403（`governance_projection.py:154-257`） | ✅ 逻辑严谨、歧义安全 |
| **真实数据** | seed_snapshot.json 中 actor/iam/governance/policy_candidate 键 = 0；候选只由一次性 M0 BSP 导入产生（`mappers/governance.py:633`）；导入 fixture 710 个 actor 全是 `iaf-sd-*` 占位 → 被 `_normalize_iaf_sub` 剥成空 → 全部 `iam_account_missing` / binding=0 | ❌ 旗舰治理页在 CI/干净检出/M0 前**永远是空表或 dev 样例** |

---

## 乔布斯视角的缺口（按严重度）

> 原则：聚焦=对一千件事说不；简洁=用户不该看到组织架构和角色码；端到端=不留断缝；"就是能用"+诚实=不许假数据、死按钮、骗人的信号。

### 🔴 Critical（对真实用户而言产品是坏的/不诚实的）

**C1. 产品内没有任何"派角色/授权"动作，而 `App.vue:248` 的文案在撒谎指路。**
角色是**单向流入**：只来自 IAM token claims（`auth_context.py:36-48`）或一次性 legacy 导入（`governance_projection.py:304-307`）。`grep role.assign/grant_role/assign_role/revoke_role` 在 dispatch/能力注册表 = **0 命中**（已复核）。可一个刚登录、零角色的政务员工会撞上「暂无可用岗位权限」门，文案告诉他：「请联系系统管理员**在身份治理中**为您的账号添加用户角色权限」（`App.vue:246-248`，已复核）——而身份治理页**没有任何派角色按钮，整个产品里也没有这个能力**。用户和管理员一起掉进产品指给他们、却又不拥有的坑。
*用户影响：身份治理最基本的动作在产品内无法完成；错误文案承诺了一条不存在的补救路径。*

**C2. 停用不在认证边界生效；产品里压根没有"停用"动作。**
`_CLAIMABLE_STATUSES = {iam_account_missing, unmatched}` 刻意排除 `disabled`（`governance_projection.py:33`，注释 31-32 行明说"被停用的旧用户绝不能把它的角色绑定借给新 IAM 身份"——**这部分是好手艺**）。但当一个 `disabled` 旧行被 IAM 登录命中时，代码走第 3 分支 `_insert_fresh_iaf_actor` **新插一行 `status="active"`**（`:244-257`、`:335`，已复核），**登录从不被拒绝**。
> ⚠️ 精确机制（我对 workflow 结论的修正）：被停用行的**角色不会被继承**（这是刻意的保护，做得对）；真正的缺口是 ——(a) IAM 登录永不被拒，停用只停了那一行、没停那个人；(b) 又制造了一条全新 active 重复行（对 disabled 用户重演 D51 重复问题）；(c) 新行角色取 IAM token 自带的 `token_role_codes`，**若 token 携带角色码，则等效"带角色复活"**。而且产品内根本没有 `actor.disable` 能力（`grep`=0），停用只能靠重跑 legacy 导入。
*用户影响：在政务平台上，"我停掉了离职/调岗人员，SSO 却照样放他进来并新建一条活账号"是安全事件，不是打磨问题。*

**C3. 710 个导入 actor 全部搁浅（`iam_account_missing`/binding=0），管理员无任何补救面；可发布环境里也没有真实数据喂这个页。**
两条喂数路径都死了：(1) `GovernanceMapper._normalize_iaf_sub` 把 `iaf-sd-*` 占位剥成空 → 710 个 actor 全落 `iam_account_missing`、0 binding（`mappers/governance.py:24-32`）；(2) seed 无 actor/candidate 键，唯一灌数路径 `customer_acceptance_up.sh` 依赖 gitignore 掉的客户 dump。补救逻辑只活在 shell 脚本（`ingest_iam_sub_backfill.py`、`repair_actor_identity_duplicates.py`），从未接到页面。
*用户影响：真实部署第一天，运维员打开身份治理（如果它真展示 actor 的话——它不展示）看到 710 个坏身份、屏幕上零动作；修平台的头号阻塞要靠工程师上终端。*

**C4. `governance.iam_overview` 后端完整、5 个消费面全注册，却被 0 行 web 代码消费——一个建好的后端没有前门。**
`iam_overview` 聚合真实 actors/orgs/roles/tenant_policies/import_issues/audit_events（`j2/governance.py:29-103`），已注册（`pages.generated.ts:97`），但 `grep iam_overview` 在 `zw-brain-web/src` 只有那一行生成清单——**没有任何 composable/lib/page 调它**（已复核）。真正的页面只消费 policy_candidate。
*用户影响：系统里最丰富的身份数据（谁是用户、IAF 认领状态、D51 的歧义/未匹配/缺失失败态、审计时间线）算出来给谁都没看。名字叫「身份治理」的页面其实是个窄窄的映射审核器。*

### 🟠 Major（真实摩擦 / 缺核心职责）

**M1. 产品唯一真正做的身份写操作（认领/rekey）不写任何审计。** `grep audit` 在 `governance_projection.py` = **0**（已复核）。相比之下 policy_candidate.review 写操作会回 `audit_id`。最安全敏感的写（改一行 actor "是谁"、搬角色绑定）没有审计记录；安全审计员问"这个账号何时、凭什么被链到这个人"——无答案。

**M2. 唯一能干的活（审一条授权）是闭眼审的。** 后端 list 支持 `legacy_system/legacy_role_ref/capability_id/surface` 四个过滤器并序列化 `evidence_json`（每条映射的"为什么"，`serializers/governance.py:80`），页面却只给一个状态 `<select>`，无证据列、无行下钻、丢了 legacy_system 列、无搜索、无分页（`B12IamGovernance.vue:110-119`）。批准会写 `tenant_capability_policy`（`governance.py:344`）——闭眼批准一次租户策略写入是治理风险。

**M3. `dispute_view` 对平台真实产生的运行时异议数据 404。** `_get_dispute` 先调 seed-only 的 `get_dispute_by_id`（disputes=0）并在 DB 查询之前就抛 `NotFoundError`，导致下一行的 `repos.objection.get_case` 永远到不了（`governance_dispute.py:68-71`）。而 `dispute_list` 会合并运行时 objection_case 行——列表说"在这"，详情说"不存在"，两次点击到自相矛盾。

**M4. `dispute_list` 的 alerts/tickets/knowledgeArticles 是永久空桩。** 三个 required 段来自 seed 中为 0 的键、无运行时仓库、`web_snapshot_redaction.py:121-123` 还强制置空。四个声明段里三个永远空，审计员分不清"没发生"还是"从没работал"。

**M5.（邻接）部门管理员"本机构+下级"可见性（已签 D61②）静默退化为只见本机构。** 解析器与子树递归已建，但 `org_projection.parent_org_code` 100% 为空（`pub_organ_tree.PARENT_CODE` 从未导入），`list_org_children` 返回 0 行。一个签了字的决策在静默欠交付。

**M6.（邻接）dev-iam-bypass 给无认证请求发全角色身份，仅靠 env 开关；生产护栏只认字面 `deploy_mode='prod'`。** `server.py:824-834` Path 2 在 bypass env 为真时给任意无 cookie 请求全角色身份；生产拒绝只在 `ZW_BRAIN_DEPLOY_MODE` 字面为 `prod/production` 时触发（`runtime_config.py:54,82`），`check_iam_prod_guard.py` 延后。staging/demo 默认空 deploy_mode + bypass env = 完全无认证敞开，安全全押在一个 env 上、只有人工清单兜底。

### 🟡 Minor（打磨 / 潜在腐烂面）

- **m1. 产品内没有"谁能访问什么"的有效权限视图。** 角色→能力矩阵只活在 `policy.py:25-469` + 开发脚本 `audit_permission_matrix.py`；治理产品的核心可审计性问题在用户面之外。
- **m2. `web_snapshot_redaction` 白名单可与 `PERMISSION_ROLES` 漂移而无 preflight 守卫。** D55 点名四份手维护副本须集合相等，但只守了 policy↔manifest 子集（段26）；redaction 比 policy 多放一个角色 = 静默过度暴露，无门拦截。
- **m3. `ROLE_SECURITY_ADMIN` + 整个数据安全中心能力模块在 manifest 里发货，却无任何角色可达**（`policy.py:290-307` 这些 cap 无角色授权 → 全员 fail-closed）。无立项排期的死重量。
- **m4. `external.share.governance.configure` 是注册的治理契约但无 executor**（`grep` 命令层=0）。MCP/A2A 消费者发现却无法本地调用的静默 no-op。
- **m5. 全新部署看到永久空表却无解释。** 应区分"还没导入"与"后端挂了"。

---

## The One Thing（若只能做一件）

**把 `governance.iam_overview` 接进 `B12IamGovernance.vue` 作为页面主视图**——actor 列表/搜索（带 IAF 认领状态 + binding 状态，用后端已经在服务的 `iam_account_missing/unmatched/disabled` 过滤）、导入问题队列（710 个搁浅用户）、身份变更审计时间线；把"权限映射审核"降为其中一个分页。

**为什么最高杠杆**：后端已建好且零 web 消费——这是让「身份治理」名副其实的最便宜路径；它为每一个 actor 生命周期动作（派角色/停用/认领）提供落脚处；它把一张空表变成管理员真能"看见身份人口"的面。**看不见就治理不了**——今天管理员盯着一张 6 列勾选表，而真正的身份故事一片漆黑。

---

## 该说"不"的（聚焦=砍）

1. **砍掉** `dispute_list` 的 alerts/tickets/knowledgeArticles 三段——四段里三段无数据源、永远填不满。少发几段诚实的，别发三段死的。
2. **暂缓**在 zw-brain 内自建完整 IAM/Keycloak 管理控制台。若角色发放永远由上游拥有，就别复刻——只把 `App.vue:248` 改诚实（指向真实 IAM 路径），只建那**一个**窄窄的 actor 解析/生命周期动词。
3. **别**仅凭一张映射审核表就把「身份治理」立成顶级导航模块。要么这轮用 iam_overview + 一个生命周期动作把模块挣回来，要么把"旧权限映射审核"折叠进 外部系统/导入 作迁移期步骤、把导航位让出来直到 actor 生命周期落地。
4. **移除/标注不可本地调用**无法触达的数据安全中心 manifest（`compliance.case.*`/`risk.*`）与 `external.share.governance.configure`，趁数据安全中心无立项地平线时别背死面。
5. **别**这轮追完整的有效权限矩阵引擎或多租户就绪（tenant_id 设计上硬编码 sd-default）；给审计员一个从 `policy.py` 派生的只读 角色→能力 视图就够。
6. **别**做条件表达式审批求值或任何依赖未导入 `parent_org_code` 的功能（解析器已建，只缺数据喂入那一行）。

---

## 目标任务路线图

| # | 任务 | 优先级 | 工作量 | 闭合缺口 | GATE? |
|---|---|---|---|---|---|
| T1 | **把 iam_overview 接为身份治理主视图**：actor 列表/搜索（认领+binding 状态、复用后端 missing/unmatched/disabled 过滤）+ 导入问题队列 + 身份变更审计时间线；映射审核降为一个分页 | **P0** | M | C4, C3, m1 | 否（纯接线，后端已有） |
| T2 | **把零角色 onboarding 断缝改诚实且可操作**：开 GATE 定角色发放归属。若产品内 → 加 `governance.actor.role.assign/revoke`（ROLE_SYSTEM、审计、写 binding）+ actor 列表上的派角色动作；若上游独占 → 重写 `App.vue:248` 指向真实 IAM 路径。同一改动里把文案改对 | **P0** | M | C1 | ✅ D28（角色/状态机） |
| T3 | **在认证边界强制停用 + 给停用一个写路径**：(a) `claim_legacy_actor_by_iaf` 命中 `disabled` 行时 fail-closed（403 actor_disabled）而非新插 active，加测试断言 disabled 重登被拒；(b) 加 `governance.actor.disable/enable`（ROLE_SYSTEM、审计），挂 actor 列表 | **P0** | M | C2 | ✅ D28（状态机） |
| T4 | **认领路径补审计**：`claim_legacy_actor_by_iaf` 对每次 rekey/insert/重复停用结果发 audit_event（method、old→new external、搬了哪些 binding、匹配证据，无 PII/密钥），复用 D4 审计总线（写失败熔断）→ 自动出现在 T1 的时间线 | **P1** | S | M1 | 否 |
| T5 | **修 dispute 列表↔详情分叉 + 砍死段**：(a) `_get_dispute` 改为抛 NotFoundError 前先回落 `repos.objection.get_case`，加"提异议→开详情"e2e；(b) 从 dispute_list output_schema + UI 移除 alerts/tickets/knowledge | **P1** | S | M3, M4 | 否 |
| T6 | **给搁浅 actor 提供 backfill/认领面**：把 `ingest_iam_sub_backfill` 逻辑包成 `governance.actor.backfill_sub`，作 actor 列表上的"关联 IAM 账号"批量/逐行动作（审计、歧义 fail-closed）——让 shell 脚本成为引擎而非唯一接口 | **P1** | M | C3 | 可能（数据写） |
| T7 | **让审核这件活有手艺**：加 `evidence_json` 逐条下钻、恢复 legacy_system 列、把四个已有后端过滤 + 文本搜索 + 分页接进页面 | **P1** | S | M2 | 否 |
| T8 | **发一份诚实标注的 sd-default seed**（几行 `legacy_policy_candidate`+`actor_projection`，`source='seed-demo'`）让页面+e2e 走真实 DB→handler→page 路径；把 B12 加进 `twin_browser_pages` PAGE_MATRIX（ROLE_SYSTEM）；加诚实空态区分"未导入"vs"后端挂"；按 source 拆分 line-67 toast | **P1** | M | C3, m5 | 否（D46：无 SPEC+无真数据渲染 ≠ Done） |
| T9 | **导入 `pub_organ_tree.PARENT_CODE`** 进 `org_projection.parent_org_code`（解析器+子树递归已建）；未导入前在 overview 显式提示组织树未填充，让下级可见性可见地失效而非静默 no-op | P2 | S | M5 | 否（兑现已签 D61②） |
| T10 | **机械硬化 dev-bypass 生产护栏**：实现 `check_iam_prod_guard.py`（preflight 拒绝带 bypass-on 发货）+ 运行时护栏在 deploy_mode 未设/空时 fail-closed（不只字面 prod） | P2 | S | M6 | 否（全局§5 升级原则） |
| T11 | **硬化四副本矩阵不变量**：扩 preflight 子集守卫（或把 `audit_permission_matrix.py` 接进 preflight）断言 redaction 成员与 PERMISSION_ROLES 对齐，不只 ⊆ ALL_ROLE_CODES | P2 | S | m2 | 否 |
| T12 | **修剪死治理面**：移除/标注不可本地调用 数据安全中心 manifest（`compliance.case.*`/`risk.*`）与 `external.share.governance.configure`，债账记录延后 | P2 | S | m3, m4 | 否 |

**节奏建议**：T1（主视图）是地基，T2/T3/T4/T6/T7 都挂在它给出的 actor 列表上。T2、T3 是状态机/角色变更，须先过 D28 业务 sign-off 再实现。T1 本身纯接线、无 GATE，可立即起步并作为后续的承载面。

---

## 复核留痕（哪些 critical 我亲自验过源码）

| 断言 | 复核结果 |
|---|---|
| 认领路径 0 审计 | ✅ `grep -ci audit governance_projection.py` = 0 |
| App.vue 指"在身份治理中加角色"但无该能力 | ✅ `App.vue:248` 原文 + `grep role.assign/grant_role`=0 |
| disabled 重登新插 active 行、登录不拒 | ✅ `governance_projection.py:225/244-257/335`；**修正**：角色不继承（刻意保护），缺口在"不拒登录+新建重复行+token 角色可复活+无 disable 动作" |
| iam_overview 零 web 消费 | ✅ `grep iam_overview zw-brain-web/src` 仅 `pages.generated.ts:97`（生成清单） |
| 身份治理页=单一功能、兜底诚实 | ✅ 首读全文 `B12IamGovernance.vue`，R-007/DataSourceBadge/canReview 门 |

> 测量纪律提醒（承 memory）：710 / binding=0 等聚合数字来自 facet agent 对 `iaf-binding-manifest.json`/seed 的实证，与既有 sd-default 缺口审计一致；若要据此立项，建议在**干净全量真实库**上再核一次基数，避免本地污染库造成的测量假象。

---

# 附：角色发放归属的乔布斯综合判断（架构决策）

> 命题（产品研发负责人提出）：IAM(IAF) 是**通用、多产品共享**的身份提供商，因此 zw-brain 应**在产品内自建角色发放（鉴权）**，IAM **只做认证**。
> 方法：9-agent workflow（4 实证读：旧 IAM/IAF 设计文档 + 旧 BSP 角色 schema + 旧角色样本数据 + zw-brain 现状耦合 → 4 乔布斯架构透镜 → 综合裁决），关键项人工复核源码。

## 裁决：YES——zw-brain 内自建角色发放，IAM 只认证

**这不是偏离,是这个领域一贯打法的正统延续,且是中等重构、不是重写**(binding 表、repo、浏览器读路径都已存在)。

### 一句话(可签)
> **IAM 证明你是谁;zw-brain 决定你能干什么。** 让 `actor_org_role_binding` 成为**唯一可写、带审计**的角色权威源、所有消费面都读它,授权**彻底忽略 token 里的一切角色**,并**先堵停用洞**。

### 旧平台事实(实证,已复核表存在)——铁证支持自建

| 证据 | 内容 |
|---|---|
| **IAF token = 纯身份** | JWT 标准字段全为 sub/preferred_username/email/name——"**标准字段全为身份,无业务角色/权限/菜单**";`BearerTokenPayloadParser` "不做签名校验、完全信任 Keycloak",只用来识别调用者 |
| **产品角色本地解析** | `resolveRoleId()` 拿 token 的 `project` claim 去匹配**本地** `sys_role.role_key`,匹配不到回落"普通用户"——角色在产品内决定与存储 |
| **BSP 自拥完整 RBAC**（已 grep 确认表存在） | `pub_role`(角色定义,层级+APP_CODE 域)、`pub_user_role`(用户↔角色 join,APP_CODE 域)、`pub_user_organ_role`(按(用户,机构)发角色)、`pub_role_resource`→`pub_resource`(角色→菜单授权链)、`pub_user_data_auth_org/_region`(**数据范围,独立一轴**) |
| **所有权方向明确** | "**完全掌控用户数据**"是 BSP 列出的**优点**;"**IAM 是 BSP 的下游(用户输出)**";BSP 往 IAM 推角色属性只是**单向 SSO 传播**,IAM 从不拥有授权 |
| **IAM 确为通用共享** | portal_user/sys_user/user/block_user **四套用户体系**联邦进同一 IAM;`APP_CODE` 列(schema 中 31 处)正是为**隔离各产品角色互不污染**而存在——schema 自己在坦白:授权不属于共享层 |

> 含义:每个消费平台(BSP、各 IAF 子模块)都**保留自己的 sys_role/角色表**、从身份 claim 本地解析角色。**没有一个把角色发放委托给共享 IAM。** zw-brain 自建就是这条正统的直接延续。

### 为什么不放 IAM(三条,均有据)
1. **能力**:共享 token 结构上装不下 zw-brain 的模型(5 业务角色 + `tag_lead_dept` D23 + 按机构多角色边 + D52–D57/D61 持续变更的 GATE);真要塞进通用 realm,它就不再通用、变成每个产品的授权库。`APP_CODE` 的存在就是反证。
2. **先例**:本领域从无人把角色发放委托给共享 IAM。
3. **体验与生命周期所有权**:不同团队、不同发版/工单节奏的通用组件,扛不动 keynote 级产品策略,也**无法按 zw-brain 的时间线强制"停用一个离职员工"**(现状已复核:token 仍门控 bearer 面,且登录把 status 重置 active——平台在登录时主动"解除停用")。**角色就是产品的灵魂,不外包。**

### 为什么"混合"是陷阱(最坏选项=两个主人)
现状**已经是两主人(意外造成)**:浏览器 BFF 读存储的 `actor_org_role_binding`,而 bearer/MCP/CLI 读 token(`auth_context.py:178` 读 `ctx.role_codes`=token 角色)。今天只因为 binding 是 token 的下游缓存(登录 `governance_projection.py:303-307` 用 token 覆写 `role_codes_json`、`793-796` 从 token 派生 binding)才"碰巧一致"。一旦在产品内可写 binding 却不切断 token 门——**同一用户在浏览器看到、在 MCP/CLI 看不到的角色**;**产品内撤销了、stale token 仍放行 bearer 面**=静默提权 + 无法回答"这人到底能干什么"。**说不。** 只有一个主人、可写、所有面都读它。

### 唯一事实源 + 防漂移(结构性塌缩,不靠同步任务)
`actor_org_role_binding`(actor, org_code, role_code)为权威可写源:(1) 删登录处 token→`role_codes_json` 覆写(`gov_projection.py:303-307`)+ token→binding 派生(`793-796`),token 只供身份;(2) 把 bearer/MCP/CLI 边界解析器(`auth_context.py:178`)改为**读 binding** 而非 `ctx.role_codes`,两面读同一源;(3) 立硬不变量 + preflight 守卫:"**token realm/resource 角色永不用于产品鉴权**",防未来有人重新引入第二主人;(4) 每次写经唯一 assign/revoke 能力,带同步 `audit_event`(旧平台对每条角色行 HMAC 签名,因它是 store-of-record——照搬此意图)。

### 迁移路径(有序、每步可发、fail-closed)
- **STEP 0(独立、先发)堵停用洞**:在两个门(`resolve_role_from_identity` token 门 + `resolve_trusted_role` binding 门)加 fail-closed 的 active/disabled 状态检查;停掉 `_apply_claim_to_actor` 登录时自动 `status='active'`(`gov_projection.py:303`)。**这是任何方案下都成立的线上洞,先于权威之争修。**
- **STEP 1 回填**:一次性把现状(末次导入 + 当前 token 角色)灌进 `actor_org_role_binding`,避免切换时非浏览器调用者失权(登录只 rekey、从不 regrant)。
- **STEP 2 binding 变权威**:删 token→role_codes_json 覆写 + token→binding 派生。
- **STEP 3 统一门(与 2 原子同发)**:bearer/MCP/CLI 边界改读 binding,永久消除混合分叉。
- **STEP 4 加写路径**:产品内 assign/revoke 能力(今 grep=0)+ 身份治理 UI,门控 ROLE_SYSTEM(+D55/D57 校正),每次 grant/revoke/rekey 发同步 `audit_event`(D4)。功能角色入 binding;机构/区划范围保持 D61 的**独立一轴**,别折进角色授予。
- **STEP 5 不变量守卫**:preflight 断言 token 角色永不用于鉴权。
- **STEP 6 修测试盲区**:dev-IAM-bypass 默认全角色→本地/e2e 测不出角色差/停用/binding 权威;加**非 bypass、窄身份 + 停用 actor** 的 e2e 夹具,证明浏览器与 bearer 两面角色**完全一致**。
- **STEP 7 GATE**:走 D28 sign-off(新增产品内 assign 能力 + 反转 D51 wave-0"登录不 regrant binding"deferral = 角色/状态机变更)+ 签字账本。

### 对前述审计的影响
- **C1(派角色)**:由"审计一个外部、不可审、不可控的权威"→"审计 zw-brain 自己的可写源"。今天 grep assign=0、认领写路径 0 审计,"谁发的这个角色"**无解**;自建后每次 grant 一等审计事件、可归因可回放。
- **C2(停用)**:今天**双重坏**——两门都不查 status + 登录重置 active;自建 STEP0+STEP3 后,停用是 zw-brain 自己控制、能按自己时间线强制的 fail-closed 检查。审计的即时结论:**STEP 0 不论权威之争如何落地都必须先发**。

### 主要风险
- 切换期双门脑裂:STEP 2/3 必须**原子同发**,否则在产品内发的角色会被下次登录冲掉、API 面仍信通用 IAM realm。
- 跳过 STEP 1 回填→切换瞬间非浏览器调用者失权。
- 不立不变量守卫→未来有人重新读 token 角色,第二主人复活。
- 停用洞是**线上、与方案无关**的最紧急项。
- 新写路径无审计/完整性=单点篡改(旧平台正因此对每条角色行 HMAC)。
- 机构范围过载:若把 org 折进角色授予而非保持 D61 独立轴,机构调动要重发角色而非移范围。
- dev-bypass 全角色→迁移"看着完成、实则带病到生产",STEP 6 夹具必做。
- D28/D51 治理:反转 D51 deferral + 新状态机能力,须负责人签字、非静默重构。

> 复核留痕:`auth_context.py:36-48`(role_codes_from_claims 只读 realm_access/resource_access)首手复核 ✓;旧 BSP 表 `pub_role/pub_user_role/pub_user_organ_role/pub_role_resource/pub_user_data_auth_org/_region` 经 grep `dsp_bsp.xml` 确认存在 ✓;旧角色边规模(66 角色 / 4,186 用户-角色 / 135 (用户,机构) / 42 机构)来自 agent 读 dump 的 value 元组,量级支撑"旧平台规模化自建"结论,立项前建议复点。
