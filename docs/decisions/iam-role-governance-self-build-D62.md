---
title: D62 — 角色分派与角色治理 zw-brain 自建（IAM 只认证）
scope: iam-role-governance
status: in_progress  # 架构 + 角色/状态机门（D28 GATE）：计划经产品研发负责人 plan-mode 批准（2026-06-18）；阶段一(A0+B+C)+阶段二(A1/A2/A3/A4+D1/D2)已落地并测试、全守卫绿；待续=D3 种子 + e2e走查 + capture重采 + D37验收 + 正式补签
date: 2026-06-18
deciders: 海若产品部产品研发负责人（GATE 决策门）
related_docs:
  - docs/audits/identity-governance-deep-dive.md（深挖审计 + 乔布斯综合裁决，本决策的论证底稿）
  - CLAUDE.md D51（iam-identity-claim，本决策 A0 对其 disabled 处理的修订）
  - CLAUDE.md D55（permission-realignment，角色↔权限边界；本决策角色门承其口径）
  - CLAUDE.md D48（data-model referential integrity，本决策 D1 FK 承其约束）
---

# D62 — 角色分派与角色治理 zw-brain 自建（IAM 只认证）

> **类型**：架构门 + 角色/状态机变更（D28 GATE）
> **触发**：身份治理深挖审计发现「产品内无法派角色/停用、授权事实源放在通用共享 IAM token」。
> **核查依据**：旧平台 BSP 数据结构与 IAM 对接设计文档（`old/12-datastructure/dsp_bsp.xml`、`old/人工智能能力中心iam统一对接方案/*`）实读 + 当前 HEAD 代码事实（`auth_context.py:36-48`、`governance_projection.py`、`session_context.py`）。
> **性质**：决策 decision_only（不抬 `.feature` 状态）；实现分两阶段落地，各带测试/验收。

---

## 一、裁决

**IAM 证明你是谁；zw-brain 决定你能干什么。** 反转「产品角色从通用共享 IAM token 派生」的现状，确立：

| 归属 | 拥有 |
|---|---|
| IAM/IAF | **认证唯一**：核验 token → 提供可信 `sub`（+身份 claim）。不 carry 任何产品角色。 |
| zw-brain | **授权唯一事实源**：`actor_org_role_binding`（actor, org_code, role_code, status）= 可写、带审计的角色权威源，所有消费面都读它。 |
| zw-brain | 产品内 分派/撤销/停用 能力 + 身份治理 UI；每次写发同步审计。 |
| zw-brain | actor 生命周期：两门 fail-closed 的 active/disabled 检查。 |

**依据**：旧平台 BSP 早已是此架构且实证——IAF token「标准字段全为身份，无业务角色/权限/菜单」；BSP 自拥 `pub_role`/`pub_user_role`(4,187 边)/`pub_user_organ_role`/`pub_role_resource`/`pub_user_data_auth_*`，「完全掌控用户数据」为其列明优点，「IAM 是 BSP 的下游」。zw-brain 自建是此正统的延续。

## 二、范围（媲美 BSP 的"运营能力面"，非"通用目录"）

**做**：用户管理 + 角色分派/撤销（按机构）+ 用户停用/启用 + 谁能访问什么（只读）+ 全程审计 + 授权事实源收口。
**不做**（乔布斯 say-no）：角色目录 CRUD/树/权重（zw-brain 固定 5 业务角色+系统，D23/D55）、APP 多产品域、菜单授权引擎全量复刻、区划直授（`pub_user_data_auth_region`，记债）、在 zw-brain 内自建 IAM 账号 CRUD。

## 三、实现状态

### ✅ 已落地并测试（阶段一）

- **A0 堵停用洞**（修订 D51 disabled 处理）：`claim_legacy_actor_by_iaf` 命中 disabled 行（既有 sub 或辅助匹配）一律 `ActorDisabledError` fail-closed——**不再复活为 active、不再新插 fresh active 行**（旧 fall-through 既绕过停用又重造 D51 重复）。`session_context.resolve_trusted_role` 对 disabled 快照拒绝（浏览器门防御）。再启用是显式管理动作（`governance.actor.status.set`），非登录副作用。
- **B 五能力**（全 `ROLE_SYSTEM` 门控、写发审计、走 `deps.write` 闭包）：
  - `governance.actor.list`（读）— 用户+有效角色+认领/停用状态，按机构/角色/状态/关键字过滤
  - `governance.actor.role.assign`（写）— 单边授（actor,org,role），写 `actor_org_role_binding`
  - `governance.actor.role.revoke`（写）— 置 binding disabled
  - `governance.actor.status.set`（写）— 停用/启用，绑定保留以便启用即恢复
  - `governance.access_matrix`（读）— 角色→能力矩阵（policy.PERMISSION_ROLES 单源派生）+ 固定角色目录
