# D54 — 0605 验收回合 GATE（代理服务注册角色口径 + 反向编目审核命名）

> **类型**：角色/权限口径变更 + 一词一概念命名（D28 GATE，decision_only）
> **签字**：薛娇（产品研发负责人），2026-06-08
> **触发链路**：第一轮修复（PR #220–#225）后研发/业务验收复核 [`old/问题反馈/问题反馈-0605/问题反馈-0605-验收.md`](../../old/问题反馈/问题反馈-0605/问题反馈-0605-验收.md) → 第二轮核查清单 [`修复任务目标清单-验收回合.md`](../../old/问题反馈/问题反馈-0605/修复任务目标清单-验收回合.md) §三 GATE 门禁清单（T6 + G1）。
> **核查依据**：当前 HEAD 代码事实（file:line 实读）+ 旧平台事实数据 `old/20260519/平台系统角色菜单梳理v5.xlsx` + `old/12-datastructure/dsp_service.xml`。
> **性质**：实现前方向裁决（decision_only，不抬 `.feature` 状态）；两项各自实现由 T6/T7/T8、G1 修复任务承接，落地后另带 D37 效果验收。账本单源 `.testing/signoff/feedback-0605-acceptance-gate.signoff.yaml`。

---

## GATE-1 ｜代理服务注册角色口径纠正（T6）

### 背景与根因

验收附图 `0605_r10_L`：业务运营员 pengxi01 在「代理服务注册向导」点「注册代理服务（草稿）」弹出「操作未完成——当前岗位无权执行此操作」。三处口径互相打架致 403：

- 前端 `zw-brain-web/src/pages/P5ApiServiceWizard.vue:149,167` 硬编码 `role:'ROLE_ORGAN_OPERATER'`（不取真实登录角色）；
- 后端 `zw_brain/domain/policy.py:112` `resource.api.register.execute = {ROLE_ORGAN_MANAGER, ROLE_BUSIAUDIT}`，**不含部门操作员**；
- 入口层 `session_context.py:131 resolve_trusted_role`：payload.role 不在会话 allowed_roles 内即 403。

业务运营员登录 + 页面强发部门操作员角色 → 两者皆不在交集 → 403。

### 旧平台权威口径（v5 实读）

| 旧平台菜单（角色菜单 v5 sheet2） | 旧平台角色 |
|---|---|
| 服务注册 / 创建代理服务 | **部门操作员、部门管理员** |
| 导入代理服务 | 部门操作员、部门管理员 |
| 融合服务受理 | 业务运营员（受理 ≠ 注册） |
| 融合服务审核 | 部门管理员 |

即：服务**注册**是部门操作员/管理员的供数动作；业务运营员只做**受理**，不参与注册。当前后端把注册权错配给业务运营员、漏了部门操作员——口径错。

### 裁决（产品研发负责人 sign-off）

1. **代理服务注册（`resource.api.register` / `submit_review`）= 部门操作员（`ROLE_ORGAN_OPERATER`）+ 部门管理员（`ROLE_ORGAN_MANAGER`）**；业务运营员（`ROLE_BUSIAUDIT`）退出注册。
2. **代理服务审核 / 发布（`resource.api.review` / `publish` / `withdraw`）= 部门管理员**；对齐 v5「融合服务审核 = 部门管理员」，业务运营员退出服务审核。

### 实现约束（承接 T6/T7/T8）

- 后端 `policy.py:112-122`：`register`/`submit_review` 角色集合改为 `{ROLE_ORGAN_OPERATER, ROLE_ORGAN_MANAGER}`；`review`/`publish`/`withdraw` 收敛为 `{ROLE_ORGAN_MANAGER}`（连带审计只读不变）。
- 前端 `P5ApiServiceWizard.vue:149,167` 去硬编码、改 `getProductRole().value`；`pageAccess.ts:127-131 ACTION_ROLE_GATES` 与后端 `PERMISSION_ROLES` 须 set-equal（仓内守卫）。
- 无权角色入口/按钮不渲染（守「无权即不可见」，非「可见+禁用/403」）。
- 落地后三角色真 UI 实测注册可提交，带 D37 验收。

---

## GATE-2 ｜「反向编目审核」命名（G1，承 6.4#16）

### 背景与根因

6.4#16 业务反馈「字段裁决/字段审核」是工程黑话，期望改「目录审核」。但 zw-brain 页头**正向编目**已有「目录审核」（部门审→平台审收件箱）；维护数据供给侧那张卡是**反向编目**（从已有库表反推目录）的审核——两者是不同工作流。若都叫「目录审核」会一词二义撞名（违一词一概念 D52.a）。当前实现已去净黑话、选词「**反向编目审核**」（`P5Provider.vue:80`，「字段审核/字段裁决」仅存代码注释、无用户可见残留）。

### 裁决（产品研发负责人 sign-off）

**采纳「反向编目审核」**作为该卡最终用词，与正向编目「目录审核」并存区分，守一词一概念。不采用「目录审核」（避免与正向编目撞名）。

### 实现约束（承接 G1）

- `P5Provider.vue:76-80` 用户可见 label 保持「反向编目审核」；清理遗留「字段审核/字段裁决」代码注释（避免后续阅读者误判）。R12 段24 兜底。改前端模板触发 feature-backed，须 `--with-e2e` 重采。

---

## 与既有决策的关系

- 承 D53（feedback-0605-gate）：D53 已裁定「API服务化重写为代理服务注册向导」方向；D54 在其下补**注册/审核角色口径**这一 D28 必签项（D53 当时未展开角色）。
- 承 D52.a（一词一概念）：GATE-2 命名裁决同构——拒绝撞名同名词。
- 不反转任何既有决策；不抬 `.feature` 状态（decision_only）。两项实现各带自身测量与 D37 验收。
