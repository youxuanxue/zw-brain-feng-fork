# D63 — 导入器 materialize `pub_user_role`：修复存量用户角色错配

- **scope**: `iam-pub-user-role-materialization`
- **类型**: 架构 + 角色映射门（D28 GATE；承 D62 / D7 / D11 / D51）
- **裁决**: 产品研发负责人（薛娇）2026-06-19，decision_only
- **签字账本**: `.testing/signoff/iam-pub-user-role-materialization.signoff.yaml`

## 1. 根因（生产实测，不是推测）

D62 把产品角色事实源收口到 `actor_org_role_binding`（IAM 只认证）。但**喂给该事实源的导入器读错了表**：

- `governance.py` 旧实现只把 `pub_user_organ_role`（136 行、多为 `ROLE_WORKER`）喂给角色映射；`pub_user_role`（旧平台**真实角色事实表**，4187 行，词汇为 `ROLE_BUSIAUDIT/ROLE_BUSINESS_MANAGER/ROLE_SUPER/ROLE_RESOURCEPUB...`）只 `stats.bump`、**从不落 binding**。
- **冒烟证据**：`role-mapping-manifest` 里映的 `ROLE_RESOURCEPUB/ROLE_PUBAUDIT/ROLE_BUSIOPER...` 几乎只出现在 `pub_user_role`——M0 实施工程师照着 `pub_user_role` 的词汇建了映射，但代码读的是 `pub_user_organ_role`。**清单知道真相，代码不读。**

### 用户级实测（生产 dump `dump-dsp_bsp-202604271139.sql`，生产解析器 `MysqldumpParser`，合并 organ ∪ pub_user_role 口径）

| 指标 | 值 |
|---|---|
| organ-only（旧导入器）给到角色的用户 | 106 |
| 合并 organ ∪ pub_user_role 后 | 139 |
| 仅 `pub_user_role` 有、旧导入器给 0 的用户 | 31 |
| `pub_user_role` 比 organ 更全、旧导入器会丢角色的用户 | 51 |
| **合计被旧导入器判错/判缺的有角色用户** | **82 / 137（60%）** |

典型：`gaodaliang` 真实持 `BUSIAUDIT+MANAGER+OPERATER+SYSTEM`，旧导入器只给 `OPERATER`。

## 2. 裁决

**把 `pub_user_role` 作为产品角色主源之一并入导入器**：与 `pub_user_organ_role` 合并去重，经 `role-mapping-manifest` 落到 5 个产品角色，受同一 fail-closed 门（`if iaf_sub and status=="active"`）约束。**只改导入路径（D7：写禁区仅 `adapters/legacy/`）；产品 5 角色集 / policy / 状态机 / 前端零变更。**

### 2.1 落点（`pub_user_role` 无 ORG_CODE）
绑到用户主机构 `pub_user.ORG_CODE`——与既有 `ROLE_VALUE` 兜底同口径。语义正确：`BUSIAUDIT/SYSTEM` 为全局角色、`MANAGER/OPERATER` 部门级取主机构。

### 2.2 join 正确性
`pub_user_role.USER_CODE` 是 → `pub_user.ID` 的外键（非 `pub_user.USER_CODE`，后者生产中 493/710 行为 `'0'`）。按 `USER_CODE` 索引、按 `user_id` 查，规避历史 `USER_CODE='0'` key-miss（测试 `test_pub_user_role_only_user_gets_binding_join_by_id` 钉死）。

### 2.3 app 范围 = 全 union（已签）
不建 APP_CODE allowlist 过滤机器：实测 DSP-only vs 全 union 合并后**仅差 6 人**（其中唯一安全敏感 = 3 人因非 DSP app 多拿 `ROLE_SYSTEM`，`BUSIAUDIT` 非 DSP 增量 = 0）。为 6 人差建 13-app 分类机器 = 过度工程（没人养的分类法会腐烂）。