- **仓储单边写**：`assign_actor_role`/`revoke_actor_role`/`set_actor_status`/`get_actor`（`governance_projection.py`，幂等、按 (actor,org,role) 收口）。
- **C 身份治理 UI**：`B12IamGovernance.vue` 重构为 3 tab（①用户与角色：列表+搜索+筛选+分派/撤销/停用 ②谁能访问什么 ③旧权限映射审核保留）；新 `useActorGovernance.ts` composable；`App.vue:248` 文案改诚实可达。`ROLE_SYSTEM` 门、≤10 页/角色守恒（无新顶层导航）。`npm run build` 绿 + vitest 18/18。
- **契约**：5 消费面契约重生在同步（REST/CLI/MCP/A2A/agent_integration）；写能力刻意不暴露 MCP。
- **测试**：`tests/test_iam_role_governance.py` 9 测全绿（仓储写、A0 停用门、角色门 403、能力端到端带审计）；身份/治理回归簇全绿（含修订后的 `test_iam_identity_claim.py`）；preflight 段26（权限矩阵子集）绿；触及面 ~280 测全绿。

### ✅ 阶段二也已落地并测试（授权事实源收口）

- **A1 停 token→角色 流**：登录不再把 token 角色写进 `role_codes_json`（A1a）；iaf:claims 不再从 token 派生 binding（A1b）；assign/revoke 把 `role_codes_json` 镜像到 active binding（A1c）。
- **A2 bearer 门读 binding**：`server._bind_auth` 非 dev-bypass 用 `_binding_role_codes_for_subject(sub)` 从 binding 派生 `role_codes`，`resolve_role_from_identity` 与 C1/N1 测试零改动；dev-bypass 保全角色。真实通用 IAM token 本不带 ROLE_*，生产侧本就 binding 权威。
- **A3 守卫**：`check_no_token_role_authz.py` 接入 preflight **段73**，钉死 token 角色不进授权。
- **A4 回填**：`scripts/backfill_actor_bindings.py`（dry-run→apply→幂等）。
- **D1/D2**：`actor_org_role_binding→actor_projection` 登记 `check_orphan_rows` C 类边（段67，A14+B5+C10，孤儿=0）；external_actor_id 认领时 rekey + SQLite 复合 FK 时序受限 → D48 §2.5 honest-downgrade 守卫兜底，不上硬 FK。
- **测试**：4 REST bearer + 2 identity claim + 1 onboarding 文案测随收口更新；夹具 `seed_identity_bindings` 把「身份持有角色」表达为 binding。全簇 ~370 测全绿；段26/28/67/73 + contract --check 全绿。

### ⏳ 待续（验收/收尾，需起栈）

- **D3 种子**：诚实标注 seed actor+binding（旗舰页非空 + 进真库渲染路径，承 D46）。
- **E2/E3 e2e**：非-bypass 窄身份 + 停用 actor 真 UI 走查（证两面角色一致 + 停用被拒）；身份治理面入 PAGE_MATRIX；`capture --with-e2e` 重采指纹（本决策改了 feature-backed 测试，须重采后方可 commit 过段60）。
- **D37 验收 + D-index**：`.testing/acceptance/iam-role-governance/evidence.json` 真 UI 证据；CLAUDE.md 补 D62 索引（≤900 字符）；正式补签。

## 四、与既有决策的关系

- **修订 D51**：A0 把「disabled 行登录 fall-through 新插 active」改为 fail-closed。D51 原意「不认领 disabled 行（不继承角色）」不变，A0 进一步堵住其 fresh-insert 旁路（既绕停用又重造重复）。属同一 IAM 会话边界的安全修订。
- **承 D55**：角色分派/撤销/停用/查清单 = 平台运维员（`ROLE_SYSTEM`）独占，与 D55 身份治理归属一致。
- **承 D48**：D1 FK 兑现「永不留孤儿行」。
- **承 D46**：身份治理面改 feature-backed 测试 → 须 `--with-e2e` 重采指纹方可进 Done。

## 五、签字

`.testing/signoff/iam-role-governance.signoff.yaml`（decision_only）。属 D28 架构+角色/状态机门：计划经产品研发负责人 plan-mode 批准（2026-06-18）为决策起点；阶段二深度收口与正式效果验收（D37）落地后补签并补登 CLAUDE.md D62 索引。
