# 旧平台 ↔ zw-brain：用户角色与权限承接对照

> **alembic 整体删除通告（2026-05-20，详见 D23 二次升级）**：本文表格中提及的 `alembic/versions/0005_*` / `0008_*` / `0009_*` 已在二轮再砍中**一并删除**（alembic 整体退役）。新项目用 SQLAlchemy `Base.metadata.create_all()` 直接建表，不再走迁移链。文本保留作为旧 BSP → zw-brain handoff 心智参考。

面向用户与权限模块开发、对接同学的同步说明：**「这人是谁」（认证）与「这人带什么业务角色 / 能干啥」（本地投影 + 产品基线 + 租户策略）**分别在旧 BSP 与新架构里落在哪；便于排障与设计评审时对齐心智模型。

---

## 阅读指引

| 术语 | 含义 |
| --- | --- |
| **IAM / IAF** | 统一 OIDC；zw-brain 只认 JWT，不自建口令体系。叙事见 [`docs/iam-login-logout-implementation.md`](./iam-login-logout-implementation.md)。 |
| **旧 BSP / ucenter** | 自建用户–角色–菜单权限树；语义与迁移边界见 [`docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md`](./reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md)。 |
| **`PERMISSION_ROLES`** | 产品维度的 **ROLE_* ↔ Skill `.execute`** 基准矩阵：`zw_brain/domain/policy.py`。 |
| **`actor_projection`** | 租户内用户在 zw-brain 的 **本地业务身份投影**，含 **`role_codes_json`**（与 Token 合并后反映在 **`actor_snapshot.role_codes`**）。 |
| **`tenant_capability_policy`** | 租户–能力包的启停 / 暴露面 / 策略覆盖（与 `tenant.policy.evaluate` 配合）；区别于「IAM 不认人」，也区别于纯代码矩阵基线。 |

**实现基线校对**：文末「代码快照」所列路径已相对远程 **`origin/main`** 核对一致（请以你本地 `git rev-parse origin/main` 为准随时间更新）。

---

## 一览表（大白话）

| 维度 | 旧平台 | zw-brain | zw-brain 实现落点（速查） |
| --- | --- | --- | --- |
| **这人谁认的** | 自建登录中心 / ucenter：**账号 + 会话**由本阵营发放 | **IAF IAM OIDC**：以 JWT **`sub`** 等为认证主键；BFF **`HttpOnly`** 会话，`access_token` 不出浏览器 | `zw_brain/entry/rest/server.py`（`/auth/iaf/*`）；`zw_brain/command/brain.py`（`_decode_iaf_claims`、`_validate_iaf_claims`、`_build_actor_projection_from_claims`）；[`docs/iam-login-logout-implementation.md`](./iam-login-logout-implementation.md) |
| **业务角色记在谁那儿** | **BSP 库表**：用户↔角色（如 **`sys_user_role` / `sys_role`**），权限与 **菜单 / 按钮** 等挂载在 **`sys_permission` / `sys_role_permission`** 等链路 | **双源**：JWT 里的 **`realm_access.roles`** 与 **`resource_access[zw-brain client].roles`**；库里 **`actor_projection.role_codes_json`**（API/会话快照为 **`actor_snapshot.role_codes`**） | 合并逻辑：`brain.py::_build_actor_projection_from_claims`。表：`actor_projection`、`role_projection`、`actor_org_role_binding`（`zw_brain/domain/models.py`）。写库：`zw_brain/domain/repositories/governance_projection.py`。首登刷新：`brain.py::sync_actor_projection` / Skill **`actor.projection.sync`**；换票成功后见 `server.py` + 上文 IAM 文档。迁移：`alembic/versions/0005_*`、`0008_*`、`0009_*` |
| **改习惯的姿势（换人角色 / 纠错）** | **改 BSP / 权限后台**：用户角色、菜单与按钮绑定 | （1）**改 IAM**：组 / client roles → 下一票 Token 自带新集合。（2）**改 zw-brain 投影**：再登录 **`actor.projection.sync`**；或 BSP **导入 / manifest** 批处理 | IAM 仍为权威输入之一；投影刷新依赖 **`GovernanceProjectionRepository.upsert_actor`** 等。**Legacy**：`zw_brain/adapters/legacy/mappers/governance.py` 写 **`actor_projection` / `role_projection`**，与 **`legacy.bsp.mapping.import`** 等治理能力配合。租户能力差异另见 **`tenant_capability_policy`** + **`tenant.policy.evaluate`**（`brain.py`） |

---