### 2.4 角色映射增补（已签）
- `ROLE_SUPER / ROLE_SUPER_ADMIN → ROLE_SYSTEM`（57 人，平台超管 = 平台运维员，负责人 2026-06-19 签）
- `TENANT_ADMIN → ROLE_ORGAN_MANAGER`（单租户，无独立租户轴）
- `ROLE_REFION_ADMIN → ROLE_ORGAN_MANAGER`（旧库 `REGION` 拼写变体 `REFION`）
- 显式**不映射**（业务决策，非遗漏）：`ROLE_APP_DEVELOPER / TENANT_DEVELOPER / ROLE_SITE_MESSAGE_RECEIVER / ROLE_GDRP_BUSINESS_TAG / ROLE_SECURITY_MANAGER`（D55 安全管理员退役，数据安全中心立项后恢复）。

### 2.5 SYSTEM 授予可复核（不在代码里建过滤机器）
materialize 出 `ROLE_SYSTEM` 且来源含 `pub_user_role` 时，导入记 `system_role_from_user_role` warn issue（actor + 来源 app）入迁移回执。运维**重导入后用 D62 身份治理页**复核 `ROLE_SYSTEM` 持有者、撤销非预期者——用既有工具复核，不在导入器里建 app 过滤。

### 2.6 边界：只惠及重导入，不动登录认领
wiring 只让**重导入**恢复角色；登录时 `claim_legacy_actor_by_iaf` 仍只认领身份、binding 来自导入（守 D62 A1 deferral）。重导入即角色恢复载体，符合运维剧本（补 sub → 重导入）。

## 3. 实现与证据

- 代码：`zw_brain/adapters/legacy/mappers/governance.py`（索引 `pub_user_role` + 并入 `binding_by_key` + SYSTEM 复核信号）；`scripts/build_m0_sd_default_fixtures.py` `ROLE_MAPPING` + `tests/fixtures/m0-sd-default/role-mapping-manifest.json`（4 新映射）。
- 测试：`tests/test_pub_user_role_materialization.py`（5 例：仅-pubrole/ID-join、`ROLE_SUPER→SYSTEM`+复核信号、organ∪pubrole 跨 app union、无 sub fail-closed、幂等）；`tests/test_bsp_permission_pipeline_e2e.py`（pipeline 流程并入 pub_user_role）；`tests/test_bsp_sd_default_real_dump_e2e.py`（真 dump 回归：`gaodaliang` 得 `SYSTEM+BUSIAUDIT+MANAGER`）。
- **真 dump 实证（本地，old/ 在场）**：重导入后 `gaodaliang = [BUSIAUDIT, ORGAN_MANAGER, ORGAN_OPERATER, SYSTEM]`；有角色 binding 的 actor 106 → 129（受 fixture 合成 sub 覆盖约束）；`ROLE_SYSTEM` 持有者 65；幂等（连导两次 binding 数恒定）；无 sub/占位 sub → 0 binding。

## 4. 运维（不在本 PR 内执行）

生产重导入恢复角色的正确序列（依赖 IAM 回填真 sub，运维另行执行）：
1. 生产 `role_mapping_manifest` 须含本期 4 新映射（DBA/M0 把同套映射并入 dump）。
2. IAM 回填真 sub → `scripts/ingest_iam_sub_backfill.py`（整批、全或无 fail-closed）。
3. 重导入（原地 rekey、不产生重复行、D51 路径）。
4. 重导入后用身份治理页复核 `ROLE_SYSTEM` 持有者、撤销非预期者。

详见 `docs/deployment/m0-site-migration.md` D63 段。

## 5. say-no（本期不做）

- 不建 APP_CODE allowlist 过滤机器（差 6 人不值）。
- 不改登录认领写 binding（守 D62 A1）。
- 不在本 PR 跑生产重导入（运维动作）。
- 不动产品 5 角色集 / policy / 状态机 / 前端。
