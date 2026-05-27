# zw-brain 角色 / 权限管理：设计 · 现状（PR #122）· 下一步

> **读者**：接手 zw-brain 角色 / 权限 / IAF IAM 接入与旧 BSP 数据导入的研发同事。
> **目标**：30 分钟读完上手。本文是该主题的**单一事实源**——其他 docs 触及角色 / 权限 / IAM 接入 / 旧 BSP 用户去向时回链本文。
> **校对基线**：所有引用路径已对照 `origin/main`（`git rev-parse origin/main` 自查），加上 PR #122 `feature/iam-provisioning-handoff-tools` 分支。
> **职责分界**：本文涵盖 zw-brain 仓内能做的全部；IAF IAM 账号生命周期是 IAM 团队职责（基线 §1.4 / 重构方案 G1 / G7），zw-brain **不**写 IAF directory、**不**碰密码 / token / 短信 / CA / UKey。

---

## § 0 — 一页摘要

**5 层架构**（每层职责单一，禁互相侵犯）：

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 认证 (auth)        ← IAF IAM OIDC，权威源；zw-brain 不写  │
├─────────────────────────────────────────────────────────────┤
│ 2. 业务身份投影        ← actor_projection（IAF sub + 旧 BSP  │
│    (actor_projection)    用户绑定 + 角色摘要）               │
├─────────────────────────────────────────────────────────────┤
│ 3. 角色集合           ← role_codes（基线 7 角色码 +          │
│    (role_codes)          tag_lead_dept 标签位）              │
├─────────────────────────────────────────────────────────────┤
│ 4. 产品权限矩阵        ← PERMISSION_ROLES（角色 ↔ Skill        │
│    (PERMISSION_ROLES)    `.execute` 静态映射）                │
├─────────────────────────────────────────────────────────────┤
│ 5. 租户能力策略        ← tenant_capability_policy（租户启停    │
│    (tenant_policy)       + 暴露面 + auth_override）           │
└─────────────────────────────────────────────────────────────┘
```

**当前状态**：

| 维度 | 已完成 | 进行中 / 阻塞 |
| --- | --- | --- |
| 认证（IAF OIDC + BFF） | ✅ 框架在 `origin/main`（PR #110 加 BFF Redis session） | 🟡 真实内网联调待 IAM 地址联通 |
| 业务身份投影 | ✅ schema + repo + claim 解码全套（`origin/main`） | — |
| 角色集合 | ✅ 7 角色码 + `tag_lead_dept` 定义就位（`role_codes.py`）；63 行 baseline mapping | — |
| 产品权限矩阵 | ✅ `PERMISSION_ROLES` 落 `zw_brain/domain/policy.py` | — |
| 租户能力策略 | ✅ `tenant_capability_policy` schema + evaluate | — |
| 旧 BSP 数据导入 | ✅ governance mapper 完整（`origin/main`） | — |
| **A 线：IAM 注入清单** | ✅ **PR #122**（export + ingest 工具 + 文档） | 🟡 待 IAM 团队走通流转（P1-A） |
| **B 线：角色 / 权限导入** | ✅ M0 sd-default baseline 3 张 fixture + e2e + mapper 占位 fail-closed + import `--unmapped-csv` + role-mapping diff 工具（**PR #122** P0-B/C/D） | — |

**PR #122 关键交付**：详 § 5（A 线 export + ingest 工具 + 文档；B 线 P0-B mapper 占位 fail-closed + P0-C `import --unmapped-csv` + P0-D `role-mapping` diff 工具）。

**下一步主路径**（详 § 7）：
1. **P0** — ✅ 完成（sd-default 测试库一整轮 + mapper 占位 fail-closed + 现场 review 工具，详 § 7.P0）
2. **P1** — 与 IAM 团队建立第一次"开通清单 csv → 注入 → 回填 csv"流转
3. **P2** — 真实客户现场 dump 上跑 e2e

---

## § 1 — 五层架构总览

### 1.1 认证（auth） — IAF IAM OIDC

**权威源**：IAF IAM（`realm=picp`，`client_id=zw-brain`），见基线 §1.4 + 重构方案 §2.2。

**zw-brain 侧职责**：
- BFF（Backend-for-Frontend）模式：access_token / refresh_token / id_token **从不出浏览器**，仅存活后端进程；前端持 HttpOnly session cookie。
- 必须校验 `state` / `nonce` / `iss` / `aud` / `exp` / JWT 签名。
- 不实现：密码、短信、扫码、CA / UKey、OAuth2 / SAML / CAS、注册、找回密码（全部 IAM）。

**不导入**：旧 BSP 的 `PASSWORD` / OAuth token / 验证码 / CA / UKey / session — 这些是旧认证运行时秘密，跨平台无复用价值（基线 §1.4）。

**zw-brain.db tables**：无（IAF IAM 是外部依赖；BFF session 走 Redis，见 [`docs/iam-login-logout-implementation.md`](iam-login-logout-implementation.md)）。

### 1.2 业务身份投影（actor_projection）

**SoT**：表 `actor_projection`（schema 见 [`zw_brain/domain/models.py`](../zw_brain/domain/models.py)）。

字段角色：
| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `external_actor_id` | IAF `sub` | 权威主键，跨次登录稳定 |
| `tenant_id` | 环境 / IAF `project_id` | 租户隔离（Phase 1 固定 `sd-default`） |
| `org_code` | IAF claims / 旧 BSP `pub_user_organ` 导入 | 部门归属 |
| `role_codes_json` | IAF roles + 旧 BSP `pub_user_role` 经 `role-mapping-manifest` 映射后的合集 | 业务角色集 |
| `profile_json.username` | IAF `preferred_username` / 旧 BSP `pub_user.ACCOUNT` | 辅助匹配 + 显示 |
| `profile_json.iam_role_codes` | IAF `resource_access[zw-brain].roles` | IAM 直接给的角色（裁决输入之一） |
| `profile_json.account_admin` | IAF `realm_access.roles` 含 `ACCOUNT_ADMIN` | 主用户标识（**不**等于超级管理员） |
| `status` | 流程 | `active` / `disabled` / `unmatched` / `iam_account_missing` |
| `source_ref` | 流程 | `iaf:claims` / `legacy:bsp:...` |

**写入路径**：
1. 首登：IAF claim → `brain.py::_build_actor_projection_from_claims` → `sync_actor_projection` Skill（行号易漂，靠 grep；定位见 § 9）。
2. 离线导入：[`legacy.bsp.mapping.import`](../zw_brain/command/handlers/infra/legacy_bsp_mapping.py) → [`GovernanceMapper`](../zw_brain/adapters/legacy/mappers/governance.py)。

**zw-brain.db tables**：`actor_projection`、`tenant_projection`、`org_projection`、`region_projection`、`role_projection`、`actor_org_role_binding`（actor↔org↔role 三方）、`legacy_object_mapping`（**通用** legacy 回指表，不只本层用）。

### 1.3 角色集合（role_codes）

**SoT**：[`zw_brain/domain/role_codes.py`](../zw_brain/domain/role_codes.py)（D23 retrofit 后唯一事实源）。

**7 角色码 + 2 系统角色 + 1 标签位**：

| 类型 | 角色码 | 显示名 | 主要 Skill 域 |
| --- | --- | --- | --- |
| 业务 | `ROLE_ORGAN_OPERATER` | 部门操作员 | J1 申请 / J2 编制提报 |
| 业务 | `ROLE_ORGAN_MANAGER` | 部门管理员 | J1 部门内审批 / J2 资源挂接（隐式继承 OPERATER） |
| 业务 | `ROLE_BUSIAUDIT` | 业务运营员 | J2 平台运营 / 发布审核 |
| 业务 | `ROLE_SECURITY_ADMIN` | 安全管理员 | B1.1 安全策略配置 |
| 业务 | `ROLE_SECURITY_AUDIT` | 安全审计员 | B1.1 合规督查 / 异议受理 |
| 业务 | `ROLE_SYSTEM` | 平台运维员 | 运维监控 / 服务编排 |
| 系统 | `admin` | 实施工程师 | M0 验收监控（不分配给客户用户） |
| 系统 | `system` | 系统 | IAM 自动触发写投影 |
| 标签 | `tag_lead_dept` | 牵头部门 | 依附 `ROLE_ORGAN_MANAGER`；仅基础主题分类 2 项权限 |

**继承关系**（[`ROLE_HIERARCHY`](../zw_brain/domain/role_codes.py)）：`ROLE_ORGAN_MANAGER` ⊇ `ROLE_ORGAN_OPERATER` 的全部权限。

**禁止字面值**：旧设计 R1-R8 退役（D23 — 历史用户角色码已废止），preflight 段 19 [`scripts/check_no_legacy_role_codes.py`](../scripts/check_no_legacy_role_codes.py) 拦截字面值残留。

**zw-brain.db tables**：无（基线 7 角色码 + `ROLE_HIERARCHY` 是**代码常量**，跟版本一起 release）。注意：导入侧的旧角色字典另存 `role_projection`（§ 1.2 投影族，**不属本层**）。

### 1.4 产品权限矩阵（PERMISSION_ROLES）

**SoT**：[`zw_brain/domain/policy.py::PERMISSION_ROLES`](../zw_brain/domain/policy.py)（`PERMISSION_ROLES` dict + `LEAD_DEPT_TAG_PERMISSIONS` frozen set）。

形态：`{<skill_id>.execute: {ROLE_*}}` 静态映射；运行时通过 [`policy.enforce_manifest_policy`](../zw_brain/domain/policy.py) 在 Skill 调用入口拦截。

**裁决入口**：
- 静态：[`policy.permissions_for_role(role) -> set[str]`](../zw_brain/domain/policy.py)
- 运行时（每次 Skill 调用）：`brain.py::_enforce_manifest_policy` → `policy.enforce_manifest_policy(skill_id, manifest, role, payload)`
- 复合（含租户能力 + 跨租户 + 风险）：`tenant.policy.evaluate` Skill（dispatch 在 [`brain.py`](../zw_brain/command/brain.py)，靠 grep 定位）

**zw-brain.db tables**：无（`PERMISSION_ROLES` + `LEAD_DEPT_TAG_PERMISSIONS` 是**代码常量**，跟版本一起 release。**禁止运行时改**：改权限矩阵 = 改产品契约 = 必须走 PR + 部署，不允许通过 admin UI 改运行时配置）。

### 1.5 租户能力策略（tenant_capability_policy）

**SoT**：表 `tenant_capability_policy`（schema 见 [`models.py`](../zw_brain/domain/models.py)）。

字段：`tenant_id` / `capability_slug` / `version` / `surface`（webui/api/cli/mcp/a2a） / `enabled` / `auth_override_json` / `audit_class` 等。

**裁决输入**（见重构方案 §3.5）：`tenant_id` + `actor_snapshot` + `org_snapshot` + `role_codes`（限 7 角色码集合）+ `tags`（仅 `tag_lead_dept`） + `capability_slug` + `surface` + `target_ref` + `risk_context`。

**裁决输出**：`allowed` + `decision_reason` + `human_confirmation_required` + `audit_class` + `policy_version`。

**zw-brain.db tables**：`tenant_capability_policy`（租户 × 能力 × 暴露面启停 + auth_override）、`capability_package`（Registry 能力包元信息）、`capability_manifest`（Skill manifest 持久化）。

---

## § 2 — 代码事实速查表

```
zw_brain/
├── domain/
│   ├── role_codes.py              ← § 1.3 角色集合 SoT（7+2+1）
│   ├── policy.py                  ← § 1.4 PERMISSION_ROLES + ROLE_HIERARCHY +
│   │                                 LEAD_DEPT_TAG_PERMISSIONS + enforce_manifest_policy
│   ├── models.py                  ← § 1.2/1.5 全部 table schema（完整清单见 § 1.2 / § 1.5）
│   └── repositories/
│       ├── governance_projection.py ← upsert_actor / find_actor_for_iaf_claims /
│       │                              bind_actor_to_iaf_claims
│       └── legacy_mapping.py       ← legacy_object_mapping 写入
├── command/
│   ├── brain.py                   ← § 1.1+1.2 IAF claim 解码 / 校验 / 投影构造
│   │                                 关键函数（行号会漂，靠 grep）：
│   │                                   _decode_iaf_claims / _validate_iaf_claims /
│   │                                   _build_actor_projection_from_claims /
│   │                                   sync_actor_projection /
│   │                                   _actor_snapshot_from_projection /
│   │                                   _enforce_manifest_policy
│   └── handlers/infra/
│       └── legacy_bsp_mapping.py  ← `legacy.bsp.mapping.import` Skill handler
├── adapters/
│   └── legacy/
│       ├── parser.py              ← MysqldumpParser（流式）
│       └── mappers/
│           └── governance.py      ← § 4 GovernanceMapper：pub_user / pub_role /
│                                     pub_user_role / pub_user_organ / pub_resource /
│                                     pub_function 等 → § 1.2 + § 1.5 全部 tables
├── entry/rest/
│   └── server.py                  ← /auth/iaf/* BFF（PR #110 起 Redis session）
└── shared/
    ├── inference/client.py        ← 集团推理网关代理（基线 D6）
    └── sensitive_mask.py          ← mask_phone / mask_email / mask_name 等

scripts/
├── build_m0_sd_default_fixtures.py    ← 生成 baseline 3 张 manifest（占位 sub）
├── export_iam_provisioning_request.py ← § 5.2 P0-1（PR #122）
├── ingest_iam_sub_backfill.py         ← § 5.3 P0-2（PR #122）
├── import_legacy_dumps.py             ← CLI：list / parse-stats / cache / import [--unmapped-csv] / verify（P0-C）
├── diff_role_mapping_against_dump.py  ← § 5.6 P0-D（PR #122）：dump 中未覆盖 ROLE_* diff
├── check_no_legacy_role_codes.py      ← preflight 段 19：拦字面值（R1-R8 退役 D23）
└── check_iam_prod_guard.py            ← preflight 段 23：dev-iam-bypass 不入 prod

tests/fixtures/m0-sd-default/                ← 3 张 baseline manifest；行数 / 用途 / SoT 见 § 4.2
├── iaf-binding-manifest.json                ← 占位 `iaf-sd-<sha1>`，待 IAM 替换
├── role-mapping-manifest.json
└── capability-mapping-manifest.json

tests/
├── test_bsp_sd_default_real_dump_e2e.py   ← B 线全流程 e2e（含 P0-B 回归）
├── test_bsp_permission_pipeline_e2e.py    ← 权限 pipeline e2e
└── test_iam_provisioning_handoff.py       ← A 线工具 + P0-C/D 单元测试；case 数见 § 5.4

docs/
├── roles-permissions-old-platform-vs-zw-brain-handoff.md  ← 本文（单一事实源）
├── iam-login-logout-implementation.md                     ← BFF + IAM 端到端叙事
├── deployment/m0-site-migration.md                        ← § 6 现场 runbook
├── reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md
│                                                          ← 重构方案完整设计
└── approved/
    ├── zw-brain-architecture.md                           ← 架构基线
    └── zw-brain-roles.md                                  ← 7 角色码官方定义
```

---

## § 3 — 运行时鉴权链路（首登 / 后续请求）

### 3.1 首登

```
浏览器                  zw-brain BFF                  IAF IAM
  │ ──── GET /login ──→  │
  │                       │ ──── 302 → IAM authorize (state+nonce) ────→ │
  │                                                                       │
  │ ←── 302 callback ─── (用户在 IAM 完成登录) ────────────────────────── │
  │ ──── GET /auth/iaf/callback?code=... ──→ │
  │                       │ ──── code → token (authorization_code grant) ──→ │
  │                       │ ←── access_token + id_token (JWT) ────────────── │
  │                       │ ─── 解码 + 验签 + state/nonce/aud/exp 校验 ────│
  │                       │ ─── 找/建 actor_projection (按 sub) ────────── │
  │                       │ ─── 跑 actor.projection.sync Skill ─────────── │
  │                       │ ─── 构造 actor_snapshot 入 BFF session ─────── │
  │ ←── 302 / + HttpOnly  │
  │     session cookie    │
```

关键函数（按调用顺序）：
- `entry/rest/server.py::auth_iaf_*`（路由）
- `command/brain.py::_decode_iaf_claims` → `_validate_iaf_claims` → `_build_actor_projection_from_claims`
- `command/brain.py::sync_actor_projection` Skill
- `domain/repositories/governance_projection.py::upsert_actor` / `bind_actor_to_iaf_claims`
- `command/brain.py::_actor_snapshot_from_projection`（生成 session 用 snapshot）

### 3.2 后续 Skill 调用

```
浏览器 ── 请求 (session cookie) ──→ BFF
                                      │
                                      ├── 从 session 取 actor_snapshot
                                      │   （role_codes / tenant_id / org_code / 等）
                                      │
                                      ├── _enforce_manifest_policy(skill_id, manifest, role, payload)
                                      │     ├── policy.enforce_manifest_policy → 角色↔权限矩阵
                                      │     ├── LEAD_DEPT_TAG_PERMISSIONS → 标签位校验
                                      │     └── 命中 → 通过；不命中 → PermissionError
                                      │
                                      ├── tenant.policy.evaluate(...)
                                      │     ├── 租户能力启停（tenant_capability_policy）
                                      │     ├── 暴露面是否允许 (webui/api/cli/mcp/a2a)
                                      │     ├── 跨租户 / 写操作 / 风险标
                                      │     └── 输出 allowed + audit_class + policy_version
                                      │
                                      └── 写 capability_call + audit_event（强同步落库）
```

---

## § 4 — 旧 BSP → zw-brain 一次性导入（A 线 + B 线）

### 4.1 数据流总览

```
                   ┌─────────────────────────────────────────────┐
                   │ A 线传送带（认证信息）— PR #122 新增工具    │
                   ├─────────────────────────────────────────────┤
旧 BSP dump ───┐   │                                              │
(pub_user)     ├──→ export_iam_provisioning_request.py ──→ csv ──┐│
               │   │                                              ││
iaf-binding ───┘   │                                       IAM   ││
manifest           │                                       团队  ││
(占位 sub)         │                                       开通  ││
                   │                                              ││
                   │ 回填 csv ← ingest_iam_sub_backfill.py ← ─────┘│
                   │ (legacy_user_id, iaf_sub)                    │
                   │  ↓ 幂等替换占位 sub                          │
                   │ iaf-binding manifest（真实 IAM sub）         │
                   └────────┬─────────────────────────────────────┘
                            │
                   ┌────────▼─────────────────────────────────────┐
                   │ B 线传送带（业务身份/角色/权限）— 已在 main  │
                   ├──────────────────────────────────────────────┤
                   │  legacy.bsp.mapping.import Skill             │
                   │     ↓                                        │
                   │  GovernanceMapper (governance.py)            │
                   │     ↓                                        │
                   │  actor_projection / role_projection /        │
                   │  org_projection / region_projection /        │
                   │  actor_org_role_binding /                    │
                   │  tenant_capability_policy /                  │
                   │  legacy_object_mapping                       │
                   └──────────────────────────────────────────────┘
```

### 4.2 GovernanceMapper 输入 / 输出契约

**输入**（旧 BSP dump）：

| 旧表 | 主要字段 | 用途 |
| --- | --- | --- |
| `pub_user` | ID / ACCOUNT / NAME / PHONE / MOBILE / EMAIL / ORG_CODE / REGION_CODE | actor 投影 |
| `pub_role` | CODE / NAME | role 投影 |
| `pub_user_role` | USER_ID / ROLE_CODE | actor↔role 关系 |
| `pub_user_organ` | USER_ID / ORG_CODE | actor↔org 关系 |
| `pub_user_organ_role` | USER_ID / ORG_CODE / ROLE_CODE | 部门内角色绑定（优先） |
| `pub_organ` | CODE / NAME / TRACE_CODE / REGION_CODE | org 投影 |
| `pub_region` | CODE / NAME / PARENT_CODE / GRADE | region 投影 |
| `pub_resource` | ID / PATH / NAME | capability mapping 候选源 |
| `pub_function` / `pub_role_function` / `pub_role_resource` | — | 旧权限关系（需 manifest 映射） |

**3 张 manifest（必备，否则 mapper fail-closed）**：

| Manifest | SoT 位置 | 内容 | 当前 sd-default baseline 行数 |
| --- | --- | --- | --- |
| `iaf-binding-manifest.json` | `tests/fixtures/m0-sd-default/` | `legacy_user_id → iaf_sub` 绑定 | **710** entries |
| `role-mapping-manifest.json` | 同上 | 旧 `ROLE_*` → 7 产品角色码 + `tag_lead_dept` | **63** rows |
| `capability-mapping-manifest.json` | 同上 | `pub_resource.ID → capability_id` | **158** rows |

**输出**（zw-brain canonical 投影）：见 §1.2 + §1.5 表清单。

**禁导字段**（[`governance.py::REAL_SECRET_FIELDS`](../zw_brain/adapters/legacy/mappers/governance.py)）：
`password` / `pwd` / `passwd` / `password_hash` / `password_salt` / `token` / `access_token` / `refresh_token` / `verification_code` / `sms_status` / `session` / `session_id` / `cookie` / `client_secret` / `secret` / `otp_key` / `sensitive_hmac` / `ukey` / `ip_list` / `ip_access_status` / `elec_img` / `pwd_lastupdate` / `pwd_changed` / `hmac` — 这些字段在 mapper 解析时直接 drop，不进 canonical 也不进审计 / 日志。

**fail-closed 状态**：
- `iam_account_missing` — 用户在 manifest 内但 IAM 未注入 → 不写 actor_projection 业务字段，只留 evidence
- `unmatched` — 用户匹配不到唯一 IAF sub → 同上
- `disabled` — 旧 BSP `status != active` → status 标 disabled，不分配 role
- `unmapped_permission` — 旧权限未在 capability-mapping-manifest 命中 → 不写 tenant_capability_policy，进 issue 报告
- `missing_role_mapping` — 旧 role 未在 role-mapping-manifest 命中 → 同上

### 4.3 端到端流（M0 现场实施）

详见 [`docs/deployment/m0-site-migration.md`](deployment/m0-site-migration.md) 「一条主旅程」 step 0a / 0b / 1-12。本文 § 6 给出 sd-default 现场 runbook。

---

## § 5 — PR #122 现状（feature/iam-provisioning-handoff-tools）

### 5.1 提交清单

| Commit | 内容 |
| --- | --- |
| `8b81a68` feat | A 线两端代码化 + 主旅程文档补 step 0a/0b + 19 单元测试 |
| `ce779b6` fix | 自我 review R-001..R-003：ingest 占位前缀 fail-closed + diff 黑名单 + 3 测试补缺 |
| `31b22c9` fix | R-004：删 `--allow-placeholder-residual` 逃生口（绕 fail-closed 太诱人，反 R-001 设计意图） |
| `f3b113e` fix | ingest doc 与代码对齐 + `not_found_in_manifest > 0` 退出 1（与残留占位 exit 2 分级） |
| `a39d2c9` feat | **P0-B/C/D 落地**：mapper 占位前缀 fail-closed（§ 5.5）+ import `--unmapped-csv`（§ 5.6）+ `diff_role_mapping_against_dump.py`（§ 5.7）+ handoff doc 同步 |
| `0c660de` fix | preflight 段 19 legacy 角色码字面值修复（R1-R8 退役；CI false negative：worktree 路径 SKIP 兜底） |

**CI**：见 PR checks（preflight 段 19 须全仓扫描通过）。

### 5.2 工具一：export_iam_provisioning_request.py

```
uv run python scripts/export_iam_provisioning_request.py \
  --manifest tests/fixtures/m0-sd-default/iaf-binding-manifest.json \
  --dump old/10示例数据/dump-dsp_bsp-202604271139.sql \
  --out tests/fixtures/m0-sd-default/iam-provisioning-request.csv \
  [--diff <上次 csv>]    # 增量模式：只输出 added / changed
  [--json]               # 摘要 json 到 stdout
```

**输入**：
- `iaf-binding-manifest.json`（SoT：哪些 legacy_user 进 IAM 注入清单）
- 旧 BSP dump（可选；缺失时只输出最小列，标 `note=legacy_dump_missing`）

**输出**：17 列 csv（脱敏）：
```
legacy_user_id, account, preferred_username,
display_name_mask, phone_mask, mobile_mask, email_mask,
org_code, org_name, region_code, region_name,
is_admin_level, status, type_code,
binding_status, iaf_sub_placeholder, note
```

**脱敏规则**：
- `display_name_mask` / `phone_mask` / `mobile_mask` 走 `zw_brain.shared.sensitive_mask`，role 默认 `external`
- `email_mask` 兜底：非 `@` 格式（旧 dump 有时 EMAIL 列塞 hash）强 mask `***`，不原样输出
- 密码 / OTP / UKEY / IP_LIST / SENSITIVE_HMAC 等 `REAL_SECRET_FIELDS` 永不入 csv

**职责边界（重要）**：
- 仓内 csv 是**脱敏版本** = IAM 团队「开通名单匹配凭据 + 部门 / 区划上下文」
- IAM 开通账号需要的**明文联系方式**由客户实施工程师从客户 HR 另渠道拿到，直接交给 IAM 团队，**不经过 zw-brain 仓库**

### 5.3 工具二：ingest_iam_sub_backfill.py

```
uv run python scripts/ingest_iam_sub_backfill.py <backfill.csv> \
  --manifest tests/fixtures/m0-sd-default/iaf-binding-manifest.json \
  [--dry-run]   # 只打摘要不写盘
  [--json]
```

**输入** csv 最少 2 列（大小写不敏感 + 注释行 `#...` 跳过）：
```
legacy_user_id, iaf_sub [, binding_status]
```

**`_classify` 优先级**（[`scripts/ingest_iam_sub_backfill.py::_classify`](../scripts/ingest_iam_sub_backfill.py)）：
1. IAM 明确标 `disabled` / `unmatched` → 尊重判断（即便 sub 非空）
2. sub 空或写 missing token（`"" / iam_account_missing / missing / none / null`）→ `iam_account_missing` fail-closed
3. 正常：sub 落库 + status 默认 `bound`

**退出码**：
| code | 含义 |
| --- | --- |
| 0 | 全部成功 |
| 1 | `not_found_in_manifest > 0`（backfill csv 含 manifest 没有的 legacy_user_id；不写盘） |
| 2 | `placeholder_residual > 0`（落库后仍有 `iaf-sd-<sha1>` 占位 sub；写盘了但流程未跑完） |

**幂等性**：同一份 backfill csv 反复跑结果一致；watermark `" | iam-sub backfilled"` 只在 description 加一次。

### 5.4 测试与门禁

- [`tests/test_iam_provisioning_handoff.py`](../tests/test_iam_provisioning_handoff.py)：**33 cases**（mask 兜底 / diff 黑名单 / classify 8 参数化 / ingest 占位前缀守卫 / not_found 错误路径 / 幂等 / watermark / 列名归一化 + 注释行 / **P0-C `_filter_issues` + `_write_unmapped_csv` 3 cases** / **P0-D `diff_roles` 3 cases**）
- [`tests/test_bsp_sd_default_real_dump_e2e.py`](../tests/test_bsp_sd_default_real_dump_e2e.py)：**3 cases**（IAF→role policy 闭环 / 缺 manifest fail-closed / **P0-B 占位 sub 进 mapper fail-closed 回归**）
- preflight 36 段全绿（含段 17 iam-doc-freshness / 段 19 no-legacy-role-codes / 段 23 iam-prod-guard）

### 5.5 P0-B：mapper 占位前缀 fail-closed

[`zw_brain/adapters/legacy/mappers/governance.py`](../zw_brain/adapters/legacy/mappers/governance.py) 在 `_string_value` 解析 binding 后立即过 `_normalize_iaf_sub(raw)`：

```python
_IAF_SUB_PLACEHOLDER_PREFIX = "iaf-sd-"

def _normalize_iaf_sub(raw: str) -> str:
    sub = (raw or "").strip()
    if not sub or sub.startswith(_IAF_SUB_PLACEHOLDER_PREFIX):
        return ""
    return sub
```

pub_user / sys_user 两条分支都接归一化后的 `iaf_sub`，占位 sub 被视同未注入，下游 `if not iaf_sub:` 路径统一触发 `iam_account_missing` issue 不写 `actor_projection` 业务字段。

回归测试：[`tests/test_bsp_sd_default_real_dump_e2e.py::test_sd_default_real_dump_fail_closed_on_placeholder_sub`](../tests/test_bsp_sd_default_real_dump_e2e.py)。

ingest 工具的 placeholder guard（PR #122 R-001）+ mapper 的占位归一化形成**两道闸门**——任一手工绕过都拦得下来。

### 5.6 P0-C：import `--unmapped-csv` 落表

[`scripts/import_legacy_dumps.py import`](../scripts/import_legacy_dumps.py) 加 `--unmapped-csv <path>` + `--issue-types <comma>`：

```
uv run python scripts/import_legacy_dumps.py import dsp_bsp \
  --unmapped-csv /tmp/unmapped.csv \
  [--issue-types unmapped_permission,missing_role_mapping]   # 覆盖默认；'all' 输出全部
```

默认范围：`unmapped_permission` / `missing_role_mapping` / `iam_account_missing` / `missing_org_relationship`（其他 issue 是数据/流程问题，落 csv 帮助小）。

CSV 列：`issue_type, table, legacy_ref, detail_json`，按 `(type, table, legacy_ref)` 排序便于 diff。

工作流：跑 import → 看 csv → 人工补 manifest → 重跑 import 闭环。

### 5.7 P0-D：role-mapping diff 工具

[`scripts/diff_role_mapping_against_dump.py`](../scripts/diff_role_mapping_against_dump.py)：

```
uv run python scripts/diff_role_mapping_against_dump.py \
  --dump <客户 dump 路径> \
  --manifest tests/fixtures/m0-sd-default/role-mapping-manifest.json \
  --out tests/fixtures/m0-sd-default/role-mapping-uncovered.csv --json
```

扫 `pub_role.CODE` + `pub_user_role.ROLE_CODE` + `pub_user_organ_role.ROLE_CODE`（按 `#` 拆多角色）union → diff `role-mapping-manifest.rows[].legacy_role_ref` → 输出未覆盖 ROLE_* 与各 table 出现次数。

CSV 列：`legacy_role_ref, occurrence_pub_role, occurrence_pub_user_role, occurrence_pub_user_organ_role, total_occurrences`，按 total 降序便于优先处理高频。

sd-default sample dump 实测：baseline 63 行 → dump 51 个 distinct role → 9 个 uncovered（高频如 `ROLE_SUPER` / `TENANT_DEVELOPER` 等大多是 `build_m0_sd_default_fixtures.py` 显式不映射的技术 / 多租户残留角色）。

---

## § 6 — sd-default 现场 runbook（实施同事按步骤跑）

### 前提
- 本机有真实 sd-default dump（路径示例 `~/Downloads/dump-sd-default-YYYY-MM-DD.sql`）
- 本机 IAM 团队联系方式 + 团队约定的 csv 列形态
- 客户 HR 明文花名册（不入仓）

### 步骤

**1. 生成 baseline 3 张 manifest**（基于 dump 派生）：
```bash
uv run python scripts/build_m0_sd_default_fixtures.py
# 写到 tests/fixtures/m0-sd-default/{iaf-binding,role-mapping,capability-mapping}-manifest.json
# iaf_sub 是 iaf-sd-<sha1> 占位
```

**2. 跑 P0-1 export 出 IAM 开通清单**：
```bash
uv run python scripts/export_iam_provisioning_request.py \
  --dump ~/Downloads/dump-sd-default-YYYY-MM-DD.sql \
  --out /tmp/iam-provisioning-request.csv --json
# 检查 dump_present=true, legacy_dump_missing=0
```

**3. 把 csv + 明文花名册交给 IAM 团队**：
- csv：仓内脱敏版（show 给 IAM 用作"哪些账号要开通 + 部门/区划上下文"）
- 明文花名册：客户 HR 明文邮箱 / 手机号（IAM 开通账号必需，不入仓）

**4. IAM 团队回填**：
回填 csv 形态：
```
legacy_user_id,iaf_sub,binding_status
005E0C60550741A6BD55183F21900C11,sd-default-iam-sub-001,bound
01054F1BB11048A89DAB6862824A0B60,,iam_account_missing
...
```

**5. dry-run 回填**：
```bash
uv run python scripts/ingest_iam_sub_backfill.py /path/to/iam-backfill.csv --dry-run --json
# 看摘要：
#   not_found_in_manifest 必须 = 0（否则 exit 1，修 csv）
#   placeholder_residual_count 应较 manifest_total 大幅下降
```

**6. apply 回填**：
```bash
uv run python scripts/ingest_iam_sub_backfill.py /path/to/iam-backfill.csv --json
echo "exit=$?"
# exit=0 → 全部 ok
# exit=2 → 仍有占位残留：催 IAM 团队补开通 或 把这些用户在 csv 中标 iam_account_missing
```

**7. 跑 B 线导入**（含 P0-C `--unmapped-csv` 落表）：
```bash
uv run python scripts/import_legacy_dumps.py import dsp_bsp \
  --unmapped-csv /tmp/sd-default-unmapped.csv
# 把 manifest（已替换真实 sub）+ dump 一次性导入 canonical；issue 落 csv 方便补 manifest
```

**7a. （可选）跑 P0-D role-mapping diff，看 dump 中有无 baseline 未覆盖的 ROLE_***：
```bash
uv run python scripts/diff_role_mapping_against_dump.py \
  --dump ~/Downloads/dump-sd-default-YYYY-MM-DD.sql --json
# 输出 csv：高频未覆盖 ROLE_* 优先补 role-mapping-manifest
```

**8. verify**：
```bash
uv run python scripts/import_legacy_dumps.py verify --tenant sd-default --json
# 看 total_unresolved / total_conflicted 是否 0；不为 0 → 看 sample_missing 修复
```

**9. e2e**：
```bash
uv run pytest tests/test_bsp_sd_default_real_dump_e2e.py -v
```

**10. 真实 IAM token 跑通**（依赖 P1）：用 IAM 团队提供的测试账号登录，验证 `actor_snapshot` 含正确 tenant / org / role_codes 且 `tenant.policy.evaluate` 裁决符合 PERMISSION_ROLES 矩阵。

---

## § 7 — 下一步计划

### P0 — 本机 / 测试库（不依赖 IAM 在线）— **全部完成**

| # | 工作 | 状态 |
| --- | --- | --- |
| P0-A | 在测试库走通 § 6 step 1-9 全流程（sd-default sample dump） | ✅ **已验证**（PR #122 分支跑过）。step 1 fixture 已在 main；step 2/5/6 工具冒烟（710 entry export + dry-run/apply ingest 幂等）；step 7-9 仓内 e2e 3 pass / ~112s + [`test_bsp_permission_pipeline_e2e.py`](../tests/test_bsp_permission_pipeline_e2e.py) 4 pass。step 10 真实 IAM token 依赖 **P1-C**。 |
| P0-B | mapper 加 `iaf-sd-` 占位前缀 fail-closed + 回归测试 | ✅ **已落地**（PR #122）。`governance.py` 加 `_normalize_iaf_sub` helper，pub_user / sys_user 两条分支均接归一化后的 `iaf_sub`；占位 sub 触发 `iam_account_missing` issue + 不写 `actor_projection` 业务字段 + 不写 active binding。回归 [`test_sd_default_real_dump_fail_closed_on_placeholder_sub`](../tests/test_bsp_sd_default_real_dump_e2e.py) pass。详 § 5.5。 |
| P0-C | `import --unmapped-csv` 落表方便补 manifest | ✅ **已落地**（PR #122）。详 § 5.6。 |
| P0-D | `role-mapping` diff 工具 | ✅ **已落地**（PR #122）。详 § 5.7。 |

### P1 — 与 IAM 团队 + 内网联调

| # | 工作 | 阻塞 | 完成判据 |
| --- | --- | --- | --- |
| P1-A | IAM 团队建立第一次"开通清单 csv → 注入 → 回填 csv"流转 | IAM 团队 SLA / 字段约定 | 走完 § 6 step 3-6；ingest 跑完 `placeholder_residual_count=0` 且 `actor_projection.iaf_sub` 全是真实 IAM directory sub |
| P1-B | IAM 内网测试地址（`cnp-jn-rgzn-inlinux-test.inspur.com:9443`）联通 | 网络 | discovery / JWKS / token endpoint 可达 |
| P1-C | 真实 OIDC 联调：授权码 / token / JWKS 验签 / `state` / `nonce` / logout 全链路 | P1-B | 跑通真实账号登录、`actor_snapshot` 字段正确 |
| P1-D | `ACCOUNT_ADMIN` 真实策略验证（**不**等于超级管理员；只作 policy condition） | P1-C | 真实 ACCOUNT_ADMIN 账号能/不能调用对应 capability，与 `PERMISSION_ROLES` 一致 |
| P1-E | preflight-debt: dev-iam-bypass prod runtime guard 升级 | 首个客户部署 | 已在段 23 + `ZW_BRAIN_DEV_IAM_BYPASS` startup hook，trigger 一到就把"零认证 fallback"硬拒 |

### P2 — 真实客户现场

| # | 工作 | 阻塞 | 完成判据 |
| --- | --- | --- | --- |
| P2-A | 客户提供真实 dump + IAM directory + HR 花名册 | 客户 SLA | 跑完 § 6 全流程，e2e green |
| P2-B | 三方抽查（部门管理员 / 业务运营员 / 安全审计员） | P2-A | m0-site-migration.md 主旅程 step 11 |
| P2-C | 关闭迁移模式 + 旧 BSP 在线服务下线 | P2-B | step 12；旧 BSP 不再作为生产依赖 |

---

## § 8 — 已知 debt（来自 [`docs/preflight-debt.md`](preflight-debt.md) 角色 / 权限相关条目）

| Debt | trigger | 升级路径 |
| --- | --- | --- |
| dev-iam-bypass runtime prod guard | 首个客户部署上线前 | runtime startup hook 在 `ZW_BRAIN_DEPLOY_MODE=prod` 时拒绝 `ZW_BRAIN_DEV_IAM_BYPASS=1` |
| AgentRuntime 协议 schema 字段就绪 | 首个真实外部 Agent 接入需求 | T1 触发当日落地 validate / doctor 工具链（D30） |

---

## § 9 — 代码快照（grep 友好）

| 主题 | 关键 grep | 主要路径 |
| --- | --- | --- |
| BFF 登录换票 | `/auth/iaf/callback\|/auth/iaf/refresh\|/auth/iaf/logout` | `zw_brain/entry/rest/server.py` |
| Claim 解码 / 投影 | `_decode_iaf_claims\|_validate_iaf_claims\|_build_actor_projection_from_claims\|sync_actor_projection\|_actor_snapshot_from_projection` | `zw_brain/command/brain.py` |
| 角色集合 SoT | `BUSINESS_ROLE_CODES\|SYSTEM_ROLE_CODES\|ROLE_HIERARCHY\|TAG_LEAD_DEPT\|ROLE_DISPLAY_NAMES_ZH` | `zw_brain/domain/role_codes.py` |
| 权限矩阵 + 运行时裁决 | `PERMISSION_ROLES\|LEAD_DEPT_TAG_PERMISSIONS\|permissions_for_role\|enforce_manifest_policy` | `zw_brain/domain/policy.py` |
| 投影表 / 租户能力 | `ActorProjectionRecord\|RoleProjectionRecord\|ActorOrgRoleBindingRecord\|TenantCapabilityPolicyRecord\|LegacyObjectMappingRecord` | `zw_brain/domain/models.py` |
| Governance repo | `upsert_actor\|find_actor_for_iaf_claims\|bind_actor_to_iaf_claims\|upsert_role` | `zw_brain/domain/repositories/governance_projection.py` |
| Legacy 导入 mapper | `GovernanceMapper\|HANDLED_TABLES\|REAL_SECRET_FIELDS\|_PUB_GOVERNANCE_TABLES\|iam_account_missing\|_normalize_iaf_sub\|_IAF_SUB_PLACEHOLDER_PREFIX` | `zw_brain/adapters/legacy/mappers/governance.py` |
| Skill 入口 | `legacy.bsp.mapping.import\|tenant.policy.evaluate\|actor.projection.sync\|iam.binding.reconcile\|role.mapping.configure` | `zw_brain/command/handlers/infra/legacy_bsp_mapping.py` + `dispatch.py` |
| PR #122 工具 | `export_iam_provisioning_request\|ingest_iam_sub_backfill\|diff_role_mapping_against_dump\|_classify\|_scan_residual_placeholders\|_PLACEHOLDER_PREFIX\|_EXCLUDED_FROM_DIFF\|_filter_issues\|_write_unmapped_csv\|_DEFAULT_UNMAPPED_ISSUE_TYPES\|diff_roles\|_collect_dump_roles` | `scripts/` |

---

## 变更记录

| 日期 | 说明 |
| --- | --- |
| 2026-05-19 | 初版：基于 `origin/main` 与上文引用文档整理（最简对照表）。 |
| 2026-05-27 | **重写为单一事实源**：5 层架构总览 + 代码事实速查 + 运行时鉴权链路 + A/B 双线传送带 + PR #122 现状 + sd-default 现场 runbook + P0/P1/P2 计划 + 已知 debt + grep 表。同日内连改三轮：(a) 文档结构落地；(b) 两轮 review 修订（准确性 / 冗余 / 重复 finding 闭环）；(c) **P0-B/C/D 落地**（mapper 占位 fail-closed §5.5 + `import --unmapped-csv` §5.6 + `diff_role_mapping_against_dump.py` §5.7）后同步 §0/§5.1/§5.4/§6/§7/§8/§9。 |

（后续若 `role.mapping.configure` / Governance UI 等与本文表述不一致，请更新本文并保持与 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 对齐。）