## zw-brain 实现落点（展开）

### 1. 认证：这人谁认的

- **REST BFF**：`zw_brain/entry/rest/server.py` — Cookie 会话、`/auth/iaf/token`、校验 `state` / `nonce`、对接 healthz / 本地验签等行为以 [`docs/iam-login-logout-implementation.md`](./iam-login-logout-implementation.md) 为准。
- **Claims → 投影草稿**：`zw_brain/command/brain.py` — **`_build_actor_projection_from_claims`**（从 `resource_access` / `realm_access` 抽 roles，并入 **`role_codes`**）。

### 2. 本地角色：`role_codes_json` / `actor_snapshot.role_codes`

- **SQLAlchemy 模型**：`zw_brain/domain/models.py`
  - **`ActorProjectionRecord`** → **`actor_projection`**，`role_codes_json`
  - **`RoleProjectionRecord`** → **`role_projection`**（导入侧角色字典投影）
  - **`ActorOrgRoleBindingRecord`** → **`actor_org_role_binding`**（人–组织–角色；`_sync_actor_role_bindings`）
- **Repository**：`zw_brain/domain/repositories/governance_projection.py` — **`upsert_actor`**、**`find_actor_for_iaf_claims`**、**`bind_actor_to_iaf_claims`**。
- **首登写入 / 刷新**：Skill **`actor.projection.sync`**，`brain.py::sync_actor_projection`；**`actor.projection.sync.execute`** 的白名单角色见 **`zw_brain/domain/policy.py`**（含 **`system`** 用于 IAM 触发写投影）。
- **运行时与 Token 快照**：会话中的 **`actor_snapshot`** 字段含义见 IAM 文档；前端 **`roles`** 为 claims 与快照合并后的呈现。

### 3. 「能干啥」：与 `PERMISSION_ROLES`、`tenant_capability_policy` 的关系

- **产品基线**：`zw_brain/domain/policy.py` — **`PERMISSION_ROLES`**、`ROLE_HIERARCHY`、`LEAD_DEPT_TAG_PERMISSIONS`；Skill 网关侧 **`enforce_manifest_policy`** / **`permissions_for_role`**。
- **租户–能力**：表 **`tenant_capability_policy`**（见 `models.py`）+ **`brain.py`** 中对 **`tenant.policy.evaluate`** 的裁决（与 Registry / fail-closed / `actor_snapshot` 绑定一致性校验配合）。

上述三层不要混用：**IAM 不认业务菜单树**；**投影解决「你是谁 + 挂了哪些 ROLE_*」**；**`PERMISSION_ROLES` / 租户策略解决「ROLE_* / 租户上下文能否调用某能力」**。

### 4. 从旧 BSP 迁入（对齐旧到新）

- 设计单一事实源：[`docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md`](./reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md)（**`sys_user_role`、`sys_role_permission` → manifest / `tenant_capability_policy`**，不在线读 BSP）。
- 代码侧适配器：**`zw_brain/adapters/legacy/mappers/governance.py`** 向 **`actor_projection` / `role_projection`** 等写入；与 **`brain.py`** 中 **`legacy.bsp.mapping.import`** 治理能力配合。

---

## 代码快照（便于 grep）

| 能力 | 主要路径 |
| --- | --- |
| BFF 登录换票 | `zw_brain/entry/rest/server.py` |
| JWT / 投影 claims | `zw_brain/command/brain.py`（`_build_actor_projection_from_claims`、`sync_actor_projection`、`_actor_snapshot_from_projection`） |
| 表定义 | `zw_brain/domain/models.py`：`actor_projection`、`role_projection`、`actor_org_role_binding`、`tenant_capability_policy` |
| Governance 仓储 | `zw_brain/domain/repositories/governance_projection.py` |
| 产品 ROLE×Skill 矩阵 | `zw_brain/domain/policy.py`：`PERMISSION_ROLES` |
| Legacy 写入投影 | `zw_brain/adapters/legacy/mappers/governance.py` |
| IAM 端到端叙事 | [`docs/iam-login-logout-implementation.md`](./iam-login-logout-implementation.md) |

---

## 变更记录

| 日期 | 说明 |
| --- | --- |
| 2026-05-19 | 初版：基于 `origin/main` 与上文引用文档整理，供权限模块与外协同步。 |

（后续若 **`role.mapping.configure`** / Governance UI 等与本文表述不一致，请更新本 md 并保持与 `docs/reconstructs/dsp-bsp-manage-governance-reconstruction-plan-v1.md` 对齐。）
